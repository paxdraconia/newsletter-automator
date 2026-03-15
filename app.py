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

import json
import streamlit as st
import pandas as pd
from config import get_gspread_client, DEFAULT_PUBLICATION

# Default categories — used as a fallback when no custom categories are saved.
DEFAULT_CATEGORIES = [
    "Tech", "Science", "Culture", "Business", "AI/ML",
    "Programming", "L&D", "Fun", "Other",
]

# Starter books from the Nerd Out Affiliate Links PDF.
# Link fields are placeholders — update with your actual affiliate URLs
# via the Book Ledger UI in Settings after importing.
STARTER_BOOKS = [
    {
        "Title": "Design For How People Learn",
        "Link": "",
        "Categories": "Philosophy",
        "Description": "If you work in L&D this is a must read book. This book contains actionable research to reach people and help them learn regardless of the modality. I personally enjoy the chapters on learning evaluation.",
        "Store": "AZ",
    },
    {
        "Title": "Make It Stick: The Science of Successful Learning",
        "Link": "",
        "Categories": "Philosophy",
        "Description": "This book is targeted at the learner but for those of us in L&D it can be helpful to understand the cognitive science behind learning and study habits. We often work with SMEs to generate new content or facilitate content we're not an expert in. Either way, we need to become credible experts fast.",
        "Store": "BS",
    },
    {
        "Title": "Creative Acts For Curious People",
        "Link": "",
        "Categories": "Philosophy",
        "Description": "If you're trying to lead a design effort or scoop up some tribal knowledge it's great to put your SME's in creative situations to get them to reveal what they know. One of my favorite exercises from the book is #36, the unpacking exercise. Fantastic book for your desk.",
        "Store": "BS",
    },
    {
        "Title": "The Timeless Way of Building",
        "Link": "",
        "Categories": "Philosophy",
        "Description": "This book is about architecture, so what is it doing here? The books main argument is that you can understand design better by looking at patterns in how things were done in the past. It advocates looking at the design of a thing to support the whole human and promote their sense of well being.",
        "Store": "BS",
    },
    {
        "Title": "Map It",
        "Link": "",
        "Categories": "Philosophy",
        "Description": "Cathy Moore's book Map It shows you a practical step by step process that fits with the realities you'll face in business. I highly recommend this to anyone in L&D at any experience level.",
        "Store": "",
    },
    {
        "Title": "Artificial Intelligence for Learning",
        "Link": "",
        "Categories": "AI",
        "Description": "Donald Clark was working in AI for learning before it was cool. I personally valued this book because it wasn't all just hype. There are case studies of how people applied AI in real life with hard lessons in each.",
        "Store": "AZ",
    },
    {
        "Title": "Integrating AI into Learning Design and Development",
        "Link": "",
        "Categories": "AI",
        "Description": "An excellent primer for how to think about AI strategically with Learning Design. It has practical real world advice and hands on activities you can use with jr learning designers.",
        "Store": "AZ",
    },
    {
        "Title": "Caste",
        "Link": "",
        "Categories": "DEI",
        "Description": "If you work in training belonging or discrimination this book will do a lot to give you more of a global frame. I read this during the pandemic and it was a challenging, fascinating and ultimately a timely read.",
        "Store": "BS",
    },
    {
        "Title": "Mismatch",
        "Link": "",
        "Categories": "DEI",
        "Description": "Mismatch is one of my favorite books. A mismatch between someone's needs and a product causes exclusion. The book provides practices and processes which will help you build more inclusive systems and products. It is critical in L&D to reach everyone.",
        "Store": "",
    },
    {
        "Title": "Real Talk",
        "Link": "",
        "Categories": "Facilitation",
        "Description": "Bridgett McGowen made an impression on me during a podcast she was on so I picked up one of her books. I found some tips that resonated with me largely because unlike many presenters I'm an introvert and apparently so is the author.",
        "Store": "",
    },
    {
        "Title": "The Art of Gathering",
        "Link": "",
        "Categories": "Facilitation",
        "Description": "This book gives structure to gatherings that resonate well with me as an introvert and a learning professional. There are lessons for classroom facilitators and designers in general like priming users to set expectations about how the experience itself will be.",
        "Store": "",
    },
    {
        "Title": "The 2 Hour Cocktail Party",
        "Link": "",
        "Categories": "Facilitation",
        "Description": "On its surface this is a way to engineer social events with a proven formula. Beyond that it has some advice that learning professionals should take to heart. Pilot with a core group. Think about managing the energy of the learner. Create a psychologically safe experience.",
        "Store": "",
    },
    {
        "Title": "Interface Design for Learning",
        "Link": "",
        "Categories": "Elearning",
        "Description": "This book has detailed descriptions about why various interface components are important to learning as well as academic research backed citations showing why it's important. It gives the theory right next to examples of what it could look like.",
        "Store": "AZ",
    },
    {
        "Title": "For the Win",
        "Link": "",
        "Categories": "Engagement",
        "Description": "I consider this book to be the best primer for L&D people in gamification because instead of focusing on how to implement points in an elearning it focuses on gamification writ large. How do you use it to solve problems, what are the pitfalls and how you should use it ethically.",
        "Store": "",
    },
    {
        "Title": "Design is Storytelling",
        "Link": "",
        "Categories": "Engagement",
        "Description": "I found this book incredibly useful in my design, it has a ton of tools and concepts that you can use today. It's presented in an engaging and entertaining way that will keep you flipping through, adding tools to your design toolbelt.",
        "Store": "AZ",
    },
    {
        "Title": "Fail To Learn",
        "Link": "",
        "Categories": "Engagement",
        "Description": "This book is written by friend of The Nerd Out, Scott Provence. It gives you an excellent formula for both learning and engagement in organisational learning. It looks at it like game loops that you might see in a board or video game but elegantly lays out how you can build engaging practice.",
        "Store": "",
    },
    {
        "Title": "The DC Comics Guide to Writing Comics",
        "Link": "",
        "Categories": "Engagement",
        "Description": "In instructional design we're expected to keep things new and interesting. Graphic novel, comic book and hero narrative structures every so often keeps things fresh and unexpected for learners. Useful not only for breaking into those modalities but also to think through keeping stories interesting.",
        "Store": "AZ",
    },
    {
        "Title": "Kirkpatrick's Four Levels of Training Evaluation",
        "Link": "",
        "Categories": "Evaluation",
        "Description": "This book will not teach you everything you need to know about training evaluation but it will get you to a point where you can talk about evaluation with other industry professionals. The 4 levels is as much a part of the lingo as ADDIE.",
        "Store": "BS",
    },
    {
        "Title": "The Cult of Personality Testing",
        "Link": "",
        "Categories": "Evaluation",
        "Description": "Personality testing is a huge fixture in corporate learning. Knowing their limitations helps prepare you for the inevitable push back you'll get before you deploy. You should go in clear eyed about what these tests can actually do.",
        "Store": "",
    },
    {
        "Title": "True North, Emerging Leader Edition",
        "Link": "",
        "Categories": "Leadership",
        "Description": "I like this book for learning leaders partly because it encourages leadership as a whole authentic person. I am a big nerd with a big heart. I am not a hyper-efficient corporate guru. There are some great words of wisdom in there.",
        "Store": "",
    },
    {
        "Title": "Getting to Yes",
        "Link": "",
        "Categories": "Leadership",
        "Description": "This book helped me as an instructional designer to reframe my requests on people's time for what might build mutual advantage and value not just for SMEs but for leaders who own my budget, critical stakeholders and even getting access to do analysis on my audience.",
        "Store": "AZ",
    },
    {
        "Title": "The Skill Code",
        "Link": "",
        "Categories": "Leadership",
        "Description": "We're going through a demographic and technological change where highly skilled workers are retiring while entry level positions are disappearing. People aren't learning the skills they need through apprenticeship on the job like they used to. This book covers the evidence and what to do about it.",
        "Store": "AZ",
    },
    {
        "Title": "Engaged: The Neuroscience Behind Creating Productive People in Successful Organizations",
        "Link": "",
        "Categories": "Brain",
        "Description": "This book is research informed, accessible and resonates with my real life experience. When you organize talent and development around the human brain instead of traditional approaches you end up with better business results.",
        "Store": "AZ",
    },
]
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
    read_book_ledger,
    add_to_book_ledger,
    update_book_ledger_entry,
    delete_book_ledger_entry,
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


# --- Sidebar ---
st.sidebar.title("Nerd Out Automator")

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
        st.subheader("Step 2: Select Clusters & Articles")
        st.caption(
            "Check the clusters you want to include. "
            "Expand each cluster to select or deselect individual articles."
        )

        # Build filtered clusters based on user selections.
        # Each cluster checkbox acts as a "select all" toggle, and individual
        # entry checkboxes let you fine-tune which articles go into the draft.
        selected_clusters = []

        for i, cluster in enumerate(clusters):
            cluster_checked = st.checkbox(
                f"**{cluster['cluster_name']}** — {cluster['description']}",
                value=False,
                key=f"cluster_checkbox_{i}",
            )

            # Show entries inside an expander — with per-entry checkboxes
            entry_count = len(cluster["entry_ids"])
            with st.expander(
                f"View entries ({entry_count} articles)"
            ):
                selected_entry_ids = []
                for entry_id in cluster["entry_ids"]:
                    entry = entries_lookup.get(entry_id, {})
                    if entry:
                        # Entry checkbox defaults to checked when cluster is checked
                        entry_checked = st.checkbox(
                            f"[{entry.get('URL', '#')}]  ({entry.get('Category', 'N/A')})",
                            value=cluster_checked,
                            key=f"entry_checkbox_{i}_{entry_id}",
                        )
                        # Show the reflection text below the checkbox
                        reflection = entry.get("Reflection", "No reflection")
                        st.caption(f"  {reflection}")

                        if entry_checked:
                            selected_entry_ids.append(entry_id)

            # Build a filtered cluster object with only selected entries
            if selected_entry_ids:
                selected_clusters.append({
                    "cluster_name": cluster["cluster_name"],
                    "description": cluster["description"],
                    "entry_ids": selected_entry_ids,
                })

        st.session_state["selected_clusters"] = selected_clusters

        # --- Step 3: Generate Draft ---
        st.divider()
        st.subheader("Step 3: Generate Newsletter Draft")

        if not selected_clusters:
            st.info("Select at least one cluster and article above to generate a draft.")
        else:
            # Show a summary of what will be drafted
            total_articles = sum(len(c["entry_ids"]) for c in selected_clusters)
            st.write(
                f"**{len(selected_clusters)} clusters** with "
                f"**{total_articles} articles** selected."
            )

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
                        config = load_config(spreadsheet, spreadsheet.id)
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

                        # Store section-to-entry mapping so reflections
                        # can be displayed alongside each draft section
                        section_entry_map = {
                            c["cluster_name"]: c["entry_ids"]
                            for c in selected_clusters
                        }
                        st.session_state["section_entry_map"] = section_entry_map
                        st.session_state["draft_entries_lookup"] = entries_lookup

                        # Auto-update only the selected entries to "Queued"
                        all_entry_ids = []
                        for cluster in selected_clusters:
                            all_entry_ids.extend(cluster["entry_ids"])
                        st.session_state["draft_entry_ids"] = all_entry_ids
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

        # Load reflection mapping (only available for freshly generated drafts,
        # not for drafts loaded from Google Sheets — that's expected)
        section_entry_map = st.session_state.get("section_entry_map", {})
        draft_entries = st.session_state.get("draft_entries_lookup", {})

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

        # --- Step 5: Affiliate Book Picks ---
        st.divider()
        st.subheader("Step 5: Affiliate Book Picks")
        st.caption(
            "Suggest a book recommendation to include in this episode. "
            "Gemini scores each book for relevance to the episode's themes, "
            "and books that haven't been used recently get a boost."
        )

        # Only allow suggestions when we have cluster context
        selected_clusters_for_aff = st.session_state.get("selected_clusters", [])

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
                    suggestions = suggest_affiliate_books(
                        selected_clusters_for_aff, aff_books
                    )

                if suggestions is None:
                    st.error("Affiliate suggestion failed. Check your Gemini API key.")
                else:
                    # Apply recency weighting in Python
                    # Build a lookup of book metadata by title
                    book_meta = {b["Title"]: b for b in aff_books}
                    from datetime import datetime, timedelta
                    now = datetime.now()
                    recency_cutoff = now - timedelta(days=60)

                    for s in suggestions:
                        meta = book_meta.get(s["title"], {})
                        times_used = int(meta.get("Times_Used", 0) or 0)
                        last_used_str = str(meta.get("Last_Used", ""))

                        # Recency adjustment
                        if times_used == 0:
                            # Never used — bonus
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

                        # Final score
                        raw = float(s.get("relevance_score", 0))
                        s["final_score"] = min(1.0, max(0.0, raw + s["recency_adj"]))

                        # Attach metadata for display
                        s["store"] = meta.get("Store", "")
                        s["link"] = meta.get("Link", "")
                        s["description"] = meta.get("Description", "")
                        s["times_used"] = times_used

                    # Sort by final score descending
                    suggestions.sort(key=lambda x: x["final_score"], reverse=True)
                    st.session_state["affiliate_suggestions"] = suggestions

        # Display suggestions if they exist
        if "affiliate_suggestions" in st.session_state:
            suggestions = st.session_state["affiliate_suggestions"]
            st.write(f"**{len(suggestions)} books** scored. Select 1–3 to include:")

            for idx, s in enumerate(suggestions):
                score_pct = int(s["final_score"] * 100)
                store_badge = f" [{s['store']}]" if s["store"] else ""
                recency_label = f" — {s['recency_flag']}"
                if s["times_used"] > 0:
                    recency_label += f" ({s['times_used']}x)"

                st.checkbox(
                    f"**{s['title']}**{store_badge} — "
                    f"Score: {score_pct}%{recency_label}",
                    value=False,
                    key=f"affiliate_pick_{idx}",
                )

                # Show reasoning + blurb in a compact expander
                with st.expander(f"Details: {s['title']}", expanded=False):
                    st.caption(f"Gemini says: {s['reasoning']}")
                    if s["description"]:
                        st.markdown(f"**Your blurb:** {s['description'][:200]}...")
                    if s["link"]:
                        st.markdown(f"Link: {s['link']}")
                    else:
                        st.caption("No affiliate link set — add one in Settings > Book Ledger")

            # Insert button
            if st.button("Insert Affiliate Section", key="insert_affiliate_btn"):
                # Collect checked books (max 3)
                picked = []
                for idx, s in enumerate(suggestions):
                    if st.session_state.get(f"affiliate_pick_{idx}", False):
                        picked.append(s)
                    if len(picked) >= 3:
                        break

                if not picked:
                    st.warning("Select at least one book to insert.")
                else:
                    # Build the affiliate section content from pre-written blurbs
                    lines = ["## Affiliate Picks\n"]
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

                    # Insert before Footer (if exists), otherwise at the end
                    sections = st.session_state["draft_sections"]
                    # Remove any existing Affiliate Picks section first
                    sections = [
                        s for s in sections
                        if s["section"] != "Affiliate Picks"
                    ]
                    footer_idx = next(
                        (i for i, s in enumerate(sections)
                         if s["section"] == "Footer"),
                        None
                    )
                    new_section = {
                        "section": "Affiliate Picks",
                        "content": affiliate_content,
                    }
                    if footer_idx is not None:
                        sections.insert(footer_idx, new_section)
                    else:
                        sections.append(new_section)

                    st.session_state["draft_sections"] = sections
                    st.session_state["affiliate_book_titles"] = affiliate_titles
                    st.success(
                        f"Inserted {len(picked)} book(s) as 'Affiliate Picks' section!"
                    )
                    st.rerun()

        # --- Save, Preview, Clear, and Publish buttons ---
        btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

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
                    "section_entry_map",
                    "draft_entries_lookup",
                    "draft_entry_ids",
                    "confirm_publish",
                    "affiliate_suggestions",
                    "affiliate_book_titles",
                ]:
                    st.session_state.pop(key, None)
                st.info("Draft cleared. You can start fresh!")
                st.rerun()

        with btn_col4:
            # Publish is only available when we know which entries to mark as Used
            draft_entry_ids = st.session_state.get("draft_entry_ids", [])
            if st.button(
                "Publish",
                disabled=not draft_entry_ids,
                help="Mark entries as Used, record the episode, and clear the draft."
                if draft_entry_ids else
                "Not available — draft was loaded from saved state without entry tracking.",
            ):
                st.session_state["confirm_publish"] = True

        # --- Publish Confirmation ---
        if st.session_state.get("confirm_publish", False):
            aff_titles = st.session_state.get("affiliate_book_titles", [])
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
                    publish_episode(
                        spreadsheet,
                        edited_sections,
                        st.session_state["draft_entry_ids"],
                        affiliate_book_titles=st.session_state.get(
                            "affiliate_book_titles", []
                        ),
                    )
                    for key in [
                        "draft_sections",
                        "clusters",
                        "cluster_entries",
                        "selected_clusters",
                        "show_preview",
                        "section_entry_map",
                        "draft_entries_lookup",
                        "draft_entry_ids",
                        "confirm_publish",
                        "affiliate_suggestions",
                        "affiliate_book_titles",
                    ]:
                        st.session_state.pop(key, None)
                    st.cache_data.clear()
                    st.success("Published! Entries marked as Used.")
                    st.rerun()
            with conf_col2:
                if st.button("Cancel"):
                    st.session_state.pop("confirm_publish", None)
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

    # Load existing config — cached, but the cache is cleared after every save
    # (st.cache_data.clear() runs when Save Settings / Add / Delete is clicked)
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

    # --- Manage Categories ---
    st.divider()
    st.subheader("Manage Categories")
    st.caption("Add, remove, or reorder the categories used in the Add Content form.")

    cat_json = config.get("categories", "")
    current_categories = json.loads(cat_json) if cat_json else list(DEFAULT_CATEGORIES)

    # Display each category with a delete button
    for i, cat in enumerate(current_categories):
        cat_col1, cat_col2 = st.columns([4, 1])
        with cat_col1:
            st.write(cat)
        with cat_col2:
            if st.button("❌", key=f"del_cat_{i}"):
                current_categories.pop(i)
                # Read-modify-write: preserve other config values
                full_config = load_config(spreadsheet, spreadsheet.id)
                full_config["categories"] = json.dumps(current_categories)
                save_config(spreadsheet, full_config)
                st.cache_data.clear()
                st.rerun()

    # Add new category
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

    # --- Book Ledger Management ---
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

    # --- Import starter books from PDF data ---
    with st.expander("Import Starter Books (from Nerd Out Affiliate Links PDF)"):
        st.caption(
            f"Import {len(STARTER_BOOKS)} pre-configured books from the Nerd Out "
            "affiliate links list. Titles, categories, descriptions, and store "
            "indicators are pre-filled. **You'll need to paste in the actual "
            "affiliate URLs** via the edit table above after importing."
        )

        # Show preview
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
