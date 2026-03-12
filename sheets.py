"""
sheets.py - Google Sheets CRUD operations.

This module is the "data layer" of the app. It handles all reading and writing
to Google Sheets. The Streamlit UI (app.py) calls these functions instead of
talking to Google Sheets directly. This separation makes the code easier to
understand, test, and modify.

Think of Google Sheets as a simple database with tabs (worksheets) as tables
and rows as records.
"""

from datetime import datetime
import gspread


# --- Tab Definitions ---
# Each tab is like a database table. These constants define the tab names
# and their column headers. If you need to add a column later, add it here.

BACKLOG_TAB = "Inbound_Backlog"
BACKLOG_HEADERS = ["ID", "Date", "URL", "Reflection", "Category", "Status"]

BOOK_TAB = "Book_Ledger"
BOOK_HEADERS = ["Title", "Link", "Categories", "Last_Used", "Times_Used"]

DRAFT_TAB = "Draft_State"
DRAFT_HEADERS = ["Section", "Content", "Last_Modified"]

# All tabs and their headers, grouped for easy iteration
ALL_TABS = {
    BACKLOG_TAB: BACKLOG_HEADERS,
    BOOK_TAB: BOOK_HEADERS,
    DRAFT_TAB: DRAFT_HEADERS,
}


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


def add_to_backlog(spreadsheet, url, reflection, category):
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

    Returns:
        A tuple of (success: bool, message: str)
        - (True, "Added entry #5") on success
        - (False, "URL already exists in row 3") if it's a duplicate
    """
    worksheet = spreadsheet.worksheet(BACKLOG_TAB)

    # Check for duplicates by searching the URL column (column 3)
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

    row = [next_id, date_str, url, reflection, category, status]

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


def add_to_book_ledger(spreadsheet, title, link, categories):
    """
    Adds a book/resource to the Book_Ledger, after checking for duplicates.

    Deduplicates by the Link column (column 2).

    Returns:
        A tuple of (success: bool, message: str)
    """
    worksheet = spreadsheet.worksheet(BOOK_TAB)

    # Check for duplicate links
    try:
        cell = worksheet.find(link, in_column=2)
        if cell:
            return (False, f"This link already exists (row {cell.row}). Skipping.")
    except gspread.exceptions.CellNotFound:
        pass

    date_str = datetime.now().strftime("%Y-%m-%d")
    row = [title, link, categories, date_str, 0]  # Times_Used starts at 0

    worksheet.append_row(row, value_input_option="USER_ENTERED")
    return (True, f"Added '{title}' to the Book Ledger.")


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

    # Clear existing draft data (keep the header row)
    all_values = worksheet.get_all_values()
    if len(all_values) > 1:
        last_row = len(all_values)
        worksheet.batch_clear([f"A2:C{last_row}"])

    # Write the new sections
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for section in sections:
        rows.append([section["section"], section["content"], timestamp])

    if rows:
        worksheet.update(
            rows, f"A2:C{1 + len(rows)}", value_input_option="USER_ENTERED"
        )


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
    all_values = worksheet.get_all_values()
    if len(all_values) > 1:
        last_row = len(all_values)
        worksheet.batch_clear([f"A2:C{last_row}"])


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
