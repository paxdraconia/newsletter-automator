"""
constants.py - Shared constants for the Newsletter Automator.

All magic strings, session state keys, and repeated values live here.
Import what you need instead of scattering string literals across files.
"""

# --- App ---
APP_TITLE = "Newsletter Automator"

# --- Gemini AI ---
GEMINI_MODEL = "gemini-2.5-flash"

# --- Draft section names ---
# Used when building, editing, and publishing newsletter drafts.
SECTION_INTRO = "Intro"
SECTION_FOOTER = "Footer"
SECTION_CLOSING = "Closing"
SECTION_AFFILIATE = "Affiliate Picks"

# --- Session state keys ---
# Centralised here so a typo becomes an ImportError instead of a silent bug.
SK_CLUSTERS = "clusters"
SK_CLUSTER_ENTRIES = "cluster_entries"
SK_SELECTED_CLUSTERS = "selected_clusters"
SK_DRAFT_SECTIONS = "draft_sections"
SK_SECTION_ENTRY_MAP = "section_entry_map"
SK_DRAFT_ENTRIES_LOOKUP = "draft_entries_lookup"
SK_DRAFT_ENTRY_IDS = "draft_entry_ids"
SK_SHOW_PREVIEW = "show_preview"
SK_CONFIRM_PUBLISH = "confirm_publish"
SK_AFFILIATE_SUGGESTIONS = "affiliate_suggestions"
SK_AFFILIATE_BOOK_TITLES = "affiliate_book_titles"

# Keys to clear when resetting a draft (Clear Draft + after Publish)
DRAFT_SESSION_KEYS = [
    SK_DRAFT_SECTIONS,
    SK_CLUSTERS,
    SK_CLUSTER_ENTRIES,
    SK_SELECTED_CLUSTERS,
    SK_SHOW_PREVIEW,
    SK_SECTION_ENTRY_MAP,
    SK_DRAFT_ENTRIES_LOOKUP,
    SK_DRAFT_ENTRY_IDS,
    SK_CONFIRM_PUBLISH,
    SK_AFFILIATE_SUGGESTIONS,
    SK_AFFILIATE_BOOK_TITLES,
]

# --- Content categories ---
DEFAULT_CATEGORIES = [
    "Tech", "Science", "Culture", "Business", "AI/ML",
    "Programming", "L&D", "Fun", "Other",
]

# --- Backlog statuses ---
VALID_STATUSES = ["New", "Reviewed", "Queued", "Used", "Archived"]

# --- Page navigation ---
PAGE_DASHBOARD = "Dashboard"
PAGE_ADD_CONTENT = "Add Content"
PAGE_CLUSTER_DRAFT = "Cluster & Draft"
PAGE_SETTINGS = "Settings"
ALL_PAGES = [PAGE_DASHBOARD, PAGE_ADD_CONTENT, PAGE_CLUSTER_DRAFT, PAGE_SETTINGS]
