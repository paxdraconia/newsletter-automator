"""
update_corpus_substack_url() — the Step 4 backfill.

Finds an already-published corpus file and patches one frontmatter field via
GitHub's read-modify-write (GET for the sha, PUT with it). The property worth
protecting is that it touches *only* substack_url: the body and every other
field must survive byte-for-byte, because this runs against issues that are
already the canonical record.
"""

import re

import pytest
import yaml

from conftest import seed_published_episode
from sheets import update_corpus_substack_url

ISSUE_PATH = "issues/2026-08-02-some-real-episode.md"

ORIGINAL = (
    "---\n"
    "title: 'Some Real Episode'\n"
    "date: '2026-08-02'\n"
    "slug: some-real-episode\n"
    "status: published\n"
    "episode_id: 20\n"
    "substack_url: ''\n"
    "sources:\n"
    "- url: https://example.com/a\n"
    "  section: Build vs Buy\n"
    "  reflection: A note that must not change\n"
    "  category: L&D\n"
    "affiliate_books: []\n"
    "tags: []\n"
    "positions: []\n"
    "---\n"
    "\n"
    "Happy Wednesday!\n\nSome body text here.\n"
)

NEW_URL = "https://alyn.substack.com/p/some-real-episode"


def body_of(text):
    return text.split("---\n", 2)[2]


@pytest.fixture
def episode(spreadsheet, github):
    seed_published_episode(spreadsheet, 20, "2026-08-02 10:18", "Some Real Episode")
    github.files[ISSUE_PATH] = {"content": ORIGINAL, "sha": "abc123sha"}
    return spreadsheet


@pytest.fixture
def backfilled(episode, github, github_config):
    update_corpus_substack_url(episode, 20, NEW_URL, github_config)
    return github


def test_reads_then_writes_once(backfilled):
    assert len(backfilled.gets) == 1
    assert len(backfilled.puts) == 1


def test_put_carries_the_sha_from_the_get(backfilled):
    assert backfilled.puts[-1]["json"]["sha"] == "abc123sha"


def test_substack_url_is_set(backfilled):
    fm = yaml.safe_load(
        re.match(r"^---\n(.*?\n)---\n", backfilled.last_put_content(), re.S).group(1)
    )
    assert fm["substack_url"] == NEW_URL


def test_other_frontmatter_survives(backfilled):
    fm = yaml.safe_load(
        re.match(r"^---\n(.*?\n)---\n", backfilled.last_put_content(), re.S).group(1)
    )
    assert fm["title"] == "Some Real Episode"
    assert fm["episode_id"] == 20
    assert fm["sources"][0]["reflection"] == "A note that must not change"


def test_body_preserved_byte_for_byte(backfilled):
    assert body_of(backfilled.last_put_content()) == body_of(ORIGINAL)


@pytest.mark.parametrize("episode_id,url", [
    ("", NEW_URL),      # no episode attached
    (20, ""),           # no URL captured yet
])
def test_no_api_calls_without_both_inputs(episode, github, github_config, episode_id, url):
    update_corpus_substack_url(episode, episode_id, url, github_config)
    assert github.gets == [] and github.puts == []


def test_no_api_calls_when_unconfigured(episode, github):
    update_corpus_substack_url(episode, 20, NEW_URL, None)
    assert github.gets == [] and github.puts == []


def test_unknown_episode_id_is_a_noop(episode, github, github_config):
    update_corpus_substack_url(episode, 9999, NEW_URL, github_config)
    assert github.gets == [] and github.puts == []


def test_missing_corpus_file_is_silent(episode, github, github_config):
    """404 means the corpus write never ran for that episode. Not an error."""
    github.get_404 = True
    update_corpus_substack_url(episode, 20, NEW_URL, github_config)
    assert github.puts == []


def test_put_failure_raises_for_the_caller_to_catch(episode, github, github_config):
    github.put_fails = True
    with pytest.raises(RuntimeError, match="GitHub API error"):
        update_corpus_substack_url(episode, 20, NEW_URL, github_config)
