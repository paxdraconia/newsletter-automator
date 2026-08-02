"""
sheets.py - Google Sheets CRUD operations.

This module is the "data layer" of the app. It handles all reading and writing
to Google Sheets. The Streamlit UI (app.py) calls these functions instead of
talking to Google Sheets directly. This separation makes the code easier to
understand, test, and modify.

Think of Google Sheets as a simple database with tabs (worksheets) as tables
and rows as records.
"""

import base64
import logging
import re
from datetime import datetime, timezone

import gspread
import requests
import yaml
from constants import (
    SECTION_INTRO, SECTION_FOOTER, SECTION_CLOSING, SECTION_AFFILIATE,
    XP_STATUS_PENDING, XP_STATUS_PROCESSING, XP_STATUS_POSTED,
    XP_STATUS_FAILED, XP_STATUS_CANCELLED, CROSS_POST_CHANNELS,
)

logger = logging.getLogger(__name__)


# --- Tab Definitions ---
# Each tab is like a database table. These constants define the tab names
# and their column headers. If you need to add a column later, add it here.

BACKLOG_TAB = "Inbound_Backlog"
BACKLOG_HEADERS = [
    "ID", "Date", "URL", "Reflection", "Category", "Status",
    "Needs_Research",   # TRUE/FALSE — set at capture. Independent of whether a URL exists.
    "Parent_ID",        # non-empty => derived by the research agent from that entry
    "Summary",          # machine-written one-liner. NEVER written to Reflection.
]

BOOK_TAB = "Book_Ledger"
BOOK_HEADERS = ["Title", "Link", "Categories", "Last_Used", "Times_Used", "Description", "Store"]

DRAFT_TAB = "Draft_State"
DRAFT_HEADERS = ["Section", "Content", "Last_Modified"]

CONFIG_TAB = "Config"
CONFIG_HEADERS = ["Setting", "Value"]

EPISODES_TAB = "Published_Episodes"
EPISODES_HEADERS = ["Episode_ID", "Publish_Date", "Title", "Entry_IDs", "Affiliate_Books"]

# Cross-poster tabs (v2)
PENDING_XP_TAB = "Pending_CrossPosts"
PENDING_XP_HEADERS = [
    "ID", "Episode_ID", "Source_Content", "Substack_URL",
    "LinkedIn_Content", "LinkedIn_Scheduled_At_UTC", "LinkedIn_Status",
    "LinkedIn_Post_URL", "LinkedIn_Error",
    "Threads_Content", "Threads_Scheduled_At_UTC", "Threads_Status",
    "Threads_Post_URL", "Threads_Error",
    "Created_At_UTC", "Last_Attempted_At_UTC", "Retry_Count", "Dry_Run",
]

XP_LOG_TAB = "CrossPost_Log"
XP_LOG_HEADERS = [
    "Log_ID", "CrossPost_ID", "Channel", "Fired_At_UTC",
    "Result", "Post_URL", "Error_Message", "Was_Dry_Run",
]

XP_ARCHIVE_TAB = "CrossPost_Archive"
XP_ARCHIVE_HEADERS = PENDING_XP_HEADERS  # Same shape, different tab

# All tabs and their headers, grouped for easy iteration
ALL_TABS = {
    BACKLOG_TAB: BACKLOG_HEADERS,
    BOOK_TAB: BOOK_HEADERS,
    DRAFT_TAB: DRAFT_HEADERS,
    CONFIG_TAB: CONFIG_HEADERS,
    EPISODES_TAB: EPISODES_HEADERS,
    PENDING_XP_TAB: PENDING_XP_HEADERS,
    XP_LOG_TAB: XP_LOG_HEADERS,
    XP_ARCHIVE_TAB: XP_ARCHIVE_HEADERS,
}


def _clear_and_write(worksheet, rows, num_columns):
    """Clear all data rows (row 2 onward), then write new rows.

    This is the shared helper for the clear-then-write pattern used by
    save_draft(), clear_draft(), and save_config().

    Args:
        worksheet: The gspread worksheet to operate on
        rows: A list of lists to write (can be empty to just clear)
        num_columns: Number of columns in the tab (for building cell ranges)
    """
    all_values = worksheet.get_all_values()
    if len(all_values) > 1:
        last_row = len(all_values)
        end_col = chr(ord("A") + num_columns - 1)
        worksheet.batch_clear([f"A2:{end_col}{last_row}"])

    if rows:
        end_col = chr(ord("A") + num_columns - 1)
        worksheet.update(
            rows, f"A2:{end_col}{1 + len(rows)}", value_input_option="USER_ENTERED"
        )


def get_or_create_spreadsheet(client, publication_name):
    """
    Opens the Google Sheet for a publication, or creates it if it doesn't exist.

    Each publication gets its own sheet named like "NerdOut_DB".
    The "_DB" suffix is a naming convention that lets us auto-discover
    all publication sheets later (see list_publications).

    Args:
        client: An authenticated gspread client (from config.get_gspread_client)
        publication_name: e.g., "NerdOut"

    Returns:
        A gspread.Spreadsheet object you can read/write to.
    """
    sheet_name = f"{publication_name}_DB"
    try:
        return client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        # Create the sheet. Note: only the service account will own this sheet.
        # You'll need to share it with your personal Google account to see it
        # in Google Drive. The README explains how.
        return client.create(sheet_name)


def ensure_tabs(spreadsheet):
    """
    Makes sure all required tabs exist with the correct headers.

    This runs every time the app starts. If you've already set up the sheet,
    it does nothing (fast). If it's a brand new sheet, it creates all three
    tabs and adds the header row to each.

    Why we do this: It means you can just create an empty Google Sheet and
    the app will set up the structure automatically on first run.
    """
    existing_tabs = [ws.title for ws in spreadsheet.worksheets()]

    for tab_name, headers in ALL_TABS.items():
        if tab_name not in existing_tabs:
            # Create the tab with some room (1000 rows)
            worksheet = spreadsheet.add_worksheet(
                title=tab_name, rows=1000, cols=len(headers)
            )
            # Add the header row (row 1)
            worksheet.update([headers], "A1")
        else:
            # Tab exists — make sure it has headers
            worksheet = spreadsheet.worksheet(tab_name)
            first_row = worksheet.row_values(1)
            if not first_row:
                # Empty tab, add headers
                worksheet.update([headers], "A1")
            elif len(first_row) < len(headers):
                # Schema migration: tab has fewer columns than the current definition.
                # This happens when we add new columns (e.g., Description + Store to
                # Book_Ledger). We widen the sheet first, then append the missing headers.
                if worksheet.col_count < len(headers):
                    worksheet.resize(cols=len(headers))
                missing = headers[len(first_row):]
                start_col = chr(ord("A") + len(first_row))
                end_col = chr(ord("A") + len(headers) - 1)
                worksheet.update(
                    [missing], f"{start_col}1:{end_col}1"
                )

    # Clean up: remove the default "Sheet1" tab that Google creates
    # (only if our tabs exist, so we don't accidentally delete the only tab)
    if len(spreadsheet.worksheets()) > len(ALL_TABS):
        try:
            default_sheet = spreadsheet.worksheet("Sheet1")
            spreadsheet.del_worksheet(default_sheet)
        except gspread.WorksheetNotFound:
            pass  # Already deleted or doesn't exist


# --- Inbound Backlog Operations ---


def read_backlog(spreadsheet):
    """
    Returns all entries from the Inbound_Backlog tab as a list of dictionaries.

    Example return value:
    [
        {"ID": 1, "Date": "2026-03-09", "URL": "https://...", ...},
        {"ID": 2, "Date": "2026-03-09", "URL": "https://...", ...},
    ]

    Returns an empty list if there are no entries (only headers).
    """
    worksheet = spreadsheet.worksheet(BACKLOG_TAB)
    # get_all_records() uses row 1 as dictionary keys automatically
    return worksheet.get_all_records()


def add_to_backlog(spreadsheet, url, reflection, category, needs_research=False):
    """
    Adds a new entry to the Inbound_Backlog, after checking for duplicates.

    The deduplication check looks at the URL column. If the same URL already
    exists, it won't add it again (prevents you from saving the same article
    twice).

    Args:
        spreadsheet: The active spreadsheet
        url: The article/content URL
        reflection: Your thoughts about why this is interesting
        category: Category like "Tech", "AI/ML", etc.
        needs_research: Whether this entry needs the research agent to
            investigate it (independent of whether a URL is present)

    Returns:
        A tuple of (success: bool, message: str)
        - (True, "Added entry #5") on success
        - (False, "URL already exists in row 3") if it's a duplicate
    """
    worksheet = spreadsheet.worksheet(BACKLOG_TAB)

    # Check for duplicates by searching the URL column (column 3)
    # Skip deduplication when URL is empty (reflection-only entries can't be deduped)
    if url:
        try:
            cell = worksheet.find(url, in_column=3)
            if cell:
                return (False, f"This URL already exists (row {cell.row}). Skipping.")
        except gspread.exceptions.CellNotFound:
            pass  # URL not found — good, we can add it

    # Generate a simple incrementing ID
    # We count all rows (including header) so row count = next ID
    all_values = worksheet.get_all_values()
    next_id = len(all_values)  # Header is row 1, so first entry is ID 1

    # Current timestamp
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # New entries start with status "New"
    status = "New"

    needs_research_str = "TRUE" if needs_research else "FALSE"

    # Parent_ID and Summary are written only by the research agent (Sprint 2),
    # never at capture time.
    row = [
        next_id, date_str, url, reflection, category, status,
        needs_research_str, "", "",
    ]

    # USER_ENTERED means Google Sheets will parse the values like a human typed them
    # (so dates look like dates, numbers like numbers, etc.)
    worksheet.append_row(row, value_input_option="USER_ENTERED")

    return (True, f"Added entry #{next_id}")


def update_backlog_status(spreadsheet, row_number, new_status):
    """
    Updates the Status column for a specific row in the backlog.

    Args:
        spreadsheet: The active spreadsheet
        row_number: The actual row number in the sheet (1-based, including header)
        new_status: The new status string (e.g., "Reviewed", "Queued")
    """
    worksheet = spreadsheet.worksheet(BACKLOG_TAB)
    # Status is the 6th column (index 5 in headers, but Sheets uses 1-based)
    status_col = BACKLOG_HEADERS.index("Status") + 1
    worksheet.update_cell(row_number, status_col, new_status)


# --- Book Ledger Operations ---


def read_book_ledger(spreadsheet):
    """Returns all entries from the Book_Ledger tab as a list of dicts."""
    worksheet = spreadsheet.worksheet(BOOK_TAB)
    return worksheet.get_all_records()


def add_to_book_ledger(spreadsheet, title, link, categories,
                       description="", store=""):
    """
    Adds a book/resource to the Book_Ledger, after checking for duplicates.

    Deduplicates by the Link column (column 2).

    Args:
        spreadsheet: The active spreadsheet
        title: Book title
        link: Affiliate link URL
        categories: Category string (e.g., "Philosophy", "AI")
        description: Personal blurb/recommendation text
        store: Store indicator ("AZ" for Amazon, "BS" for Bookstore.org, or "")

    Returns:
        A tuple of (success: bool, message: str)
    """
    worksheet = spreadsheet.worksheet(BOOK_TAB)

    # Check for duplicate links
    if link:
        try:
            cell = worksheet.find(link, in_column=2)
            if cell:
                return (False, f"'{title}' already exists (row {cell.row}). Skipping.")
        except gspread.exceptions.CellNotFound:
            pass

    # Last_Used starts empty (set only when used in an episode). Times_Used = 0.
    row = [title, link, categories, "", 0, description, store]

    worksheet.append_row(row, value_input_option="USER_ENTERED")
    return (True, f"Added '{title}' to the Book Ledger.")


def update_book_ledger_entry(spreadsheet, row_number, updated_fields):
    """
    Updates specific fields for a book at the given sheet row number.

    Args:
        spreadsheet: The active spreadsheet
        row_number: The actual row number in the sheet (1-based, including header)
        updated_fields: A dict of field names → new values.
                        Only Title, Link, Categories, Description, Store are editable.
    """
    worksheet = spreadsheet.worksheet(BOOK_TAB)
    editable = {"Title", "Link", "Categories", "Description", "Store"}

    for field_name, new_value in updated_fields.items():
        if field_name in editable:
            col_index = BOOK_HEADERS.index(field_name) + 1  # 1-based
            worksheet.update_cell(row_number, col_index, new_value)


def delete_book_ledger_entry(spreadsheet, row_number):
    """
    Deletes a book row from the Book_Ledger tab.

    Args:
        spreadsheet: The active spreadsheet
        row_number: The actual row number in the sheet (1-based)
    """
    worksheet = spreadsheet.worksheet(BOOK_TAB)
    worksheet.delete_rows(row_number)


def update_book_usage(spreadsheet, book_titles):
    """
    Updates Last_Used and Times_Used for books that were included in a published episode.

    Called during publish to track which books have been recommended recently
    and how many times total.

    Args:
        spreadsheet: The active spreadsheet
        book_titles: List of book title strings to update
    """
    worksheet = spreadsheet.worksheet(BOOK_TAB)
    last_used_col = BOOK_HEADERS.index("Last_Used") + 1
    times_used_col = BOOK_HEADERS.index("Times_Used") + 1
    today = datetime.now().strftime("%Y-%m-%d")

    for title in book_titles:
        try:
            cell = worksheet.find(title, in_column=1)
            if cell:
                # Update Last_Used to today
                worksheet.update_cell(cell.row, last_used_col, today)
                # Increment Times_Used
                current_times = worksheet.cell(cell.row, times_used_col).value
                new_times = int(current_times or 0) + 1
                worksheet.update_cell(cell.row, times_used_col, new_times)
        except gspread.exceptions.CellNotFound:
            pass  # Book not found — skip silently


# --- Publication Discovery ---


def list_publications(client):
    """
    Discovers all publications by listing spreadsheets that end with "_DB".

    This is how multi-newsletter support works: instead of a hardcoded list,
    the app scans for all sheets the service account can access that follow
    our naming convention.

    Returns:
        A list of publication names, e.g., ["NerdOut", "FutureNewsletter"]
    """
    all_sheets = client.list_spreadsheet_files()
    publications = []
    for sheet in all_sheets:
        name = sheet["name"]
        if name.endswith("_DB"):
            # Strip the "_DB" suffix to get the publication name
            publications.append(name[:-3])
    return sorted(publications)


# --- Draft State Operations ---
# These functions manage the newsletter draft stored in the Draft_State tab.
# The draft persists in Google Sheets so you can start editing on your PC
# and finish on your phone — same data, any device.


def save_draft(spreadsheet, sections):
    """
    Saves the newsletter draft to the Draft_State tab.

    This overwrites any existing draft (clears old data first, then writes
    the new sections). Each section becomes one row.

    Args:
        spreadsheet: The active spreadsheet
        sections: A list of dicts, each with keys: "section" and "content"
                  Example: [
                      {"section": "Intro", "content": "Welcome to this week's..."},
                      {"section": "AI Revolution", "content": "Three articles caught..."},
                  ]
    """
    worksheet = spreadsheet.worksheet(DRAFT_TAB)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = [[s["section"], s["content"], timestamp] for s in sections]
    _clear_and_write(worksheet, rows, len(DRAFT_HEADERS))


def read_draft(spreadsheet):
    """
    Reads the current draft from the Draft_State tab.

    Returns:
        A list of dicts with keys: Section, Content, Last_Modified
        Returns an empty list if no draft exists.
    """
    worksheet = spreadsheet.worksheet(DRAFT_TAB)
    return worksheet.get_all_records()


def clear_draft(spreadsheet):
    """
    Deletes all draft content from the Draft_State tab (keeps headers).

    Use this when you want to start a fresh draft.
    """
    worksheet = spreadsheet.worksheet(DRAFT_TAB)
    _clear_and_write(worksheet, [], len(DRAFT_HEADERS))


def batch_update_backlog_statuses(spreadsheet, entry_ids, new_status):
    """
    Updates the Status column for multiple entries at once.

    More efficient than calling update_backlog_status() in a loop because
    it uses a single batch update instead of one API call per row.

    Args:
        spreadsheet: The active spreadsheet
        entry_ids: A list of entry IDs (integers) to update
        new_status: The new status string (e.g., "Queued")
    """
    worksheet = spreadsheet.worksheet(BACKLOG_TAB)
    status_col = BACKLOG_HEADERS.index("Status") + 1

    # Build a list of cell updates
    # Each entry ID maps to sheet row = ID + 1 (header is row 1)
    cells_to_update = []
    for entry_id in entry_ids:
        sheet_row = int(entry_id) + 1
        cells_to_update.append(
            gspread.Cell(row=sheet_row, col=status_col, value=new_status)
        )

    if cells_to_update:
        worksheet.update_cells(cells_to_update, value_input_option="USER_ENTERED")


# --- Config Operations ---
# These functions manage persistent settings in the Config tab.
# Settings are stored as key-value pairs (one per row).


def read_config(spreadsheet):
    """
    Reads all settings from the Config tab and returns them as a flat dict.

    Example return value:
        {"default_intro": "Happy Wednesday!", "default_footer": "Follow me on..."}

    Returns an empty dict if no settings have been saved yet.
    """
    worksheet = spreadsheet.worksheet(CONFIG_TAB)
    records = worksheet.get_all_records()
    # Convert list of {"Setting": key, "Value": val} dicts to a flat dict
    return {row["Setting"]: row["Value"] for row in records if row["Setting"]}


def save_config(spreadsheet, config_dict):
    """
    Saves settings to the Config tab, replacing any existing values.

    Uses the same clear-then-write pattern as save_draft().

    Args:
        spreadsheet: The active spreadsheet
        config_dict: A dict of settings, e.g. {"default_intro": "Happy Wednesday!"}
    """
    worksheet = spreadsheet.worksheet(CONFIG_TAB)
    rows = [[key, value] for key, value in config_dict.items()]
    _clear_and_write(worksheet, rows, len(CONFIG_HEADERS))


# --- Published Episodes Operations ---


def compute_fallback_title(sections):
    """
    The title used when no editorial title is given: section names joined
    with " | ", skipping Intro/Closing/Footer/Affiliate Picks. Shared between
    publish_episode() and the app.py "title is blank" warning so they can
    never drift apart.
    """
    section_names = [
        s["section"] for s in sections
        if s["section"] not in (SECTION_INTRO, SECTION_CLOSING, SECTION_FOOTER, SECTION_AFFILIATE)
    ]
    return " | ".join(section_names) if section_names else "Newsletter"


def publish_episode(
    spreadsheet, sections, entry_ids, affiliate_book_titles=None,
    episode_title=None, section_entry_map=None, corpus_github=None,
):
    """
    Publishes the current draft as an episode.

    Records the episode in the Published_Episodes tab, updates all included
    entries from Queued to Used, updates affiliate book usage stats, writes
    the issue to the nerdout-corpus repo, and clears the draft.

    Args:
        spreadsheet: The active spreadsheet
        sections: List of section dicts ({"section": str, "content": str})
        entry_ids: List of entry IDs (ints) used in this episode. Empty for
                   a freehand episode with no backlog entries attached.
        affiliate_book_titles: Optional list of book title strings that were
                               included as affiliate recommendations
        episode_title: The real editorial title, captured at publish time.
                       Falls back to the joined section names when blank, so
                       an empty title never fails the publish.
        section_entry_map: Optional dict of {section_name: [entry_ids]},
                       used to annotate each corpus source with the section
                       it was published under.
        corpus_github: Optional dict of GitHub API credentials for the
                       corpus write. See config.get_corpus_github_config().
                       If not provided (or incomplete), the corpus write is
                       skipped entirely.
    """
    worksheet = spreadsheet.worksheet(EPISODES_TAB)

    # Auto-increment episode ID
    all_values = worksheet.get_all_values()
    next_id = len(all_values)  # Same pattern as backlog IDs

    fallback_title = compute_fallback_title(sections)
    title = episode_title.strip() if episode_title and episode_title.strip() else fallback_title

    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry_ids_str = ",".join(str(eid) for eid in entry_ids)
    affiliate_str = ",".join(affiliate_book_titles) if affiliate_book_titles else ""

    row = [next_id, date_str, title, entry_ids_str, affiliate_str]
    worksheet.append_row(row, value_input_option="USER_ENTERED")

    # Mark entries as Used (freehand episodes have no entries to mark)
    if entry_ids:
        batch_update_backlog_statuses(spreadsheet, entry_ids, "Used")

    # Update affiliate book usage stats (Last_Used + Times_Used)
    if affiliate_book_titles:
        update_book_usage(spreadsheet, affiliate_book_titles)

    # Corpus write — must never be able to fail a publish. The episode above
    # is already recorded and entries already flipped to Used by this point;
    # a bad corpus_issues_dir or a filesystem error here just gets logged.
    try:
        _write_corpus_issue(
            spreadsheet, next_id, title, sections, entry_ids,
            affiliate_book_titles, section_entry_map, corpus_github,
        )
    except Exception as e:
        logger.error("Corpus write failed for episode %s: %s", next_id, e)

    # Clear the draft
    clear_draft(spreadsheet)

    # Return the episode ID so callers (e.g., the cross-post handoff) can link
    # the published episode to a follow-up cross-post.
    return next_id


def _slugify(text):
    """Kebab-case a title for use as a corpus filename slug."""
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "untitled"


def _write_corpus_issue(
    spreadsheet, episode_id, title, sections, entry_ids,
    affiliate_book_titles, section_entry_map, corpus_github,
):
    """
    Commits the published issue to the nerdout-corpus repo as a markdown file
    with SCHEMA.md-shaped frontmatter, via GitHub's Contents API (this app
    runs on Streamlit Cloud, which has no local filesystem access to a
    corpus repo checkout). See SCHEMA.md in that repo for the field
    contract this must match.
    """
    corpus_github = corpus_github or {}
    token = corpus_github.get("token")
    repo = corpus_github.get("repo")
    branch = corpus_github.get("branch", "master")
    if not token or not repo:
        return  # Corpus GitHub credentials not configured — nothing to do.

    # Map each entry_id to the section it was published under.
    entry_to_section = {}
    for section_name, ids in (section_entry_map or {}).items():
        for eid in ids:
            entry_to_section[str(eid)] = section_name

    # Join entry_ids against the backlog for URL/Reflection/Category.
    backlog_by_id = {}
    if entry_ids:
        backlog_by_id = {str(row.get("ID")): row for row in read_backlog(spreadsheet)}

    sources = []
    for eid in entry_ids:
        backlog_row = backlog_by_id.get(str(eid), {})
        sources.append({
            "url": backlog_row.get("URL", ""),
            "section": entry_to_section.get(str(eid), ""),
            "reflection": backlog_row.get("Reflection", ""),
            "category": backlog_row.get("Category", ""),
        })

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = _slugify(title)

    frontmatter = {
        "title": title,
        "date": date_str,
        "slug": slug,
        "status": "published",
        "episode_id": episode_id,
        "substack_url": "",  # backfilled later by the cross-post flow
        "sources": sources,
        "affiliate_books": affiliate_book_titles or [],
        "tags": [],
        "positions": [],  # Sprint 2
    }
    fm_yaml = yaml.safe_dump(
        frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    body = "\n\n".join(s["content"] for s in sections)
    content = f"---\n{fm_yaml}---\n\n{body}\n"

    filename = f"{date_str}-{slug}.md"
    api_url = f"https://api.github.com/repos/{repo}/contents/issues/{filename}"
    payload = {
        "message": f"Publish: {title}",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": branch,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    response = requests.put(api_url, json=payload, headers=headers, timeout=15)
    if not response.ok:
        raise RuntimeError(
            f"GitHub API error ({response.status_code}) writing {filename}: "
            f"{response.text[:300]}"
        )


# --- Cross-Poster Operations ---
# These functions manage the Pending_CrossPosts and CrossPost_Log tabs that
# back the LinkedIn/Threads cross-poster (v2). Conventions:
#   * All timestamp columns are UTC ISO 8601. The UI converts to user TZ at the edge.
#   * Status enum per channel: pending → processing → posted | failed | cancelled.
#   * "Post Now" flow writes a row at status=processing, then transitions to
#     posted/failed in the same request — same code path the Phase 2 cron uses.


def _utc_now_iso():
    """Returns the current UTC time as a string the sheet stores cleanly."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _next_id(worksheet):
    """Auto-incrementing ID by row count. Header is row 1, so first id = 1."""
    return len(worksheet.get_all_values())


def add_pending_crosspost(
    spreadsheet,
    *,
    source_content,
    substack_url,
    linkedin_content,
    linkedin_scheduled_at_utc,
    threads_content,
    threads_scheduled_at_utc,
    episode_id="",
    dry_run=False,
    initial_status=XP_STATUS_PENDING,
):
    """
    Append a new cross-post row.

    Used by both the scheduling flow (status=pending) and the Phase 1 post-now
    flow (status=processing — caller will transition to posted/failed
    immediately after the API call).

    Args:
        spreadsheet: The active spreadsheet
        source_content: Raw text used to generate previews (for audit)
        substack_url: Optional URL appended to the post body
        linkedin_content: The LinkedIn post text
        linkedin_scheduled_at_utc: UTC ISO timestamp ("" for post-now)
        threads_content: The Threads post text (single segment or thread)
        threads_scheduled_at_utc: UTC ISO timestamp ("" for post-now)
        episode_id: Optional Episode_ID linking to Published_Episodes
        dry_run: If True, the cron logs the payload but skips API calls
        initial_status: pending (default) or processing (post-now flow)

    Returns:
        The new row's ID (int).
    """
    worksheet = spreadsheet.worksheet(PENDING_XP_TAB)
    new_id = _next_id(worksheet)
    now = _utc_now_iso()

    # Both channels start at the same status. If a channel has no content
    # (user only wants one), we mark it cancelled so the cron skips it.
    li_status = initial_status if linkedin_content else XP_STATUS_CANCELLED
    th_status = initial_status if threads_content else XP_STATUS_CANCELLED

    row = [
        new_id,
        episode_id or "",
        source_content or "",
        substack_url or "",
        linkedin_content or "",
        linkedin_scheduled_at_utc or "",
        li_status,
        "",  # LinkedIn_Post_URL
        "",  # LinkedIn_Error
        threads_content or "",
        threads_scheduled_at_utc or "",
        th_status,
        "",  # Threads_Post_URL
        "",  # Threads_Error
        now,  # Created_At_UTC
        "",   # Last_Attempted_At_UTC
        0,    # Retry_Count
        "TRUE" if dry_run else "FALSE",
    ]
    worksheet.append_row(row, value_input_option="USER_ENTERED")
    return new_id


def read_pending_crossposts(spreadsheet, *, include_terminal=False):
    """
    Read all cross-post rows.

    Args:
        spreadsheet: The active spreadsheet
        include_terminal: If False (default), exclude rows whose BOTH channels
                          are in a terminal state (posted/failed/cancelled).
                          Useful for the UI's "Pending" view.

    Returns:
        List of dicts (one per row).
    """
    worksheet = spreadsheet.worksheet(PENDING_XP_TAB)
    records = worksheet.get_all_records()

    if include_terminal:
        return records

    terminal = {XP_STATUS_POSTED, XP_STATUS_FAILED, XP_STATUS_CANCELLED}
    return [
        r for r in records
        if not (r.get("LinkedIn_Status") in terminal
                and r.get("Threads_Status") in terminal)
    ]


def _row_for_crosspost(spreadsheet, crosspost_id):
    """Find the sheet row number for a crosspost ID. Returns None if missing."""
    worksheet = spreadsheet.worksheet(PENDING_XP_TAB)
    try:
        cell = worksheet.find(str(crosspost_id), in_column=1)
        return cell.row if cell else None
    except gspread.exceptions.CellNotFound:
        return None


def update_crosspost_status(
    spreadsheet, crosspost_id, channel,
    *, status=None, post_url=None, error_message=None,
    last_attempted=True, increment_retry=False,
):
    """
    Update the channel-specific status fields for a cross-post row.

    Only the fields you pass are updated. Pass status=None to leave it alone
    (e.g., if you only want to record an error message after a retry).

    Args:
        spreadsheet: The active spreadsheet
        crosspost_id: The ID column value of the row to update
        channel: "linkedin" or "threads"
        status: New status (pending/processing/posted/failed/cancelled)
        post_url: URL of the published post (on success)
        error_message: Error string (on failure)
        last_attempted: If True, stamp Last_Attempted_At_UTC = now
        increment_retry: If True, bump Retry_Count by 1
    """
    if channel not in CROSS_POST_CHANNELS:
        raise ValueError(f"Unknown channel: {channel}")

    sheet_row = _row_for_crosspost(spreadsheet, crosspost_id)
    if sheet_row is None:
        return

    worksheet = spreadsheet.worksheet(PENDING_XP_TAB)
    prefix = "LinkedIn" if channel == "linkedin" else "Threads"
    cells = []

    def _add(col_name, value):
        col = PENDING_XP_HEADERS.index(col_name) + 1
        cells.append(gspread.Cell(row=sheet_row, col=col, value=value))

    if status is not None:
        _add(f"{prefix}_Status", status)
    if post_url is not None:
        _add(f"{prefix}_Post_URL", post_url)
    if error_message is not None:
        _add(f"{prefix}_Error", error_message)
    if last_attempted:
        _add("Last_Attempted_At_UTC", _utc_now_iso())
    if increment_retry:
        retry_col = PENDING_XP_HEADERS.index("Retry_Count") + 1
        current = worksheet.cell(sheet_row, retry_col).value
        cells.append(gspread.Cell(
            row=sheet_row, col=retry_col, value=int(current or 0) + 1
        ))

    if cells:
        worksheet.update_cells(cells, value_input_option="USER_ENTERED")


def claim_crosspost(spreadsheet, crosspost_id, channel):
    """
    Atomically claim a row for processing.

    Reads the current channel status. If still 'pending', flips to 'processing'
    and stamps Last_Attempted_At_UTC. Returns True on successful claim, False
    if another worker already claimed it (or it's no longer pending).

    Used by the Phase 2 cron to prevent double-posting under overlapping runs.
    Phase 1 post-now flow doesn't strictly need this, but routing through the
    same helper keeps behavior consistent.
    """
    if channel not in CROSS_POST_CHANNELS:
        raise ValueError(f"Unknown channel: {channel}")

    sheet_row = _row_for_crosspost(spreadsheet, crosspost_id)
    if sheet_row is None:
        return False

    worksheet = spreadsheet.worksheet(PENDING_XP_TAB)
    prefix = "LinkedIn" if channel == "linkedin" else "Threads"
    status_col = PENDING_XP_HEADERS.index(f"{prefix}_Status") + 1

    current_status = worksheet.cell(sheet_row, status_col).value
    if current_status != XP_STATUS_PENDING:
        return False

    update_crosspost_status(
        spreadsheet, crosspost_id, channel,
        status=XP_STATUS_PROCESSING, last_attempted=True,
    )
    return True


def cancel_crosspost(spreadsheet, crosspost_id, channel=None):
    """
    Cancel a pending cross-post. If channel is None, cancels both channels.

    Cancelled rows stay in the sheet for audit. The cron skips any row whose
    target channel status is not 'pending'.
    """
    channels = [channel] if channel else list(CROSS_POST_CHANNELS)
    for ch in channels:
        update_crosspost_status(
            spreadsheet, crosspost_id, ch,
            status=XP_STATUS_CANCELLED, last_attempted=False,
        )


def update_crosspost_content(
    spreadsheet, crosspost_id,
    *, linkedin_content=None, threads_content=None,
    linkedin_scheduled_at_utc=None, threads_scheduled_at_utc=None,
    substack_url=None,
):
    """
    Update the editable fields on a pending cross-post row.

    Only fields passed (not None) are updated. Used by the Pending Posts view
    to let the user fix typos or reschedule before the cron fires.
    """
    sheet_row = _row_for_crosspost(spreadsheet, crosspost_id)
    if sheet_row is None:
        return

    worksheet = spreadsheet.worksheet(PENDING_XP_TAB)
    cells = []

    def _add(col_name, value):
        col = PENDING_XP_HEADERS.index(col_name) + 1
        cells.append(gspread.Cell(row=sheet_row, col=col, value=value))

    if linkedin_content is not None:
        _add("LinkedIn_Content", linkedin_content)
    if threads_content is not None:
        _add("Threads_Content", threads_content)
    if linkedin_scheduled_at_utc is not None:
        _add("LinkedIn_Scheduled_At_UTC", linkedin_scheduled_at_utc)
    if threads_scheduled_at_utc is not None:
        _add("Threads_Scheduled_At_UTC", threads_scheduled_at_utc)
    if substack_url is not None:
        _add("Substack_URL", substack_url)

    if cells:
        worksheet.update_cells(cells, value_input_option="USER_ENTERED")


def log_crosspost_attempt(
    spreadsheet, crosspost_id, channel, *,
    result, post_url="", error_message="", was_dry_run=False,
):
    """
    Append an entry to CrossPost_Log for a fire attempt.

    Args:
        spreadsheet: The active spreadsheet
        crosspost_id: The Pending_CrossPosts row this attempt is for
        channel: "linkedin" or "threads"
        result: "posted" | "failed" | "dry_run" | "retry_scheduled"
        post_url: Returned URL on success
        error_message: Error string on failure
        was_dry_run: True if this was a dry-run pass
    """
    worksheet = spreadsheet.worksheet(XP_LOG_TAB)
    log_id = _next_id(worksheet)
    row = [
        log_id,
        crosspost_id,
        channel,
        _utc_now_iso(),
        result,
        post_url,
        error_message,
        "TRUE" if was_dry_run else "FALSE",
    ]
    worksheet.append_row(row, value_input_option="USER_ENTERED")
