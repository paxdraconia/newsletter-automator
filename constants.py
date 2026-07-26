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

# Cross-poster session keys
SK_XP_SOURCE = "xp_source_content"
SK_XP_SUBSTACK_URL = "xp_substack_url"
SK_XP_LINKEDIN_DRAFT = "xp_linkedin_draft"
SK_XP_THREADS_DRAFT = "xp_threads_draft"
SK_XP_FROM_EPISODE = "xp_from_episode"   # True when arrived via post-publish button
SK_XP_EPISODE_ID = "xp_episode_id"       # Episode_ID of the source episode
SK_XP_DRY_RUN = "xp_dry_run"
SK_XP_LAST_RESULT = "xp_last_result"     # Last post_now result for inline feedback

# Flash state set by publish, read by the next Cluster & Draft render.
# Holds {"episode_id": int, "source_content": str} so we can offer a
# "Cross-Post This Episode" handoff once on the success screen.
SK_JUST_PUBLISHED = "just_published"

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

# Keys to clear when resetting a cross-post draft
XP_SESSION_KEYS = [
    SK_XP_SOURCE,
    SK_XP_SUBSTACK_URL,
    SK_XP_LINKEDIN_DRAFT,
    SK_XP_THREADS_DRAFT,
    SK_XP_FROM_EPISODE,
    SK_XP_EPISODE_ID,
    SK_XP_LAST_RESULT,
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
PAGE_CROSS_POST = "Cross-Post"
PAGE_SETTINGS = "Settings"
ALL_PAGES = [
    PAGE_DASHBOARD,
    PAGE_ADD_CONTENT,
    PAGE_CLUSTER_DRAFT,
    PAGE_CROSS_POST,
    PAGE_SETTINGS,
]

# --- Cross-poster ---
CHANNEL_LINKEDIN = "linkedin"
CHANNEL_THREADS = "threads"
CROSS_POST_CHANNELS = [CHANNEL_LINKEDIN, CHANNEL_THREADS]

# Status enum for Pending_CrossPosts rows (per channel)
XP_STATUS_PENDING = "pending"
XP_STATUS_PROCESSING = "processing"
XP_STATUS_POSTED = "posted"
XP_STATUS_FAILED = "failed"
XP_STATUS_CANCELLED = "cancelled"

# Hard cap on a single Threads segment (per Threads docs)
THREADS_CHAR_LIMIT = 500
THREADS_SEGMENT_DELIMITER = "---THREAD---"

# LinkedIn target word band (soft, enforced via prompt + UI hint, not API)
LINKEDIN_TARGET_MIN_WORDS = 150
LINKEDIN_TARGET_MAX_WORDS = 250
