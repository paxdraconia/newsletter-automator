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
