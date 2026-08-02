"""
app.py - Main Streamlit application for the Newsletter Automator.

This is the entry point. Run it with: streamlit run app.py

How Streamlit works (important for understanding this code):
- Streamlit re-runs this ENTIRE file from top to bottom every time you
  interact with any widget (click a button, change a dropdown, etc.)
- That's why we use caching (@st.cache_resource, @st.cache_data) to avoid
  re-doing expensive work (like authenticating with Google) on every rerun.
- st.session_state persists values across reruns (like a global variable
  that survives page refreshes).
"""

import json
import os
import streamlit as st
import pandas as pd
from config import get_gspread_client, get_corpus_github_config, DEFAULT_PUBLICATION
from constants import (
    APP_TITLE,
    DEFAULT_CATEGORIES,
    VALID_STATUSES,
    ALL_PAGES,
    PAGE_DASHBOARD,
    PAGE_ADD_CONTENT,
    PAGE_CLUSTER_DRAFT,
    PAGE_CROSS_POST,
    PAGE_SETTINGS,
    SECTION_INTRO,
    SECTION_FOOTER,
    SECTION_AFFILIATE,
    SK_CLUSTERS,
    SK_CLUSTER_ENTRIES,
    SK_SELECTED_CLUSTERS,
    SK_DRAFT_SECTIONS,
    SK_SECTION_ENTRY_MAP,
    SK_DRAFT_ENTRIES_LOOKUP,
    SK_DRAFT_ENTRY_IDS,
    SK_SHOW_PREVIEW,
    SK_CONFIRM_PUBLISH,
    SK_AFFILIATE_SUGGESTIONS,
    SK_AFFILIATE_BOOK_TITLES,
    SK_XP_SOURCE,
    SK_XP_SUBSTACK_URL,
    SK_XP_LINKEDIN_DRAFT,
    SK_XP_THREADS_DRAFT,
    SK_XP_FROM_EPISODE,
    SK_XP_EPISODE_ID,
    SK_XP_DRY_RUN,
    SK_XP_LAST_RESULT,
    SK_JUST_PUBLISHED,
    DRAFT_SESSION_KEYS,
    XP_SESSION_KEYS,
    THREADS_CHAR_LIMIT,
    CHANNEL_LINKEDIN,
    CHANNEL_THREADS,
)

# Navigation intent key — set by buttons to navigate on the next render
_SK_NAVIGATE_TO = "_navigate_to"

# Starter books loaded from an optional JSON file (gitignored — personal data).
# See starter_books.json.template for the expected format.
_STARTER_BOOKS_PATH = os.path.join(os.path.dirname(__file__), "starter_books.json")
if os.path.exists(_STARTER_BOOKS_PATH):
    with open(_STARTER_BOOKS_PATH, encoding="utf-8") as _f:
        STARTER_BOOKS = json.load(_f)
else:
    STARTER_BOOKS = []
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
    publish_episode,
    compute_fallback_title,
    read_book_ledger,
    add_to_book_ledger,
    update_book_ledger_entry,
    delete_book_ledger_entry,
)

# --- Page Configuration ---
# This MUST be the first Streamlit command in the file.
st.set_page_config(
    page_title=APP_TITLE,
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


@st.cache_data(ttl=60)
def load_publications(_client, _client_id="default"):
    """Cache publication list for 60 seconds — avoids re-listing spreadsheets on every rerun."""
    return list_publications(_client)


@st.cache_data(ttl=60)
def load_config(_spreadsheet, spreadsheet_id):
    """Cache config for 60 seconds — categories and settings rarely change mid-session."""
    return read_config(_spreadsheet)


@st.cache_data(ttl=30)
def load_book_ledger(_spreadsheet, spreadsheet_id):
    """Cache book ledger for 30 seconds — same pattern as load_backlog."""
    return read_book_ledger(_spreadsheet)


@st.cache_resource(ttl=300)
def ensure_tabs_cached(_spreadsheet, spreadsheet_id):
    """Ensure tabs exist, cached for 5 minutes. Tabs only need creating once."""
    ensure_tabs(_spreadsheet)
    return True  # cache_resource needs a return value


# --- Authentication ---
# This runs once and is cached. If it fails, config.py shows an error and stops.
client = get_gspread_client()

# --- Navigation Intent ---
# Buttons can't directly modify page_nav (the widget key), but they can set
# _navigate_to. We check it here and apply it to page_nav before rendering the sidebar.
if _SK_NAVIGATE_TO in st.session_state:
    st.session_state["page_nav"] = st.session_state.pop(_SK_NAVIGATE_TO)

# --- Sidebar ---
st.sidebar.title(APP_TITLE)

# Publication selector
# First, discover what publications exist (sheets ending in _DB)
available_publications = load_publications(client)

# If no publications exist yet, start with the default
if not available_publications:
    available_publications = [DEFAULT_PUBLICATION]

selected_pub = st.sidebar.selectbox(
    "Publication",
    options=available_publications,
    index=0,
    help="Each publication has its own Google Sheet database.",
)

# Page navigation. Bound via key="page_nav" so other flows can navigate
# programmatically (e.g., the post-publish "Cross-Post This Episode" button
# writes PAGE_CROSS_POST into st.session_state["page_nav"] and reruns).
if "page_nav" not in st.session_state:
    st.session_state["page_nav"] = ALL_PAGES[0]

page = st.sidebar.radio(
    "Navigate",
    options=ALL_PAGES,
    key="page_nav",
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
# Wrapped in try/except: if the Google auth token has expired (happens after ~1 hour),
# the first API call will fail. We catch that, clear the cached client so it
# re-authenticates, and retry once. This makes the app self-healing.
try:
    spreadsheet = get_or_create_spreadsheet(client, selected_pub)
    ensure_tabs_cached(spreadsheet, spreadsheet.id)
except Exception:
    st.cache_resource.clear()
    client = get_gspread_client()
    spreadsheet = get_or_create_spreadsheet(client, selected_pub)
    ensure_tabs_cached(spreadsheet, spreadsheet.id)


# --- Page: Add Content ---
def render_ingest_form():
    """The manual content ingest form — paste a URL and/or your reflection."""
    st.header("Add Content")
    st.caption(
        "Paste a URL and/or your reflection to add it to the backlog. "
        "URL is optional — you can submit a reflection-only entry."
    )

    # Load categories from config (custom categories managed in Settings)
    # Uses cached version to avoid API calls on every rerun
    config = load_config(spreadsheet, spreadsheet.id)
    cat_json = config.get("categories", "")
    categories = json.loads(cat_json) if cat_json else DEFAULT_CATEGORIES

    # st.form() batches all the inputs together. Nothing happens until you
    # click "Add to Backlog". Without a form, every keystroke would trigger
    # a full page rerun (annoying and slow).
    with st.form(key="ingest_form", clear_on_submit=True):
        url_input = st.text_input(
            "URL",
            placeholder="https://example.com/interesting-article",
            help="Optional — leave blank for reflection-only entries.",
        )

        reflection_input = st.text_area(
            "Reflection",
            placeholder="Why is this interesting? Key takeaways, your thoughts...",
            height=150,
        )

        category_input = st.selectbox("Category", options=categories)

        needs_research_input = st.checkbox(
            "I need to research this",
            help="Flags this entry for the research agent. Independent of "
            "whether a URL is present.",
        )

        submitted = st.form_submit_button("Add to Backlog", type="primary")

    if submitted:
        url_clean = url_input.strip() if url_input else ""
        reflection_clean = reflection_input.strip() if reflection_input else ""

        # Must provide at least a URL or a reflection
        if not url_clean and not reflection_clean:
            st.error("Please enter a URL, a reflection, or both.")
            return

        # If a URL is provided, validate it starts with http/https
        if url_clean and not url_clean.startswith(("http://", "https://")):
            st.error("URL must start with http:// or https://")
            return

        if url_clean and not reflection_clean:
            st.info("Tip: Adding a reflection helps you remember why you saved this!")

        # Save to Google Sheets
        success, message = add_to_backlog(
            spreadsheet, url_clean, reflection_clean, category_input,
            needs_research=needs_research_input,
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
    valid_statuses = VALID_STATUSES

    # --- Editable Data Table ---
    # st.data_editor replaces the old st.dataframe + separate status form.
    # The "disabled" parameter locks all columns EXCEPT Status.
    # The Status column becomes a dropdown (SelectboxColumn) — just click to change.
    edited_df = st.data_editor(
        filtered_df,
        key="backlog_editor",
        width="stretch",
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


# --- Page: Cluster & Draft (helper functions) ---

def _render_clustering_step(backlog_data):
    """Steps 1-2: Run Gemini clustering and display cluster checkboxes."""
    df = pd.DataFrame(backlog_data)

    # Filter to only New and Reviewed entries (ready for clustering)
    clusterizable = df[df["Status"].isin(["New", "Reviewed"])]

    if clusterizable.empty:
        st.info(
            "No entries with status 'New' or 'Reviewed' to cluster. "
            "Update entry statuses on the Dashboard first."
        )
    else:
        st.write(f"**{len(clusterizable)} entries** ready for clustering.")

        if st.button("Cluster Links", type="primary"):
            with st.spinner("Asking Gemini to find themes in your links..."):
                from gemini import cluster_entries

                entries_for_clustering = clusterizable.to_dict("records")
                clusters, error = cluster_entries(entries_for_clustering)

                if clusters is None:
                    msg = "Clustering failed."
                    if error:
                        msg += f"\n\n**Error:** `{error}`"
                    else:
                        msg += (
                            " Check that your Gemini API key is configured "
                            "in .env (locally) or Streamlit Secrets (cloud)."
                        )
                    st.error(msg)
                else:
                    st.session_state[SK_CLUSTERS] = clusters
                    st.session_state[SK_CLUSTER_ENTRIES] = entries_for_clustering

    # --- Display Clusters (if they exist in session state) ---
    if SK_CLUSTERS in st.session_state:
        clusters = st.session_state[SK_CLUSTERS]
        entries_lookup = {
            e["ID"]: e for e in st.session_state[SK_CLUSTER_ENTRIES]
        }

        st.divider()
        st.subheader("Step 2: Select Clusters & Articles")
        st.caption(
            "Check the clusters you want to include. "
            "Expand each cluster to select or deselect individual articles."
        )

        selected_clusters = []

        for i, cluster in enumerate(clusters):
            cluster_checked = st.checkbox(
                f"**{cluster['cluster_name']}** — {cluster['description']}",
                value=False,
                key=f"cluster_checkbox_{i}",
            )

            entry_count = len(cluster["entry_ids"])
            with st.expander(
                f"View entries ({entry_count} articles)"
            ):
                selected_entry_ids = []
                for entry_id in cluster["entry_ids"]:
                    entry = entries_lookup.get(entry_id, {})
                    if entry:
                        entry_checked = st.checkbox(
                            f"[{entry.get('URL', '#')}]  ({entry.get('Category', 'N/A')})",
                            value=cluster_checked,
                            key=f"entry_checkbox_{i}_{entry_id}",
                        )
                        reflection = entry.get("Reflection", "No reflection")
                        st.caption(f"  {reflection}")

                        if entry_checked:
                            selected_entry_ids.append(entry_id)

            if selected_entry_ids:
                selected_clusters.append({
                    "cluster_name": cluster["cluster_name"],
                    "description": cluster["description"],
                    "entry_ids": selected_entry_ids,
                })

        st.session_state[SK_SELECTED_CLUSTERS] = selected_clusters
        return entries_lookup
    return None


def _render_draft_generation_step(entries_lookup):
    """Step 3: Generate a newsletter draft from selected clusters."""
    selected_clusters = st.session_state.get(SK_SELECTED_CLUSTERS, [])

    st.divider()
    st.subheader("Step 3: Generate Newsletter Draft")

    if not selected_clusters:
        st.info("Select at least one cluster and article above to generate a draft.")
        return

    total_articles = sum(len(c["entry_ids"]) for c in selected_clusters)
    st.write(
        f"**{len(selected_clusters)} clusters** with "
        f"**{total_articles} articles** selected."
    )

    if st.button("Generate Draft", type="primary"):
        with st.spinner("Fetching article titles..."):
            from gemini import fetch_all_titles
            url_titles = fetch_all_titles(entries_lookup)

        with st.spinner("Gemini is writing your newsletter draft..."):
            from gemini import generate_draft

            draft_sections, error = generate_draft(
                selected_clusters, entries_lookup, url_titles
            )

            if draft_sections is None:
                msg = "Draft generation failed."
                if error:
                    msg += f"\n\n**Error:** `{error}`"
                else:
                    msg += " Check your Gemini API key."
                st.error(msg)
            else:
                # Auto-assemble: prepend intro, append footer from Settings
                config = load_config(spreadsheet, spreadsheet.id)
                default_intro = config.get("default_intro", "")
                default_footer = config.get("default_footer", "")

                if default_intro:
                    for section in draft_sections:
                        if section["section"] == SECTION_INTRO:
                            section["content"] = (
                                default_intro
                                + "\n\n"
                                + section["content"]
                            )
                            break

                if default_footer:
                    draft_sections.append({
                        "section": SECTION_FOOTER,
                        "content": default_footer,
                    })

                st.session_state[SK_DRAFT_SECTIONS] = draft_sections
                st.success("Draft generated! Edit it below.")

                section_entry_map = {
                    c["cluster_name"]: c["entry_ids"]
                    for c in selected_clusters
                }
                st.session_state[SK_SECTION_ENTRY_MAP] = section_entry_map
                st.session_state[SK_DRAFT_ENTRIES_LOOKUP] = entries_lookup

                all_entry_ids = []
                for cluster in selected_clusters:
                    all_entry_ids.extend(cluster["entry_ids"])
                st.session_state[SK_DRAFT_ENTRY_IDS] = all_entry_ids
                batch_update_backlog_statuses(
                    spreadsheet, all_entry_ids, "Queued"
                )
                st.cache_data.clear()


def _render_draft_editor():
    """Step 4: Show editable text areas for each draft section.

    Returns the list of edited sections (needed by save/publish).
    """
    st.divider()
    st.subheader("Step 4: Edit Your Draft")
    st.caption(
        "Edit each section below. Click 'Save Draft' to persist your changes "
        "to Google Sheets — you can come back later and pick up where you left off."
    )

    draft_sections = st.session_state[SK_DRAFT_SECTIONS]
    edited_sections = []

    section_entry_map = st.session_state.get(SK_SECTION_ENTRY_MAP, {})
    draft_entries = st.session_state.get(SK_DRAFT_ENTRIES_LOOKUP, {})

    for i, section in enumerate(draft_sections):
        st.markdown(f"### {section['section']}")
        edited_content = st.text_area(
            label=f"Edit: {section['section']}",
            value=section["content"],
            height=200,
            key=f"draft_section_{section['section']}",
            label_visibility="collapsed",
        )
        edited_sections.append({
            "section": section["section"],
            "content": edited_content,
        })

        # Show original reflections for reference (if mapping exists)
        entry_ids_for_section = section_entry_map.get(section["section"], [])
        if entry_ids_for_section and draft_entries:
            with st.expander(
                f"Your reflections ({len(entry_ids_for_section)} entries)"
            ):
                for eid in entry_ids_for_section:
                    entry = draft_entries.get(eid, {})
                    if entry:
                        url = entry.get("URL", "")
                        reflection = entry.get("Reflection", "No reflection")
                        if url:
                            st.markdown(f"**{url}**")
                        st.caption(reflection)
                        st.markdown("---")

    return edited_sections


def _render_affiliate_step():
    """Step 5: Suggest and insert affiliate book picks."""
    st.divider()
    st.subheader("Step 5: Affiliate Book Picks")
    st.caption(
        "Suggest a book recommendation to include in this episode. "
        "Gemini scores each book for relevance to the episode's themes, "
        "and books that haven't been used recently get a boost."
    )

    selected_clusters_for_aff = st.session_state.get(SK_SELECTED_CLUSTERS, [])

    if st.button("Suggest Affiliate Books", key="suggest_affiliate_btn"):
        aff_books = load_book_ledger(spreadsheet, spreadsheet.id)
        if not aff_books:
            st.warning(
                "No books in the Book Ledger. "
                "Add books in Settings first."
            )
        elif not selected_clusters_for_aff:
            st.warning(
                "No cluster context available. Generate a draft first "
                "so Gemini knows what topics to match against."
            )
        else:
            with st.spinner("Gemini is scoring book relevance..."):
                from gemini import suggest_affiliate_books
                suggestions, error = suggest_affiliate_books(
                    selected_clusters_for_aff, aff_books
                )

            if suggestions is None:
                msg = "Affiliate suggestion failed."
                if error:
                    msg += f"\n\n**Error:** `{error}`"
                else:
                    msg += " Check your Gemini API key."
                st.error(msg)
            else:
                # Apply recency weighting in Python
                book_meta = {b["Title"]: b for b in aff_books}
                from datetime import datetime, timedelta
                now = datetime.now()
                recency_cutoff = now - timedelta(days=60)

                for s in suggestions:
                    meta = book_meta.get(s["title"], {})
                    times_used = int(meta.get("Times_Used", 0) or 0)
                    last_used_str = str(meta.get("Last_Used", ""))

                    if times_used == 0:
                        s["recency_adj"] = 0.1
                        s["recency_flag"] = "Never used"
                    elif last_used_str:
                        try:
                            last_used_date = datetime.strptime(
                                last_used_str, "%Y-%m-%d"
                            )
                            if last_used_date > recency_cutoff:
                                s["recency_adj"] = -0.15
                                s["recency_flag"] = "Used recently"
                            else:
                                s["recency_adj"] = 0.0
                                s["recency_flag"] = "Not used recently"
                        except ValueError:
                            s["recency_adj"] = 0.0
                            s["recency_flag"] = "Unknown"
                    else:
                        s["recency_adj"] = 0.0
                        s["recency_flag"] = "Not used recently"

                    raw = float(s.get("relevance_score", 0))
                    s["final_score"] = min(1.0, max(0.0, raw + s["recency_adj"]))

                    s["store"] = meta.get("Store", "")
                    s["link"] = meta.get("Link", "")
                    s["description"] = meta.get("Description", "")
                    s["times_used"] = times_used

                suggestions.sort(key=lambda x: x["final_score"], reverse=True)
                st.session_state[SK_AFFILIATE_SUGGESTIONS] = suggestions

    # Display suggestions if they exist
    if SK_AFFILIATE_SUGGESTIONS in st.session_state:
        suggestions = st.session_state[SK_AFFILIATE_SUGGESTIONS]
        st.write(f"**{len(suggestions)} books** scored. Select 1\u20133 to include:")

        for idx, s in enumerate(suggestions):
            score_pct = int(s["final_score"] * 100)
            store_badge = f" [{s['store']}]" if s["store"] else ""
            recency_label = f" \u2014 {s['recency_flag']}"
            if s["times_used"] > 0:
                recency_label += f" ({s['times_used']}x)"

            st.checkbox(
                f"**{s['title']}**{store_badge} \u2014 "
                f"Score: {score_pct}%{recency_label}",
                value=False,
                key=f"affiliate_pick_{idx}",
            )

            with st.expander(f"Details: {s['title']}", expanded=False):
                st.caption(f"Gemini says: {s['reasoning']}")
                if s["description"]:
                    st.markdown(f"**Your blurb:** {s['description'][:200]}...")
                if s["link"]:
                    st.markdown(f"Link: {s['link']}")
                else:
                    st.caption("No affiliate link set \u2014 add one in Settings > Book Ledger")

        # Insert button
        if st.button("Insert Affiliate Section", key="insert_affiliate_btn"):
            picked = []
            for idx, s in enumerate(suggestions):
                if st.session_state.get(f"affiliate_pick_{idx}", False):
                    picked.append(s)
                if len(picked) >= 3:
                    break

            if not picked:
                st.warning("Select at least one book to insert.")
            else:
                lines = [f"## {SECTION_AFFILIATE}\n"]
                affiliate_titles = []
                for book in picked:
                    title = book["title"]
                    link = book.get("link", "")
                    desc = book.get("description", "")
                    affiliate_titles.append(title)

                    if link:
                        lines.append(f"> [{title}]({link})\n")
                    else:
                        lines.append(f"> **{title}** *(add affiliate link in Settings)*\n")
                    if desc:
                        lines.append(f"{desc}\n")

                affiliate_content = "\n".join(lines)

                sections = st.session_state[SK_DRAFT_SECTIONS]
                sections = [
                    s for s in sections
                    if s["section"] != SECTION_AFFILIATE
                ]
                footer_idx = next(
                    (i for i, s in enumerate(sections)
                     if s["section"] == SECTION_FOOTER),
                    None
                )
                new_section = {
                    "section": SECTION_AFFILIATE,
                    "content": affiliate_content,
                }
                if footer_idx is not None:
                    sections.insert(footer_idx, new_section)
                else:
                    sections.append(new_section)

                st.session_state[SK_DRAFT_SECTIONS] = sections
                st.session_state[SK_AFFILIATE_BOOK_TITLES] = affiliate_titles
                st.success(
                    f"Inserted {len(picked)} book(s) as 'Affiliate Picks' section!"
                )
                st.rerun()


def _render_draft_actions(edited_sections):
    """Step 6: Save, Preview, Clear, and Publish buttons."""
    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

    with btn_col1:
        if st.button("Save Draft", type="primary"):
            save_draft(spreadsheet, edited_sections)
            st.session_state[SK_DRAFT_SECTIONS] = edited_sections
            st.success("Draft saved to Google Sheets!")

    with btn_col2:
        if st.button("Preview as Markdown"):
            st.session_state[SK_SHOW_PREVIEW] = not st.session_state.get(
                SK_SHOW_PREVIEW, False
            )

    with btn_col3:
        if st.button("Clear Draft"):
            clear_draft(spreadsheet)
            for key in DRAFT_SESSION_KEYS:
                st.session_state.pop(key, None)
            st.info("Draft cleared. You can start fresh!")
            st.rerun()

    with btn_col4:
        draft_entry_ids = st.session_state.get(SK_DRAFT_ENTRY_IDS, [])
        if st.button(
            "Publish",
            help="Mark entries as Used, record the episode, and clear the draft."
            if draft_entry_ids else
            "Record the episode and clear the draft. No backlog entries to "
            "mark \u2014 this is a freehand episode.",
        ):
            st.session_state[SK_CONFIRM_PUBLISH] = True

    # --- Publish Confirmation ---
    if st.session_state.get(SK_CONFIRM_PUBLISH, False):
        episode_title = st.text_input(
            "Episode title",
            key="publish_episode_title",
            help="The real title. Used for the archive filename and Published_Episodes.",
        )
        if not episode_title or not episode_title.strip():
            st.warning(
                "Title is blank — will fall back to "
                f"**\"{compute_fallback_title(edited_sections)}\"** for the "
                "archive filename and Published_Episodes."
            )

        aff_titles = st.session_state.get(SK_AFFILIATE_BOOK_TITLES, [])
        aff_note = ""
        if aff_titles:
            aff_note = (
                f" Affiliate book(s) will be tracked: "
                f"**{', '.join(aff_titles)}**."
            )
        st.warning(
            "Are you sure you want to publish? This will mark all included "
            f"entries as **Used** and record the episode.{aff_note}"
        )
        conf_col1, conf_col2 = st.columns(2)
        with conf_col1:
            if st.button("Yes, Publish"):
                # Capture the source for the cross-post handoff BEFORE we clear
                # draft state. We use the Intro section if present (typically
                # the most cross-post-worthy hook) and fall back to the full
                # concatenated draft.
                intro_section = next(
                    (s["content"] for s in edited_sections
                     if s["section"] == SECTION_INTRO),
                    "",
                )
                full_text = "\n\n".join(s["content"] for s in edited_sections)
                source_for_xp = intro_section or full_text

                episode_id = publish_episode(
                    spreadsheet,
                    edited_sections,
                    st.session_state.get(SK_DRAFT_ENTRY_IDS, []),
                    affiliate_book_titles=st.session_state.get(
                        SK_AFFILIATE_BOOK_TITLES, []
                    ),
                    episode_title=episode_title,
                    section_entry_map=st.session_state.get(SK_SECTION_ENTRY_MAP, {}),
                    corpus_github=get_corpus_github_config(),
                )
                for key in DRAFT_SESSION_KEYS:
                    st.session_state.pop(key, None)
                # Flash payload for the post-publish "Cross-Post This Episode"
                # handoff. Read once on the next render of Cluster & Draft.
                st.session_state[SK_JUST_PUBLISHED] = {
                    "episode_id": episode_id,
                    "source_content": source_for_xp,
                }
                st.cache_data.clear()
                st.rerun()
        with conf_col2:
            if st.button("Cancel"):
                st.session_state.pop(SK_CONFIRM_PUBLISH, None)
                st.rerun()

    # --- Markdown Preview ---
    if st.session_state.get(SK_SHOW_PREVIEW, False):
        st.divider()
        st.subheader("Preview")
        full_markdown = "\n\n".join(
            section["content"] for section in edited_sections
        )
        st.markdown(full_markdown)


# --- Page: Cluster & Draft (main coordinator) ---
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

    # --- Post-publish flash: offer Cross-Post handoff once ---
    just_pub = st.session_state.get(SK_JUST_PUBLISHED)
    if just_pub:
        st.success(
            f"Published episode #{just_pub['episode_id']}! "
            "Entries marked as Used."
        )
        with st.container(border=True):
            st.markdown(
                "**Cross-post this episode to LinkedIn and Threads?** "
                "We'll pre-fill the source content. You'll add the Substack URL "
                "after you publish on Substack."
            )
            if st.button("Cross-Post This Episode", type="primary",
                         key="xp_handoff_btn"):
                st.session_state[SK_XP_SOURCE] = just_pub["source_content"]
                st.session_state[SK_XP_EPISODE_ID] = just_pub["episode_id"]
                st.session_state[SK_XP_FROM_EPISODE] = True
                st.session_state[SK_XP_SUBSTACK_URL] = ""
                # Clear any leftover preview drafts from a prior session
                st.session_state.pop(SK_XP_LINKEDIN_DRAFT, None)
                st.session_state.pop(SK_XP_THREADS_DRAFT, None)
                st.session_state.pop(SK_XP_LAST_RESULT, None)
                st.session_state.pop(SK_JUST_PUBLISHED, None)
                st.session_state[_SK_NAVIGATE_TO] = PAGE_CROSS_POST
                st.rerun()
            if st.button("Dismiss", key="xp_dismiss_btn"):
                st.session_state.pop(SK_JUST_PUBLISHED, None)
                st.rerun()

    # --- Step 1: Clustering ---
    st.subheader("Step 1: Cluster Your Links")
    st.caption(
        "Takes all your New and Reviewed entries and groups them into "
        "topic clusters using Gemini AI."
    )

    backlog_data = load_backlog(spreadsheet, spreadsheet.id)

    if not backlog_data:
        st.info("No entries in the backlog. Add some content first!")
        return

    entries_lookup = _render_clustering_step(backlog_data)

    if entries_lookup and SK_SELECTED_CLUSTERS in st.session_state:
        _render_draft_generation_step(entries_lookup)

    # --- Step 4: Edit & Save Draft ---
    # Check for an existing saved draft if we don't have one in session state.
    # This enables cross-device persistence: start on PC, finish on phone.
    if SK_DRAFT_SECTIONS not in st.session_state:
        existing_draft = read_draft(spreadsheet)
        if existing_draft:
            st.session_state[SK_DRAFT_SECTIONS] = [
                {"section": row["Section"], "content": row["Content"]}
                for row in existing_draft
            ]

    if SK_DRAFT_SECTIONS in st.session_state:
        edited_sections = _render_draft_editor()
        _render_affiliate_step()
        _render_draft_actions(edited_sections)


# --- Page: Settings (helper functions) ---

def _render_boilerplate_settings():
    """Boilerplate settings: intro, footer, categories, and save button."""
    st.caption(
        "Configure default text that gets added to every newsletter draft. "
        "These values are saved to Google Sheets and persist across sessions."
    )

    st.info(
        "**Tip:** You can use Markdown links in these fields! "
        "Format: `[Link Text](https://url)` — for example: "
        "`[Nerd Out Gear](https://your-merch-link.com)`"
    )

    config = load_config(spreadsheet, spreadsheet.id)

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

    # --- Manage Categories ---
    st.divider()
    st.subheader("Manage Categories")
    st.caption("Add, remove, or reorder the categories used in the Add Content form.")

    cat_json = config.get("categories", "")
    current_categories = json.loads(cat_json) if cat_json else list(DEFAULT_CATEGORIES)

    for i, cat in enumerate(current_categories):
        cat_col1, cat_col2 = st.columns([4, 1])
        with cat_col1:
            st.write(cat)
        with cat_col2:
            if st.button("\u274c", key=f"del_cat_{i}"):
                current_categories.pop(i)
                full_config = load_config(spreadsheet, spreadsheet.id)
                full_config["categories"] = json.dumps(current_categories)
                save_config(spreadsheet, full_config)
                st.cache_data.clear()
                st.rerun()

    new_cat_col1, new_cat_col2 = st.columns([3, 1])
    with new_cat_col1:
        new_cat = st.text_input("New category", key="new_cat_input",
                                placeholder="e.g., Health, Design, Education")
    with new_cat_col2:
        st.write("")  # Spacer to align button
        if st.button("Add", key="add_cat_btn"):
            if new_cat and new_cat.strip():
                clean_cat = new_cat.strip()
                if clean_cat not in current_categories:
                    current_categories.append(clean_cat)
                    full_config = load_config(spreadsheet, spreadsheet.id)
                    full_config["categories"] = json.dumps(current_categories)
                    save_config(spreadsheet, full_config)
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.warning(f"'{clean_cat}' already exists.")

    st.divider()

    if st.button("Save Settings", type="primary"):
        save_config(spreadsheet, {
            "default_intro": default_intro,
            "default_footer": default_footer,
            "categories": json.dumps(current_categories),
        })
        st.cache_data.clear()
        st.success("Settings saved!")

def _render_book_ledger():
    """Book Ledger management: view, edit, delete, add, and import books."""
    st.divider()
    st.header("Book Ledger")
    st.caption(
        "Manage your affiliate book recommendations. These books are suggested "
        "during draft generation based on relevance to the episode's topics. "
        "Last Used and Times Used are updated automatically when you publish."
    )

    books = load_book_ledger(spreadsheet, spreadsheet.id)

    if books:
        books_df = pd.DataFrame(books)

        # Ensure all expected columns exist (handles migration edge cases)
        for col in ["Description", "Store"]:
            if col not in books_df.columns:
                books_df[col] = ""

        edited_books = st.data_editor(
            books_df,
            key="book_ledger_editor",
            width="stretch",
            hide_index=True,
            disabled=["Last_Used", "Times_Used"],
            column_config={
                "Title": st.column_config.TextColumn("Title", width="medium"),
                "Link": st.column_config.LinkColumn("Affiliate Link", width="medium"),
                "Categories": st.column_config.TextColumn("Category", width="small"),
                "Description": st.column_config.TextColumn("Blurb", width="large"),
                "Store": st.column_config.SelectboxColumn(
                    "Store",
                    options=["", "AZ", "BS"],
                    help="AZ = Amazon, BS = Bookstore.org",
                    width="small",
                ),
                "Last_Used": st.column_config.TextColumn(
                    "Last Used", width="small",
                ),
                "Times_Used": st.column_config.NumberColumn(
                    "Times Used", width="small",
                ),
            },
            num_rows="fixed",
        )

        # Save book edits
        book_col1, book_col2 = st.columns(2)
        with book_col1:
            if st.button("Save Book Changes", key="save_books_btn"):
                editor_state = st.session_state.get("book_ledger_editor", {})
                edited_rows = editor_state.get("edited_rows", {})

                if not edited_rows:
                    st.info("No book changes to save.")
                else:
                    save_count = 0
                    for row_index_str, changes in edited_rows.items():
                        row_index = int(row_index_str)
                        # Sheet row = DataFrame index + 2 (row 1 = headers)
                        sheet_row = row_index + 2
                        update_book_ledger_entry(spreadsheet, sheet_row, changes)
                        save_count += 1
                    st.success(f"Updated {save_count} book(s)!")
                    st.cache_data.clear()
                    st.rerun()

        with book_col2:
            # Delete selected book
            book_titles_for_delete = ["(select a book)"] + [
                b.get("Title", f"Row {i}") for i, b in enumerate(books)
            ]
            delete_selection = st.selectbox(
                "Delete a book",
                options=book_titles_for_delete,
                key="delete_book_select",
                label_visibility="collapsed",
            )
            if st.button("Delete Selected Book", key="delete_book_btn"):
                if delete_selection != "(select a book)":
                    # Find the index of this book
                    idx = book_titles_for_delete.index(delete_selection) - 1
                    sheet_row = idx + 2  # +2 for header
                    delete_book_ledger_entry(spreadsheet, sheet_row)
                    st.success(f"Deleted '{delete_selection}'")
                    st.cache_data.clear()
                    st.rerun()
    else:
        st.info("No books in the ledger yet. Add one below or import starter books.")

    # --- Add a single book ---
    with st.expander("Add a Book"):
        with st.form(key="add_book_form", clear_on_submit=True):
            book_title = st.text_input("Title", placeholder="e.g., Atomic Habits")
            book_link = st.text_input(
                "Affiliate Link", placeholder="https://amzn.to/..."
            )
            book_category = st.text_input(
                "Category", placeholder="e.g., Leadership, AI, Philosophy"
            )
            book_store = st.selectbox(
                "Store", options=["", "AZ", "BS"],
                help="AZ = Amazon, BS = Bookstore.org"
            )
            book_description = st.text_area(
                "Description / Blurb",
                placeholder="Your personal recommendation text...",
                height=100,
            )
            if st.form_submit_button("Add Book", type="primary"):
                if book_title:
                    success, msg = add_to_book_ledger(
                        spreadsheet, book_title.strip(), book_link.strip(),
                        book_category.strip(), book_description.strip(),
                        book_store,
                    )
                    if success:
                        st.success(msg)
                        st.cache_data.clear()
                    else:
                        st.warning(msg)
                else:
                    st.error("Title is required.")

    # --- Import starter books from JSON file ---
    with st.expander("Import Starter Books"):
        if not STARTER_BOOKS:
            st.info(
                "No `starter_books.json` found. To enable bulk import, create one "
                "in the project root. See `starter_books.json.template` for the format."
            )
        else:
            st.caption(
                f"Import {len(STARTER_BOOKS)} pre-configured books. Titles, categories, "
                "descriptions, and store indicators are pre-filled. **You'll need to "
                "paste in the actual affiliate URLs** via the edit table above after importing."
            )

            preview_df = pd.DataFrame(STARTER_BOOKS)[
                ["Title", "Categories", "Store"]
            ]
            st.dataframe(preview_df, hide_index=True, width=600)

            if st.button("Import All Starter Books", key="import_starter_btn"):
                added = 0
                skipped = 0
                for book in STARTER_BOOKS:
                    success, _ = add_to_book_ledger(
                        spreadsheet,
                        book["Title"], book["Link"], book["Categories"],
                        book["Description"], book["Store"],
                    )
                    if success:
                        added += 1
                    else:
                        skipped += 1
                st.success(
                    f"Imported {added} books! "
                    + (f"({skipped} skipped as duplicates)" if skipped else "")
                )
                st.cache_data.clear()
                st.rerun()


# --- Page: Settings (main coordinator) ---
def render_settings():
    """Settings page for configuring newsletter defaults and book ledger."""
    st.header("Settings")
    _render_boilerplate_settings()
    _render_book_ledger()


# --- Page: Cross-Post -------------------------------------------------------


def _render_threads_char_counter(content):
    """Show per-segment char counts for a Threads draft, with over-limit warnings."""
    from cross_post import split_threads_content
    segments = split_threads_content(content)
    if not segments:
        st.caption(f"0 / {THREADS_CHAR_LIMIT} chars")
        return
    if len(segments) == 1:
        n = len(segments[0])
        if n > THREADS_CHAR_LIMIT:
            st.error(
                f"{n} / {THREADS_CHAR_LIMIT} chars — over the limit "
                f"by {n - THREADS_CHAR_LIMIT}. Threads will reject this."
            )
        else:
            st.caption(f"{n} / {THREADS_CHAR_LIMIT} chars")
        return
    # Multi-segment thread
    rows = []
    any_over = False
    for i, seg in enumerate(segments, 1):
        n = len(seg)
        marker = "❗" if n > THREADS_CHAR_LIMIT else "✓"
        any_over = any_over or (n > THREADS_CHAR_LIMIT)
        rows.append(f"{marker} Segment {i}: {n} / {THREADS_CHAR_LIMIT}")
    summary = " · ".join(rows)
    if any_over:
        st.error(f"Thread of {len(segments)}: {summary}")
    else:
        st.caption(f"Thread of {len(segments)}: {summary}")


def render_cross_post():
    """Cross-Post page: draft, preview, edit, and post to LinkedIn + Threads."""
    st.header("Cross-Post")
    st.caption(
        "Draft LinkedIn and Threads posts in Alyn's voice from any source "
        "content (a newsletter excerpt, an article, or a raw idea). "
        "Phase 1: post immediately. Scheduling lands in Phase 2."
    )

    from_episode = st.session_state.get(SK_XP_FROM_EPISODE, False)
    if from_episode:
        st.info(
            f"Set up from episode #{st.session_state.get(SK_XP_EPISODE_ID, '?')}. "
            "Paste your Substack URL below — it's required for episode "
            "cross-posts so the post can link back to the published piece."
        )

    # --- Source content + Substack URL ---
    # Bind text widgets directly to the SK_XP_* keys via `key=` so that other
    # flows (the post-publish handoff) can set values via st.session_state and
    # have them appear in the widget on the next render.
    if SK_XP_SOURCE not in st.session_state:
        st.session_state[SK_XP_SOURCE] = ""
    if SK_XP_SUBSTACK_URL not in st.session_state:
        st.session_state[SK_XP_SUBSTACK_URL] = ""

    source = st.text_area(
        "Source content",
        height=180,
        key=SK_XP_SOURCE,
        placeholder="Paste a newsletter excerpt, article, or raw idea here...",
    )

    substack_url = st.text_input(
        "Substack URL" + (" (required)" if from_episode else " (optional)"),
        key=SK_XP_SUBSTACK_URL,
        placeholder="https://yournewsletter.substack.com/p/your-post-slug",
        help=(
            "Required when cross-posting an episode — the post needs to "
            "link back. Optional for ad-hoc posts."
            if from_episode else
            "Optional. If provided, LinkedIn appends 'Full post: <url>' and "
            "Threads will fit the URL in its 500-char budget."
        ),
    )

    # --- Generate Previews ---
    gen_col, dry_col = st.columns([2, 1])
    with gen_col:
        if st.button(
            "Generate Previews", type="primary", key="xp_generate_btn",
            disabled=not source.strip(),
            help="Asks Gemini to draft both posts in kinney-voice.",
        ):
            from gemini import generate_linkedin_preview, generate_threads_preview
            with st.spinner("Drafting LinkedIn post..."):
                li_text, li_err = generate_linkedin_preview(
                    source.strip(), substack_url.strip(),
                )
            with st.spinner("Drafting Threads post..."):
                th_text, th_err = generate_threads_preview(
                    source.strip(), substack_url.strip(),
                )
            if li_text is None or th_text is None:
                msg = "Preview generation failed."
                err = li_err or th_err
                if err:
                    msg += f"\n\n**Error:** `{err}`"
                else:
                    msg += " Check that GEMINI_API_KEY is configured."
                st.error(msg)
            else:
                st.session_state[SK_XP_LINKEDIN_DRAFT] = li_text
                st.session_state[SK_XP_THREADS_DRAFT] = th_text
                st.session_state.pop(SK_XP_LAST_RESULT, None)
                st.success("Previews ready. Edit below, then Post Now.")
    with dry_col:
        dry_run = st.toggle(
            "Dry run",
            value=st.session_state.get(SK_XP_DRY_RUN, True),
            key="xp_dry_run_toggle",
            help=(
                "ON: log the would-be payload but don't actually post. "
                "Use this until you've finished OAuth setup."
            ),
        )
        st.session_state[SK_XP_DRY_RUN] = dry_run

    # --- Editable Previews ---
    li_draft = st.session_state.get(SK_XP_LINKEDIN_DRAFT)
    th_draft = st.session_state.get(SK_XP_THREADS_DRAFT)

    if li_draft is not None or th_draft is not None:
        st.divider()
        st.subheader("Edit Previews")

        li_col, th_col = st.columns(2)

        with li_col:
            st.markdown("**LinkedIn**")
            li_edited = st.text_area(
                "LinkedIn post",
                height=320,
                key=SK_XP_LINKEDIN_DRAFT,
                label_visibility="collapsed",
            )
            words = len([w for w in li_edited.split() if w.strip()])
            st.caption(f"{words} words · {len(li_edited)} chars")

        with th_col:
            st.markdown("**Threads**")
            th_edited = st.text_area(
                "Threads post",
                height=320,
                key=SK_XP_THREADS_DRAFT,
                label_visibility="collapsed",
                help=(
                    f"Hard cap: {THREADS_CHAR_LIMIT} chars per segment. Use "
                    "'---THREAD---' on its own line to split into a thread."
                ),
            )
            _render_threads_char_counter(th_edited)

        # --- Post Now ---
        st.divider()

        # Hard gate: episode flow requires Substack URL
        gate_blocked = from_episode and not substack_url.strip()
        if gate_blocked:
            st.warning(
                "Substack URL is required to cross-post an episode. "
                "Paste it above to enable Post Now."
            )

        # Threads hard limit gate
        from cross_post import threads_segments_within_limit
        threads_ok, _ = threads_segments_within_limit(th_edited)
        if not threads_ok:
            st.warning(
                "One or more Threads segments exceed the 500-char limit. "
                "Edit the post until the counter goes green."
            )

        post_disabled = (
            gate_blocked
            or not threads_ok
            or not (li_edited.strip() or th_edited.strip())
        )

        post_col, reset_col = st.columns([2, 1])
        with post_col:
            mode_label = "Post Now (Dry Run)" if dry_run else "Post Now"
            if st.button(
                mode_label, type="primary", key="xp_post_now_btn",
                disabled=post_disabled,
            ):
                from cross_post import post_now
                with st.spinner("Posting..."):
                    result = post_now(
                        spreadsheet,
                        source_content=source.strip(),
                        substack_url=substack_url.strip(),
                        linkedin_content=li_edited.strip(),
                        threads_content=th_edited.strip(),
                        episode_id=str(
                            st.session_state.get(SK_XP_EPISODE_ID, "")
                        ),
                        dry_run=dry_run,
                    )
                st.session_state[SK_XP_LAST_RESULT] = result

        with reset_col:
            if st.button("Reset", key="xp_reset_btn"):
                for key in XP_SESSION_KEYS:
                    st.session_state.pop(key, None)
                st.rerun()

    # --- Last Post Result ---
    last_result = st.session_state.get(SK_XP_LAST_RESULT)
    if last_result:
        st.divider()
        st.subheader(f"Last attempt (CrossPost #{last_result['crosspost_id']})")
        for channel, outcome in last_result["channels"].items():
            label = "LinkedIn" if channel == CHANNEL_LINKEDIN else "Threads"
            status = outcome["status"]
            if status == "posted":
                if outcome["url"].startswith("[DRY RUN"):
                    st.info(f"**{label}:** dry-run logged — `{outcome['url']}`")
                else:
                    st.success(f"**{label}:** posted — [view post]({outcome['url']})")
            elif status == "failed":
                st.error(f"**{label}:** failed — {outcome['error']}")
            elif status == "skipped":
                st.caption(f"**{label}:** skipped (no content)")


# --- Page Routing ---
# This is where we decide which page to show based on the sidebar selection.
if page == PAGE_DASHBOARD:
    render_dashboard()
elif page == PAGE_ADD_CONTENT:
    render_ingest_form()
elif page == PAGE_CLUSTER_DRAFT:
    render_cluster_and_draft()
elif page == PAGE_CROSS_POST:
    render_cross_post()
elif page == PAGE_SETTINGS:
    render_settings()
