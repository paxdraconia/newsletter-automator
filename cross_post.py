"""
cross_post.py - LinkedIn + Threads publishing for the cross-poster (v2).

Mirrors the gemini.py / sheets.py separation: this module owns all third-party
posting APIs and the orchestration around a single fire attempt. The Streamlit
UI calls post_now() (Phase 1) and the GitHub Actions cron will call
process_pending() (Phase 2). Both share the same core helpers below.

Design notes:
  * Dry-run mode skips the network call and returns a synthetic "[DRY RUN]" URL.
    Same code path otherwise — so the CrossPost_Log audit trail is identical
    whether you're testing or live.
  * Errors don't raise out of post_now(); they're captured into the row's
    *_Error column so the UI can surface a friendly message without crashing.
  * Threads multi-segment posts are handled by splitting on the
    THREADS_SEGMENT_DELIMITER and chaining replies.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from config import get_linkedin_credentials, get_threads_credentials
from constants import (
    CHANNEL_LINKEDIN,
    CHANNEL_THREADS,
    THREADS_CHAR_LIMIT,
    THREADS_SEGMENT_DELIMITER,
    XP_STATUS_FAILED,
    XP_STATUS_POSTED,
    XP_STATUS_PROCESSING,
)
from sheets import (
    add_pending_crosspost,
    log_crosspost_attempt,
    update_crosspost_status,
)

logger = logging.getLogger(__name__)


# --- Threads segment helpers -------------------------------------------------


def split_threads_content(content: str) -> list[str]:
    """
    Split Gemini's Threads output into individual segments.

    Handles both single-post (one segment) and multi-segment threads. Trims
    whitespace on each segment so leading/trailing newlines from Gemini's
    output don't burn against the 500-char budget.
    """
    if not content:
        return []
    raw_parts = content.split(THREADS_SEGMENT_DELIMITER)
    return [p.strip() for p in raw_parts if p.strip()]


def threads_segments_within_limit(content: str) -> tuple[bool, list[int]]:
    """
    Check whether every segment fits the 500-char Threads limit.

    Returns a tuple of (all_ok, segment_lengths). The UI uses the lengths to
    show a per-segment counter and a red badge on any segment over the cap.
    """
    segments = split_threads_content(content)
    lengths = [len(s) for s in segments]
    return (all(l <= THREADS_CHAR_LIMIT for l in lengths), lengths)


# --- LinkedIn API wrapper ----------------------------------------------------


LINKEDIN_UGC_ENDPOINT = "https://api.linkedin.com/v2/ugcPosts"


class CrossPostError(Exception):
    """Raised when a real (non-dry-run) post attempt fails."""


def _post_to_linkedin_real(content: str) -> str:
    """
    POST to LinkedIn's UGC endpoint. Returns the post URL on success.

    Raises CrossPostError with a helpful message on auth or API failures.
    """
    creds = get_linkedin_credentials()
    token = creds.get("access_token")
    urn = creds.get("person_urn")

    if not token or not urn:
        raise CrossPostError(
            "LinkedIn credentials missing. Set LINKEDIN_ACCESS_TOKEN and "
            "LINKEDIN_PERSON_URN in your .env or Streamlit Secrets. See the "
            "OAuth setup section of the README."
        )

    payload = {
        "author": urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": content},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    response = requests.post(
        LINKEDIN_UGC_ENDPOINT, json=payload, headers=headers, timeout=15,
    )

    if response.status_code == 401:
        raise CrossPostError(
            "LinkedIn token expired or invalid (HTTP 401). Re-run the LinkedIn "
            "auth flow and update LINKEDIN_ACCESS_TOKEN in your secrets."
        )
    if not response.ok:
        raise CrossPostError(
            f"LinkedIn API error {response.status_code}: {response.text[:300]}"
        )

    # The post ID is returned in the response header `x-restli-id` and also
    # in the body's `id` field. Build a viewable URL from it.
    post_id = response.headers.get("x-restli-id") or response.json().get("id", "")
    if not post_id:
        return "https://www.linkedin.com/feed/"
    return f"https://www.linkedin.com/feed/update/{post_id}/"


# --- Threads API wrapper -----------------------------------------------------


THREADS_BASE = "https://graph.threads.net/v1.0"


def _post_threads_segment(
    text: str, *, token: str, user_id: str, reply_to_id: Optional[str] = None,
) -> tuple[str, str]:
    """
    Post a single Threads segment (top-level or reply).

    Threads uses a two-step publish: create a media container, then publish it.
    Returns (media_id, permalink).
    """
    create_url = f"{THREADS_BASE}/{user_id}/threads"
    create_params = {
        "media_type": "TEXT",
        "text": text,
        "access_token": token,
    }
    if reply_to_id:
        create_params["reply_to_id"] = reply_to_id

    create_resp = requests.post(create_url, params=create_params, timeout=15)
    if not create_resp.ok:
        raise CrossPostError(
            f"Threads container create failed "
            f"({create_resp.status_code}): {create_resp.text[:300]}"
        )
    container_id = create_resp.json().get("id")
    if not container_id:
        raise CrossPostError("Threads container response missing 'id'.")

    publish_url = f"{THREADS_BASE}/{user_id}/threads_publish"
    publish_resp = requests.post(
        publish_url,
        params={"creation_id": container_id, "access_token": token},
        timeout=15,
    )
    if not publish_resp.ok:
        raise CrossPostError(
            f"Threads publish failed "
            f"({publish_resp.status_code}): {publish_resp.text[:300]}"
        )
    media_id = publish_resp.json().get("id", container_id)

    # Permalink lookup is a separate GET; we synthesize a best-effort URL.
    permalink = f"https://www.threads.net/@me/post/{media_id}"
    return media_id, permalink


def _post_to_threads_real(content: str) -> str:
    """
    Post a (possibly multi-segment) Threads thread. Returns the permalink of
    the first post.
    """
    creds = get_threads_credentials()
    token = creds.get("long_lived_token")
    user_id = creds.get("user_id")

    if not token or not user_id:
        raise CrossPostError(
            "Threads credentials missing. Set META_LONG_LIVED_TOKEN and "
            "THREADS_USER_ID in your .env or Streamlit Secrets. See the "
            "OAuth setup section of the README."
        )

    segments = split_threads_content(content)
    if not segments:
        raise CrossPostError("Threads content is empty.")

    over_limit = [i for i, s in enumerate(segments) if len(s) > THREADS_CHAR_LIMIT]
    if over_limit:
        raise CrossPostError(
            f"Threads segment(s) {over_limit} exceed the {THREADS_CHAR_LIMIT}-char "
            "limit. Edit the post and retry."
        )

    first_id, first_url = _post_threads_segment(
        segments[0], token=token, user_id=user_id,
    )
    parent_id = first_id
    for segment in segments[1:]:
        parent_id, _ = _post_threads_segment(
            segment, token=token, user_id=user_id, reply_to_id=parent_id,
        )

    return first_url


# --- Public dispatch ---------------------------------------------------------


def post_to_channel(channel: str, content: str, *, dry_run: bool = False) -> str:
    """
    Post a single channel's content. Returns the resulting post URL (or a
    synthetic dry-run URL).

    This is the one function the cron and the UI both call. Channel-specific
    transport details (LinkedIn UGC vs Threads two-step) are hidden inside.
    """
    if not content:
        raise CrossPostError(f"No content to post for channel '{channel}'.")

    if dry_run:
        logger.info(
            "[DRY RUN] Would post to %s (%d chars):\n%s",
            channel, len(content), content,
        )
        return f"[DRY RUN: {channel}]"

    if channel == CHANNEL_LINKEDIN:
        return _post_to_linkedin_real(content)
    if channel == CHANNEL_THREADS:
        return _post_to_threads_real(content)
    raise CrossPostError(f"Unknown channel: {channel}")


# --- Orchestration: post_now (Phase 1 immediate flow) ------------------------


def post_now(
    spreadsheet,
    *,
    source_content: str,
    substack_url: str,
    linkedin_content: str,
    threads_content: str,
    episode_id: str = "",
    dry_run: bool = False,
):
    """
    Create a Pending_CrossPosts row and immediately attempt to post both
    channels. Used by the Phase 1 "Post Now" UI button.

    Returns a dict per channel describing the outcome:
        {
            "linkedin": {"status": "posted", "url": "...", "error": ""},
            "threads":  {"status": "failed", "url": "",    "error": "..."},
        }

    Channels with empty content come back as {"status": "skipped"}.
    """
    crosspost_id = add_pending_crosspost(
        spreadsheet,
        source_content=source_content,
        substack_url=substack_url,
        linkedin_content=linkedin_content,
        linkedin_scheduled_at_utc="",
        threads_content=threads_content,
        threads_scheduled_at_utc="",
        episode_id=episode_id,
        dry_run=dry_run,
        initial_status=XP_STATUS_PROCESSING,
    )

    channels = (
        (CHANNEL_LINKEDIN, linkedin_content),
        (CHANNEL_THREADS, threads_content),
    )
    results = {}

    for channel, content in channels:
        if not content:
            results[channel] = {"status": "skipped", "url": "", "error": ""}
            continue
        try:
            post_url = post_to_channel(channel, content, dry_run=dry_run)
            update_crosspost_status(
                spreadsheet, crosspost_id, channel,
                status=XP_STATUS_POSTED, post_url=post_url, error_message="",
            )
            log_crosspost_attempt(
                spreadsheet, crosspost_id, channel,
                result="dry_run" if dry_run else "posted",
                post_url=post_url, was_dry_run=dry_run,
            )
            results[channel] = {"status": "posted", "url": post_url, "error": ""}
        except CrossPostError as exc:
            err = str(exc)
            update_crosspost_status(
                spreadsheet, crosspost_id, channel,
                status=XP_STATUS_FAILED, error_message=err,
            )
            log_crosspost_attempt(
                spreadsheet, crosspost_id, channel,
                result="failed", error_message=err, was_dry_run=dry_run,
            )
            results[channel] = {"status": "failed", "url": "", "error": err}
        except Exception as exc:  # pragma: no cover — defensive
            logger.exception("Unexpected error in post_now")
            err = f"Unexpected error: {exc}"
            update_crosspost_status(
                spreadsheet, crosspost_id, channel,
                status=XP_STATUS_FAILED, error_message=err,
            )
            log_crosspost_attempt(
                spreadsheet, crosspost_id, channel,
                result="failed", error_message=err, was_dry_run=dry_run,
            )
            results[channel] = {"status": "failed", "url": "", "error": err}

    return {"crosspost_id": crosspost_id, "channels": results}
