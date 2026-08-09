"""
Shared test doubles for the sheets.py data layer.

Everything here is in-memory: no Google Sheets API, no GitHub API, no network.
The publish path writes to a real spreadsheet and commits to a real repo in
production, so the tests exercise the real functions against fakes rather than
against anything that could touch the live newsletter data.
"""

import base64
import sys
from pathlib import Path

import pytest

# Tests live in tests/; the modules under test are at the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sheets  # noqa: E402
from sheets import (  # noqa: E402
    BACKLOG_HEADERS,
    BACKLOG_TAB,
    BOOK_HEADERS,
    BOOK_TAB,
    DRAFT_HEADERS,
    DRAFT_TAB,
    EPISODES_TAB,
)

EPISODES_HEADERS_FAKE = [
    "Episode_ID", "Publish_Date", "Title", "Entry_IDs", "Affiliate_Books",
]


class FakeWorksheet:
    def __init__(self, headers):
        self.headers = list(headers)
        self.rows = [list(headers)]

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def get_all_records(self):
        return [dict(zip(self.rows[0], r)) for r in self.rows[1:]]

    def append_row(self, row, value_input_option=None):
        self.rows.append(list(row))

    def row_values(self, n):
        return self.rows[n - 1] if len(self.rows) >= n else []

    def update_cells(self, cells, value_input_option=None):
        for cell in cells:
            self._ensure(cell.row, cell.col)
            self.rows[cell.row - 1][cell.col - 1] = cell.value

    def update_cell(self, row, col, value):
        self._ensure(row, col)
        self.rows[row - 1][col - 1] = value

    def cell(self, row, col):
        class _Cell:
            def __init__(self, value):
                self.value = value

        r = self.rows[row - 1] if len(self.rows) >= row else []
        return _Cell(r[col - 1] if len(r) >= col else None)

    def find(self, query, in_column=None):
        # Mirrors gspread 6.x: returns None on no match rather than raising.
        for i, row in enumerate(self.rows):
            idx = in_column - 1
            if len(row) > idx and row[idx] == query:
                class _FoundCell:
                    pass

                found = _FoundCell()
                found.row = i + 1
                return found
        return None

    def batch_clear(self, ranges):
        self.rows = [self.rows[0]]

    def update(self, rows, range_str, value_input_option=None):
        self.rows = [self.rows[0]] + [list(r) for r in rows]

    def _ensure(self, row, col):
        while len(self.rows) < row:
            self.rows.append([""] * len(self.headers))
        target = self.rows[row - 1]
        while len(target) < col:
            target.append("")


class FakeSpreadsheet:
    def __init__(self):
        self._tabs = {
            EPISODES_TAB: FakeWorksheet(EPISODES_HEADERS_FAKE),
            BACKLOG_TAB: FakeWorksheet(BACKLOG_HEADERS),
            BOOK_TAB: FakeWorksheet(BOOK_HEADERS),
            DRAFT_TAB: FakeWorksheet(DRAFT_HEADERS),
        }

    def worksheet(self, name):
        return self._tabs[name]


class FakeResponse:
    def __init__(self, ok=True, status_code=201, text="", json_data=None):
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._json_data = json_data

    def json(self):
        return self._json_data


class FakeGitHub:
    """
    Stands in for the GitHub Contents API.

    Records every request so tests can assert on the URL, payload and headers,
    and can serve a stored file so the read-modify-write backfill path has
    something to fetch.
    """

    def __init__(self):
        self.puts = []
        self.gets = []
        self.files = {}          # "issues/name.md" -> {"content": str, "sha": str}
        self.put_fails = False
        self.get_404 = False

    def put(self, url, json=None, headers=None, timeout=None):
        self.puts.append({"url": url, "json": json, "headers": headers})
        if self.put_fails:
            return FakeResponse(ok=False, status_code=422, text="Simulated failure")
        return FakeResponse(ok=True, status_code=201)

    def get(self, url, headers=None, params=None, timeout=None):
        self.gets.append({"url": url, "headers": headers, "params": params})
        if self.get_404:
            return FakeResponse(ok=False, status_code=404, text="Not Found")
        entry = self.files.get(url.split("/contents/", 1)[1])
        if entry is None:
            return FakeResponse(ok=False, status_code=404, text="Not Found")
        return FakeResponse(
            ok=True,
            status_code=200,
            json_data={
                "content": base64.b64encode(
                    entry["content"].encode("utf-8")
                ).decode("ascii"),
                "sha": entry["sha"],
            },
        )

    def last_put_content(self):
        return base64.b64decode(self.puts[-1]["json"]["content"]).decode("utf-8")


@pytest.fixture
def spreadsheet():
    return FakeSpreadsheet()


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(sheets.requests, "put", fake.put)
    monkeypatch.setattr(sheets.requests, "get", fake.get)
    return fake


@pytest.fixture
def github_config():
    return {
        "token": "fake-token",
        "repo": "paxdraconia/nerdout-corpus",
        "branch": "master",
    }


def seed_backlog(spreadsheet, entries):
    """entries: [{ID, URL, Reflection, Category}] written as Queued rows."""
    worksheet = spreadsheet.worksheet(BACKLOG_TAB)
    for entry in entries:
        worksheet.append_row([
            entry["ID"], "2026-07-26", entry["URL"], entry["Reflection"],
            entry["Category"], "Queued", "FALSE", "", "",
        ])


def seed_published_episode(spreadsheet, episode_id, publish_date, title):
    spreadsheet.worksheet(EPISODES_TAB).append_row(
        [episode_id, publish_date, title, "1,2", ""]
    )
