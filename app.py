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
    save_draft,
    read_draft,
    clear_draft,
    batch_update_backlog_statuses,
    read_config,
    save_config,
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

# Page navigation — now includes "Cluster & Draft" for the AI workflow
page = st.sidebar.radio(
    "Navigate",
    options=["Dashboard", "Add Content", "Cluster & Draft", "Settings"],
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
    """The main dashboard with inline status editing via st.data_editor."""
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

    # --- Valid statuses for the dropdown ---
    valid_statuses = ["New", "Reviewed", "Queued", "Used", "Archived"]

    # --- Editable Data Table ---
    # st.data_editor replaces the old st.dataframe + separate status form.
    # The "disabled" parameter locks all columns EXCEPT Status.
    # The Status column becomes a dropdown (SelectboxColumn) — just click to change.
    edited_df = st.data_editor(
        filtered_df,
        key="backlog_editor",
        use_container_width=True,
        hide_index=True,
        disabled=["ID", "Date", "URL", "Reflection", "Category"],
        column_config={
            "URL": st.column_config.LinkColumn("URL"),
            "ID": st.column_config.NumberColumn("ID", width="small"),
            "Date": st.column_config.TextColumn("Date", width="medium"),
            "Reflection": st.column_config.TextColumn("Reflection", width="large"),
            "Status": st.column_config.SelectboxColumn(
                "Status",
                options=valid_statuses,
                required=True,
                help="Click to change the status of this entry.",
            ),
        },
        num_rows="fixed",
    )

    # --- Detect and Save Edits ---
    # When you change a Status cell, Streamlit tracks the change in
    # session_state["backlog_editor"]["edited_rows"]. The format is:
    #   { "0": {"Status": "Reviewed"}, "3": {"Status": "Used"} }
    # where the key is the zero-based index in the FILTERED DataFrame.
    if st.button("Save Changes", type="primary"):
        editor_state = st.session_state.get("backlog_editor", {})
        edited_rows = editor_state.get("edited_rows", {})

        if not edited_rows:
            st.info("No changes to save.")
        else:
            save_count = 0
            for row_index_str, changes in edited_rows.items():
                row_index = int(row_index_str)
                if "Status" in changes:
                    # Get the actual entry ID from the filtered DataFrame
                    entry_id = int(filtered_df.iloc[row_index]["ID"])
                    new_status = changes["Status"]
                    # Sheet row = entry ID + 1 (row 1 is the header)
                    sheet_row = entry_id + 1
                    update_backlog_status(spreadsheet, sheet_row, new_status)
                    save_count += 1

            st.success(f"Updated {save_count} entry(ies)!")
            st.cache_data.clear()
            st.rerun()


# --- Page: Cluster & Draft ---
def render_cluster_and_draft():
    """The AI-powered clustering and draft generation page.

    Workflow:
    1. Click "Cluster Links" → Gemini groups your New/Reviewed entries into topics
    2. Review clusters, uncheck any you want to skip
    3. Click "Generate Draft" → Gemini writes a newsletter draft
    4. Edit the draft sections, save to Google Sheets
    5. Come back later (even on a different device) to resume editing
    """
    st.header("Cluster & Draft")

    # --- Step 1: Clustering ---
    st.subheader("Step 1: Cluster Your Links")
    st.caption(
        "Takes all your New and Reviewed entries and groups them into "
        "topic clusters using Gemini AI."
    )

    # Load backlog data
    backlog_data = load_backlog(spreadsheet, spreadsheet.id)

    if not backlog_data:
        st.info("No entries in the backlog. Add some content first!")
        return

    df = pd.DataFrame(backlog_data)

    # Filter to only New and Reviewed entries (ready for clustering)
    clusterizable = df[df["Status"].isin(["New", "Reviewed"])]

    if clusterizable.empty:
        st.info(
            "No entries with status 'New' or 'Reviewed' to cluster. "
            "Update entry statuses on the Dashboard first."
        )
        # Still check for existing draft below
    else:
        st.write(f"**{len(clusterizable)} entries** ready for clustering.")

        # --- Cluster Button ---
        if st.button("Cluster Links", type="primary"):
            with st.spinner("Asking Gemini to find themes in your links..."):
                from gemini import cluster_entries

                entries_for_clustering = clusterizable.to_dict("records")
                clusters = cluster_entries(entries_for_clustering)

                if clusters is None:
                    st.error(
                        "Clustering failed. Check that your Gemini API key is "
                        "configured in .env (locally) or Streamlit Secrets (cloud)."
                    )
                else:
                    # Store clusters in session_state so they persist across reruns
                    st.session_state["clusters"] = clusters
                    st.session_state["cluster_entries"] = entries_for_clustering

    # --- Display Clusters (if they exist in session state) ---
    if "clusters" in st.session_state:
        clusters = st.session_state["clusters"]
        entries_lookup = {
            e["ID"]: e for e in st.session_state["cluster_entries"]
        }

        st.divider()
        st.subheader("Step 2: Review & Select Clusters")
        st.caption("Uncheck any clusters you want to skip in this issue.")

        selected_clusters = []

        for i, cluster in enumerate(clusters):
            is_selected = st.checkbox(
                f"**{cluster['cluster_name']}** — {cluster['description']}",
                value=True,
                key=f"cluster_checkbox_{i}",
            )

            if is_selected:
                selected_clusters.append(cluster)

            # Show the entries in this cluster
            with st.expander(f"View entries in '{cluster['cluster_name']}'"):
                for entry_id in cluster["entry_ids"]:
                    entry = entries_lookup.get(entry_id, {})
                    if entry:
                        st.markdown(
                            f"- **[Link]({entry.get('URL', '#')})** "
                            f"({entry.get('Category', 'N/A')})\n\n"
                            f"  {entry.get('Reflection', 'No reflection')}"
                        )

        st.session_state["selected_clusters"] = selected_clusters

        # --- Step 3: Generate Draft ---
        st.divider()
        st.subheader("Step 3: Generate Newsletter Draft")

        if not selected_clusters:
            st.info("Select at least one cluster above to generate a draft.")
        else:
            if st.button("Generate Draft", type="primary"):
                # Fetch article titles from URLs for better link formatting
                with st.spinner("Fetching article titles..."):
                    from gemini import fetch_all_titles
                    url_titles = fetch_all_titles(entries_lookup)

                with st.spinner("Gemini is writing your newsletter draft..."):
                    from gemini import generate_draft

                    draft_sections = generate_draft(
                        selected_clusters, entries_lookup, url_titles
                    )

                    if draft_sections is None:
                        st.error(
                            "Draft generation failed. Check your Gemini API key."
                        )
                    else:
                        # Auto-assemble: prepend intro, append footer from Settings
                        config = read_config(spreadsheet)
                        default_intro = config.get("default_intro", "")
                        default_footer = config.get("default_footer", "")

                        if default_intro:
                            for section in draft_sections:
                                if section["section"] == "Intro":
                                    section["content"] = (
                                        default_intro
                                        + "\n\n"
                                        + section["content"]
                                    )
                                    break

                        if default_footer:
                            draft_sections.append({
                                "section": "Footer",
                                "content": default_footer,
                            })

                        st.session_state["draft_sections"] = draft_sections
                        st.success("Draft generated! Edit it below.")

                        # Auto-update clustered entries to "Queued" status
                        all_entry_ids = []
                        for cluster in selected_clusters:
                            all_entry_ids.extend(cluster["entry_ids"])
                        batch_update_backlog_statuses(
                            spreadsheet, all_entry_ids, "Queued"
                        )
                        st.cache_data.clear()

    # --- Step 4: Edit & Save Draft ---
    # Check for an existing saved draft if we don't have one in session state.
    # This enables cross-device persistence: start on PC, finish on phone.
    if "draft_sections" not in st.session_state:
        existing_draft = read_draft(spreadsheet)
        if existing_draft:
            st.session_state["draft_sections"] = [
                {"section": row["Section"], "content": row["Content"]}
                for row in existing_draft
            ]

    if "draft_sections" in st.session_state:
        st.divider()
        st.subheader("Step 4: Edit Your Draft")
        st.caption(
            "Edit each section below. Click 'Save Draft' to persist your changes "
            "to Google Sheets — you can come back later and pick up where you left off."
        )

        draft_sections = st.session_state["draft_sections"]
        edited_sections = []

        for i, section in enumerate(draft_sections):
            st.markdown(f"### {section['section']}")
            edited_content = st.text_area(
                label=f"Edit: {section['section']}",
                value=section["content"],
                height=200,
                key=f"draft_section_{i}",
                label_visibility="collapsed",
            )
            edited_sections.append({
                "section": section["section"],
                "content": edited_content,
            })

        # --- Save, Preview, and Clear buttons ---
        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            if st.button("Save Draft", type="primary"):
                save_draft(spreadsheet, edited_sections)
                st.session_state["draft_sections"] = edited_sections
                st.success("Draft saved to Google Sheets!")

        with btn_col2:
            if st.button("Preview as Markdown"):
                st.session_state["show_preview"] = not st.session_state.get(
                    "show_preview", False
                )

        with btn_col3:
            if st.button("Clear Draft"):
                clear_draft(spreadsheet)
                for key in [
                    "draft_sections",
                    "clusters",
                    "cluster_entries",
                    "selected_clusters",
                    "show_preview",
                ]:
                    st.session_state.pop(key, None)
                st.info("Draft cleared. You can start fresh!")
                st.rerun()

        # --- Markdown Preview ---
        if st.session_state.get("show_preview", False):
            st.divider()
            st.subheader("Preview")
            full_markdown = "\n\n".join(
                section["content"] for section in edited_sections
            )
            st.markdown(full_markdown)


# --- Page: Settings ---
def render_settings():
    """Settings page for configuring newsletter defaults like intro and footer."""
    st.header("Settings")
    st.caption(
        "Configure default text that gets added to every newsletter draft. "
        "These values are saved to Google Sheets and persist across sessions."
    )

    st.info(
        "**Tip:** You can use Markdown links in these fields! "
        "Format: `[Link Text](https://url)` — for example: "
        "`[Nerd Out Gear](https://your-merch-link.com)`"
    )

    # Load existing config (no cache — this page needs fresh values after saving)
    config = read_config(spreadsheet)

    default_intro = st.text_area(
        "Default Intro",
        value=config.get("default_intro", "Happy Wednesday!"),
        height=100,
        help="This text is prepended to every new draft's Intro section.",
    )

    default_footer = st.text_area(
        "Default Footer",
        value=config.get("default_footer", ""),
        height=200,
        placeholder="Paste your recurring footer here — social links, book links, etc.",
        help="This text is appended as a Footer section at the end of every new draft.",
    )

    # Live markdown preview so users can verify their links render correctly
    if default_intro or default_footer:
        st.divider()
        st.subheader("Preview")
        if default_intro:
            st.markdown("**Intro:**")
            st.markdown(default_intro)
        if default_footer:
            st.markdown("**Footer:**")
            st.markdown(default_footer)
        st.divider()

    if st.button("Save Settings", type="primary"):
        save_config(spreadsheet, {
            "default_intro": default_intro,
            "default_footer": default_footer,
        })
        st.cache_data.clear()
        st.success("Settings saved!")


# --- Page Routing ---
# This is where we decide which page to show based on the sidebar selection.
if page == "Dashboard":
    render_dashboard()
elif page == "Add Content":
    render_ingest_form()
elif page == "Cluster & Draft":
    render_cluster_and_draft()
elif page == "Settings":
    render_settings()
