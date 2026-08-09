"""
publish_episode() — the publish path, including the corpus write.

The load-bearing property here is the last test in this file: a corpus write
failure must never break a publish. Everything else about publishing is
recoverable; a half-published episode is not.
"""

import re

import pytest
import yaml

from conftest import seed_backlog
from sheets import BACKLOG_TAB, DRAFT_TAB, EPISODES_TAB, publish_episode

SECTIONS = [
    {"section": "Intro", "content": "Happy Wednesday!"},
    {"section": "Build vs Buy", "content": "Some real analysis here."},
    {"section": "Footer", "content": "See you next week."},
]


def frontmatter_of(text):
    return yaml.safe_load(re.match(r"^---\n(.*?\n)---\n", text, re.S).group(1))


@pytest.fixture
def published(spreadsheet, github, github_config):
    """A normal publish: two backlog entries, an affiliate book, a real title."""
    seed_backlog(spreadsheet, [
        {"ID": 1, "URL": "https://example.com/a",
         "Reflection": "Good numbers here", "Category": "L&D"},
        {"ID": 2, "URL": "https://example.com/b",
         "Reflection": "", "Category": "AI/ML"},
    ])
    episode_id = publish_episode(
        spreadsheet, SECTIONS, [1, 2],
        affiliate_book_titles=["Map It — Cathy Moore"],
        episode_title='Your LMS Is Just a "System of Record."',
        section_entry_map={"Build vs Buy": [1, 2]},
        corpus_github=github_config,
    )
    return episode_id


def test_records_episode_row(spreadsheet, published):
    assert len(spreadsheet.worksheet(EPISODES_TAB).get_all_values()) == 2


def test_marks_entries_used(spreadsheet, published):
    records = spreadsheet.worksheet(BACKLOG_TAB).get_all_records()
    assert all(r["Status"] == "Used" for r in records)


def test_clears_draft(spreadsheet, published):
    assert len(spreadsheet.worksheet(DRAFT_TAB).get_all_values()) == 1


def test_writes_exactly_one_corpus_file(github, published):
    assert len(github.puts) == 1


def test_corpus_put_targets_issues_path(github, published):
    url = github.puts[-1]["url"]
    assert url.startswith(
        "https://api.github.com/repos/paxdraconia/nerdout-corpus/contents/issues/"
    )
    assert url.endswith("-your-lms-is-just-a-system-of-record.md")


def test_corpus_put_auth_and_branch(github, published):
    assert github.puts[-1]["json"]["branch"] == "master"
    assert github.puts[-1]["headers"]["Authorization"] == "Bearer fake-token"


def test_frontmatter_matches_schema(github, published):
    fm = frontmatter_of(github.last_put_content())
    assert fm["title"] == 'Your LMS Is Just a "System of Record."'
    assert fm["slug"] == "your-lms-is-just-a-system-of-record"
    assert fm["status"] == "published"
    assert fm["episode_id"] == published
    assert fm["substack_url"] == ""      # backfilled later by the cross-post flow
    assert fm["affiliate_books"] == ["Map It — Cathy Moore"]
    assert fm["tags"] == []
    assert fm["positions"] == []          # Sprint 2 owns this; never set at publish


def test_sources_joined_from_backlog(github, published):
    fm = frontmatter_of(github.last_put_content())
    assert fm["sources"][0] == {
        "url": "https://example.com/a",
        "section": "Build vs Buy",
        "reflection": "Good numbers here",
        "category": "L&D",
    }
    # An entry saved without a note keeps an empty string, not a missing key.
    assert fm["sources"][1]["reflection"] == ""


def test_body_contains_every_section(github, published):
    content = github.last_put_content()
    for section in SECTIONS:
        assert section["content"] in content


def test_freehand_episode_has_no_sources(spreadsheet, github, github_config):
    publish_episode(
        spreadsheet, [{"section": "Intro", "content": "A quick freehand note."}],
        [], episode_title="A Freehand Episode", corpus_github=github_config,
    )
    assert len(github.puts) == 1
    assert frontmatter_of(github.last_put_content())["sources"] == []


def test_blank_title_falls_back_to_section_names(spreadsheet, github, github_config):
    publish_episode(
        spreadsheet,
        [{"section": "Intro", "content": "Hi"},
         {"section": "AI Roundup", "content": "Stuff"}],
        [], episode_title="   ", corpus_github=github_config,
    )
    assert "ai-roundup" in github.puts[-1]["url"]


def test_corpus_failure_never_breaks_the_publish(
    spreadsheet, github, github_config,
):
    """The whole reason the corpus write is wrapped. Publishing must survive."""
    seed_backlog(spreadsheet, [
        {"ID": 1, "URL": "https://x.com", "Reflection": "r", "Category": "c"},
    ])
    github.put_fails = True

    episode_id = publish_episode(
        spreadsheet, [{"section": "Intro", "content": "test"}], [1],
        episode_title="Should Still Publish", section_entry_map={},
        corpus_github=github_config,
    )

    assert episode_id is not None
    assert len(spreadsheet.worksheet(EPISODES_TAB).get_all_values()) == 2
    assert all(
        r["Status"] == "Used"
        for r in spreadsheet.worksheet(BACKLOG_TAB).get_all_records()
    )
    assert len(spreadsheet.worksheet(DRAFT_TAB).get_all_values()) == 1


@pytest.mark.parametrize("config", [
    None,
    {"token": None, "repo": "paxdraconia/nerdout-corpus", "branch": "master"},
    {"token": "t", "repo": None, "branch": "master"},
])
def test_no_corpus_call_when_unconfigured(spreadsheet, github, config):
    episode_id = publish_episode(
        spreadsheet, [{"section": "Intro", "content": "test"}], [],
        episode_title="No Config", corpus_github=config,
    )
    assert episode_id is not None
    assert github.puts == []
