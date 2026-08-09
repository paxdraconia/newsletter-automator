"""
Small pure helpers that other code depends on being exactly right.

_slugify in particular is a cross-repo contract: the corpus repo's
file_issue.py duplicates this logic deliberately (the two repos are joined by
SCHEMA.md, not by an import), so a change here silently means two producers
writing different filenames for the same title.
"""

import pytest

from conftest import seed_published_episode
from config import _normalize_person_urn
from sheets import _slugify, compute_fallback_title, read_published_episodes

INTRO = {"section": "Intro", "content": ""}
FOOTER = {"section": "Footer", "content": ""}


def test_fallback_title_joins_content_sections():
    sections = [INTRO, {"section": "AI Roundup", "content": ""},
                {"section": "L&D", "content": ""}, FOOTER]
    assert compute_fallback_title(sections) == "AI Roundup | L&D"


def test_fallback_title_skips_boilerplate_sections():
    assert compute_fallback_title([INTRO, FOOTER]) == "Newsletter"


def test_fallback_title_on_empty_sections():
    assert compute_fallback_title([]) == "Newsletter"


@pytest.mark.parametrize("title,expected", [
    ('Your LMS Is Just a "System of Record."',
     "your-lms-is-just-a-system-of-record"),
    ("There Is No Such Thing as a 'Learner'",
     "there-is-no-such-thing-as-a-learner"),
    ("COGNITIVE DEBT ", "cognitive-debt"),
    ("The $4 Billion AI Hole in L&D", "the-4-billion-ai-hole-in-l-d"),
    ("!!!", "untitled"),
])
def test_slugify(title, expected):
    assert _slugify(title) == expected


@pytest.mark.parametrize("value,expected", [
    ("abc123def4", "urn:li:person:abc123def4"),
    ("urn:li:person:abc123def4", "urn:li:person:abc123def4"),
    ("  abc123def4  ", "urn:li:person:abc123def4"),
    ("", ""),
    (None, None),
])
def test_normalize_person_urn(value, expected):
    """LinkedIn's setup flow surfaces a bare member id; /author needs the URN."""
    assert _normalize_person_urn(value) == expected


def test_read_published_episodes_is_newest_first(spreadsheet):
    for i in range(1, 6):
        seed_published_episode(spreadsheet, i, f"2026-01-{i:02d} 09:00", f"Episode {i}")
    episodes = read_published_episodes(spreadsheet)
    assert [e["Episode_ID"] for e in episodes] == [5, 4, 3, 2, 1]


def test_read_published_episodes_honours_limit(spreadsheet):
    for i in range(1, 31):
        seed_published_episode(spreadsheet, i, f"2026-01-{i:02d} 09:00", f"Episode {i}")
    assert len(read_published_episodes(spreadsheet)) == 25
    assert len(read_published_episodes(spreadsheet, limit=100)) == 30


def test_read_published_episodes_on_empty_tab(spreadsheet):
    assert read_published_episodes(spreadsheet) == []
