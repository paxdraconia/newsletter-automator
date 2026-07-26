"""
config.py - Configuration and authentication module.

This module handles the difference between running locally (using a .env file)
and running on Streamlit Cloud (using streamlit.secrets). The rest of the app
doesn't need to care which environment it's in — it just calls these functions.
"""

import os
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# The default publication name. This is the newsletter you're starting with.
DEFAULT_PUBLICATION = "NerdOut"

# Google API scopes - these tell Google what permissions we need.
# "spreadsheets" = read/write Google Sheets
# "drive" = needed to list/create spreadsheets (Sheets are technically Drive files)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource(ttl=3000)
def get_gspread_client():
    """
    Returns an authenticated Google Sheets client.

    @st.cache_resource(ttl=3000) means Streamlit caches the client for ~50 minutes,
    then re-authenticates. Google service account tokens expire after 1 hour, so
    refreshing at 50 minutes prevents "token expired" crashes.

    The function tries two authentication methods:
    1. Streamlit Cloud: reads credentials from st.secrets (set in the cloud dashboard)
    2. Local development: reads credentials from a JSON file path in your .env
    """
    # Method 1: Try Streamlit Cloud secrets
    try:
        service_account_info = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(
            service_account_info, scopes=SCOPES
        )
        return gspread.authorize(credentials)
    except (KeyError, FileNotFoundError):
        pass  # Not on Streamlit Cloud, try local method

    # Method 2: Try local .env file
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)

        json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        if json_path and os.path.exists(json_path):
            credentials = Credentials.from_service_account_file(
                json_path, scopes=SCOPES
            )
            return gspread.authorize(credentials)
    except ImportError:
        pass  # python-dotenv not installed (shouldn't happen, but be safe)

    # Neither method worked — show a helpful error
    st.error(
        "Could not authenticate with Google Sheets. Please check your setup:\n\n"
        "**Local development:** Copy `.env.template` to `.env` and set "
        "`GOOGLE_SERVICE_ACCOUNT_FILE` to your service account JSON path.\n\n"
        "**Streamlit Cloud:** Add your service account credentials in "
        "Settings > Secrets. See `secrets.toml.template` for the format."
    )
    st.stop()


def get_gemini_api_key():
    """
    Returns the Gemini API key, or None if not configured.

    This is optional for Iteration 1 (no AI features yet), but the key is
    loaded here so future iterations can just call this function.
    """
    # Try Streamlit Cloud first
    try:
        return st.secrets["GEMINI_API_KEY"]
    except (KeyError, FileNotFoundError):
        pass

    # Try local .env
    try:
        from dotenv import load_dotenv

        load_dotenv(override=True)
        return os.environ.get("GEMINI_API_KEY")
    except ImportError:
        return None


def _get_secret(name):
    """
    Generic secret getter: tries Streamlit Cloud secrets, then local .env.

    Returns None if the secret isn't set in either place. Used for the
    cross-poster credentials so each one doesn't need its own helper.
    """
    try:
        return st.secrets[name]
    except (KeyError, FileNotFoundError):
        pass

    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
        return os.environ.get(name)
    except ImportError:
        return None


def get_corpus_github_config():
    """
    Returns GitHub API credentials for committing published issues to the
    nerdout-corpus repo (see sheets.py:_write_corpus_issue).

    This app runs on Streamlit Cloud, which has no filesystem access to a
    local corpus repo checkout — the corpus write goes through GitHub's
    Contents API instead, the same way any cloud app commits to a repo it
    doesn't have a local clone of.

    Keys:
        token:  A GitHub personal access token, fine-grained and scoped to
                just the corpus repo, with "Contents: Read and write"
                permission. Required — comes back None if not configured.
        repo:   "owner/repo", e.g. "paxdraconia/nerdout-corpus"
        branch: Target branch. Defaults to "master".

    Caller should treat a missing token as "not configured" and skip the
    corpus write (this must never be able to fail a publish).
    """
    return {
        "token": _get_secret("CORPUS_GITHUB_TOKEN"),
        "repo": _get_secret("CORPUS_GITHUB_REPO") or "paxdraconia/nerdout-corpus",
        "branch": _get_secret("CORPUS_GITHUB_BRANCH") or "master",
    }


def get_linkedin_credentials():
    """
    Returns a dict of LinkedIn credentials for the cross-poster.

    Keys:
        access_token: OAuth bearer token (refreshed every ~60 days)
        person_urn:   The user's URN, e.g., "urn:li:person:XXXX"
                      (captured once during the OAuth setup flow)

    Any missing value comes back as None — caller should treat that as
    "not configured" and either skip posting or surface a setup hint.
    """
    return {
        "access_token": _get_secret("LINKEDIN_ACCESS_TOKEN"),
        "person_urn": _get_secret("LINKEDIN_PERSON_URN"),
    }


def get_threads_credentials():
    """
    Returns a dict of Threads (Meta) credentials for the cross-poster.

    Keys:
        long_lived_token: Long-lived access token (60 days, auto-refreshable)
        user_id:          The Threads user ID (numeric string)
        app_id:           Meta app ID (used for token refresh in Phase 2)
        app_secret:       Meta app secret (used for token refresh in Phase 2)
    """
    return {
        "long_lived_token": _get_secret("META_LONG_LIVED_TOKEN"),
        "user_id": _get_secret("THREADS_USER_ID"),
        "app_id": _get_secret("META_APP_ID"),
        "app_secret": _get_secret("META_APP_SECRET"),
    }
