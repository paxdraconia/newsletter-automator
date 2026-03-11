"""
app.py - Main Streamlit application for the Nerd Out Automator.

This is the entry point. Run it with: streamlit run app.py

How Streamlit works (important for understanding this code):
- Streamlit re-runs this ENTIRE file from top to bottom every time you
  interact with any widget (click a button, change a dropdown, etc.)
- That's why we use caching (@st.cache_resource, @st.cache_data) to avoid
  re-doing expensive work (like authenticating with Google) on every rerun.
- st.session_state persists values across reruns (like a global variable
  that survives page refreshes).
"""

import streamlit as st
import pandas as pd
from config import get_gspread_client, DEFAULT_PUBLICATION
from sheets import (
    get_or_create_spreadsheet,
    ensure_tabs,
    read_backlog,
    add_to_backlog,
    update_backlog_status,
    list_publications,
)

# --- Page Configuration ---
# This MUST be the first Streamlit command in the file.
st.set_page_config(
    page_title="Nerd Out Automator",
    page_icon="📰",
    layout="wide",
)


# --- Cached Data Loading ---
# The underscore prefix (_spreadsheet) tells Streamlit "don't try to hash this
# parameter" — gspread objects can't be hashed. We pass spreadsheet_id as the
# actual cache key instead.
@st.cache_data(ttl=30)
def load_backlog(_spreadsheet, spreadsheet_id):
    """Load backlog data with a 30-second cache to avoid hitting the API too often."""
    return read_backlog(_spreadsheet)


# --- Authentication ---
# This runs once and is cached. If it fails, config.py shows an error and stops.
client = get_gspread_client()


# --- Sidebar ---
st.sidebar.title("Nerd Out Automator")

# Publication selector
# First, discover what publications exist (sheets ending in _DB)
available_publications = list_publications(client)

# If no publications exist yet, start with the default
if not available_publications:
    available_publications = [DEFAULT_PUBLICATION]

selected_pub = st.sidebar.selectbox(
    "Publication",
    options=available_publications,
    index=0,
    help="Each publication has its own Google Sheet database.",
)

# Page navigation
page = st.sidebar.radio(
    "Navigate",
    options=["Dashboard", "Add Content"],
    index=0,
)

# Manage Publications (expandable section in sidebar)
with st.sidebar.expander("Manage Publications"):
    new_pub_name = st.text_input(
        "New Publication Name",
        placeholder="e.g., TechDigest",
        help="Letters, numbers, and underscores only.",
    )
    if st.button("Create Publication"):
        if new_pub_name:
            # Clean the name: remove spaces, keep alphanumeric + underscore
            clean_name = "".join(
                c if c.isalnum() or c == "_" else "" for c in new_pub_name
            )
            if clean_name:
                get_or_create_spreadsheet(client, clean_name)
                ensure_tabs(get_or_create_spreadsheet(client, clean_name))
                st.sidebar.success(f"Created '{clean_name}_DB'!")
                # Clear caches so the dropdown refreshes
                st.cache_data.clear()
                st.rerun()
            else:
                st.sidebar.error("Name must contain letters or numbers.")
        else:
            st.sidebar.error("Please enter a name.")


# --- Initialize the selected publication's sheet ---
spreadsheet = get_or_create_spreadsheet(client, selected_pub)
ensure_tabs(spreadsheet)


# --- Page: Add Content ---
def render_ingest_form():
    """The manual content ingest form — paste a URL and your reflection."""
    st.header("Add Content")
    st.caption(
        "Paste a URL and your reflection to add it to the backlog. "
        "The app will check for duplicates automatically."
    )

    # st.form() batches all the inputs together. Nothing happens until you
    # click "Add to Backlog". Without a form, every keystroke would trigger
    # a full page rerun (annoying and slow).
    with st.form(key="ingest_form", clear_on_submit=True):
        url_input = st.text_input(
            "URL",
            placeholder="https://example.com/interesting-article",
        )

        reflection_input = st.text_area(
            "Reflection",
            placeholder="Why is this interesting? Key takeaways, your thoughts...",
            height=150,
        )

        # Predefined categories for consistency. You can add more here later.
        categories = [
            "Tech",
            "Science",
            "Culture",
            "Business",
            "AI/ML",
            "Programming",
            "L&D",
            "Fun",
            "Other",
        ]
        category_input = st.selectbox("Category", options=categories)

        submitted = st.form_submit_button("Add to Backlog", type="primary")

    if submitted:
        # Validate the URL
        if not url_input or not url_input.strip().startswith(("http://", "https://")):
            st.error("Please enter a valid URL starting with http:// or https://")
            return

        url_clean = url_input.strip()
        reflection_clean = reflection_input.strip()

        if not reflection_clean:
            st.info("Tip: Adding a reflection helps you remember why you saved this!")

        # Save to Google Sheets
        success, message = add_to_backlog(
            spreadsheet, url_clean, reflection_clean, category_input
        )

        if success:
            st.success(message)
            # Clear the cache so the dashboard shows the new entry immediately
            st.cache_data.clear()
        else:
            st.warning(message)


# --- Page: Dashboard ---
def render_dashboard():
    """The main dashboard showing the Inbound Backlog with filters and metrics."""
    st.header(f"Dashboard: {selected_pub}")

    # Load data (cached for 30 seconds to avoid hammering the API)
    backlog_data = load_backlog(spreadsheet, spreadsheet.id)

    if not backlog_data:
        st.info(
            "No entries in the backlog yet. "
            "Go to **Add Content** in the sidebar to get started!"
        )
        return

    # Convert to a pandas DataFrame for easy filtering and display
    df = pd.DataFrame(backlog_data)

    # --- Filters ---
    col1, col2 = st.columns(2)

    with col1:
        all_statuses = df["Status"].unique().tolist()
        status_filter = st.multiselect(
            "Filter by Status",
            options=all_statuses,
            default=all_statuses,
        )

    with col2:
        all_categories = df["Category"].unique().tolist()
        category_filter = st.multiselect(
            "Filter by Category",
            options=all_categories,
            default=all_categories,
        )

    # Apply filters
    filtered_df = df[
        (df["Status"].isin(status_filter)) & (df["Category"].isin(category_filter))
    ]

    # --- Metrics ---
    met1, met2, met3 = st.columns(3)
    met1.metric("Total Entries", len(df))
    met2.metric("Showing", len(filtered_df))
    met3.metric("New", len(df[df["Status"] == "New"]))

    # --- Data Table ---
    st.dataframe(
        filtered_df,
        use_container_width=True,
        column_config={
            "URL": st.column_config.LinkColumn("URL"),
            "ID": st.column_config.NumberColumn("ID", width="small"),
            "Date": st.column_config.TextColumn("Date", width="medium"),
            "Reflection": st.column_config.TextColumn("Reflection", width="large"),
        },
        hide_index=True,
    )

    # --- Status Updater ---
    st.divider()
    st.subheader("Update Entry Status")
    st.caption(
        "Change an entry's status as you work through your backlog. "
        "The ID is shown in the table above."
    )

    with st.form("status_update_form"):
        update_col1, update_col2 = st.columns(2)

        with update_col1:
            row_id = st.number_input("Entry ID", min_value=1, step=1)

        with update_col2:
            new_status = st.selectbox(
                "New Status",
                options=["New", "Reviewed", "Queued", "Used", "Archived"],
            )

        update_submitted = st.form_submit_button("Update Status")

    if update_submitted:
        # The actual row in the sheet = ID + 1 (because row 1 is the header)
        row_number = int(row_id) + 1
        update_backlog_status(spreadsheet, row_number, new_status)
        st.success(f"Updated entry #{row_id} to '{new_status}'")
        st.cache_data.clear()
        st.rerun()


# --- Page Routing ---
# This is where we decide which page to show based on the sidebar selection.
if page == "Dashboard":
    render_dashboard()
elif page == "Add Content":
    render_ingest_form()
