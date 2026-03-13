"""
gemini.py - Gemini AI operations for clustering and draft generation.

This module handles all interactions with the Gemini API. The Streamlit UI
(app.py) calls these functions instead of talking to Gemini directly.

How it works:
- We send the user's collected links and reflections to Gemini
- Gemini groups them into topic clusters (semantic similarity)
- Later, Gemini generates a newsletter draft from selected clusters
"""

import json
import requests
from bs4 import BeautifulSoup
from google import genai
from config import get_gemini_api_key


def get_gemini_client():
    """
    Creates and returns a Gemini API client.

    Returns the client, or None if the API key is not configured.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def fetch_url_title(url):
    """
    Fetches the HTML <title> tag from a URL.

    Returns the title string, or None if it can't be fetched (timeout,
    non-HTML page, connection error, etc.). Wrapped in try/except so
    it never crashes the app.
    """
    try:
        response = requests.get(
            url,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0 (Newsletter Automator)"},
            allow_redirects=True,
        )
        response.raise_for_status()

        # Only parse HTML content
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("title")
        if title_tag and title_tag.string:
            return title_tag.string.strip()
        return None
    except Exception:
        return None


def fetch_all_titles(entries_lookup):
    """
    Fetches HTML titles for all entries in the lookup dict.

    Args:
        entries_lookup: A dict mapping entry ID -> entry dict (each has a 'URL' key)

    Returns:
        A dict mapping URL -> title string (or None if fetch failed)
    """
    url_titles = {}
    for entry in entries_lookup.values():
        url = entry.get("URL", "")
        if url and url not in url_titles:
            url_titles[url] = fetch_url_title(url)
    return url_titles


def cluster_entries(entries):
    """
    Takes a list of backlog entries and asks Gemini to group them into
    topic clusters.

    Args:
        entries: A list of dicts, each with keys: ID, URL, Reflection, Category
                 (filtered to New/Reviewed status entries)

    Returns:
        A list of cluster dicts on success:
        [
            {
                "cluster_name": "AI in Education",
                "description": "Articles about how AI is changing learning...",
                "entry_ids": [1, 3, 7]
            },
            ...
        ]
        Returns None if the API key is missing or the call fails.
    """
    client = get_gemini_client()
    if not client:
        return None

    # Build the prompt with the user's entries
    entries_text = ""
    for entry in entries:
        entries_text += (
            f"- ID: {entry['ID']}\n"
            f"  URL: {entry['URL']}\n"
            f"  Category: {entry['Category']}\n"
            f"  Reflection: {entry['Reflection']}\n\n"
        )

    prompt = f"""You are helping organize links for a newsletter called "Nerd Out."

Here are the collected links and the curator's reflections on each:

{entries_text}

Your task: Group these entries into 3-6 topic clusters based on thematic
similarity. Each cluster should have a clear, catchy name that could work
as a newsletter section heading.

Rules:
- Every entry must belong to exactly one cluster.
- Aim for 3-6 clusters. If there are fewer than 6 entries, use fewer clusters.
- The cluster name should be engaging (like a newsletter section title).
- The description should be 1-2 sentences explaining the common thread.
- Return the entry IDs (as integers) for each cluster.
"""

    # JSON schema for structured output — forces Gemini to return valid,
    # parseable JSON matching this exact structure. No fragile text parsing needed.
    response_schema = {
        "type": "object",
        "properties": {
            "clusters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cluster_name": {
                            "type": "string",
                            "description": "A catchy section heading for this cluster",
                        },
                        "description": {
                            "type": "string",
                            "description": "1-2 sentences on the common thread",
                        },
                        "entry_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "The IDs of entries in this cluster",
                        },
                    },
                    "required": ["cluster_name", "description", "entry_ids"],
                },
            }
        },
        "required": ["clusters"],
    }

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            },
        )
        result = json.loads(response.text)
        return result["clusters"]
    except Exception as e:
        print(f"Gemini clustering error: {e}")
        return None


def generate_draft(selected_clusters, entries_lookup, url_titles=None):
    """
    Takes selected clusters and their entries, and asks Gemini to generate
    a structured Markdown newsletter draft.

    Args:
        selected_clusters: A list of cluster dicts from cluster_entries()
        entries_lookup: A dict mapping entry ID -> entry dict
        url_titles: Optional dict mapping URL -> article title string.
                    If provided, Gemini will use article titles as link text.

    Returns:
        A list of section dicts on success:
        [
            {"section": "Intro", "content": "Welcome to this week's..."},
            {"section": "AI in Education", "content": "## AI in Education\\n..."},
            {"section": "Closing", "content": "That's a wrap..."}
        ]
        Returns None on failure.
    """
    client = get_gemini_client()
    if not client:
        return None

    # Build the cluster details for the prompt
    clusters_text = ""
    for cluster in selected_clusters:
        clusters_text += f"\n### {cluster['cluster_name']}\n"
        clusters_text += f"Theme: {cluster['description']}\n"
        clusters_text += "Entries:\n"
        for eid in cluster["entry_ids"]:
            entry = entries_lookup.get(eid, {})
            if entry:
                url = entry.get('URL', 'N/A')
                clusters_text += f"- URL: {url}\n"
                # Include the fetched article title if available
                if url_titles:
                    title = url_titles.get(url)
                    if title:
                        clusters_text += f"  Article Title: {title}\n"
                clusters_text += (
                    f"  Reflection: {entry.get('Reflection', 'N/A')}\n"
                    f"  Category: {entry.get('Category', 'N/A')}\n"
                )

    prompt = f"""You are writing a newsletter called "Nerd Out" — a curated digest
for curious people who love learning about tech, science, culture, and more.

The tone is: enthusiastic but not hype-y, smart but accessible, like a friend
who reads a lot and wants to share the best stuff they found this week.

Here are the topic clusters and their entries:
{clusters_text}

Generate a complete newsletter draft in Markdown with these sections:

1. "Intro" — A 2-3 sentence opening that teases the themes in this issue.
   Make it inviting and energetic.

2. One section per topic cluster (use the cluster name as the section heading).
   For each section:
   - Write a brief 2-3 sentence narrative connecting the entries
   - For each entry, write a 1-2 sentence summary that captures why it matters
   - Format every link as [Article Title](URL) using the provided Article Title.
     If no Article Title was provided for a link, use the Category as the link text.
   - Use the curator's reflection as inspiration but write fresh copy

3. "Closing" — A 1-2 sentence sign-off that encourages readers to share
   or reply with their own finds.

Important:
- Use Markdown formatting (## for headings, **bold** for emphasis, [links](url))
- Every link MUST be formatted as [Article Title](URL), never as a raw URL
- Keep each section concise — this is a newsletter, not an essay
- The total draft should be scannable and fun to read
"""

    response_schema = {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "description": "The section name",
                        },
                        "content": {
                            "type": "string",
                            "description": "The Markdown content for this section",
                        },
                    },
                    "required": ["section", "content"],
                },
            }
        },
        "required": ["sections"],
    }

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            },
        )
        result = json.loads(response.text)
        return result["sections"]
    except Exception as e:
        print(f"Gemini draft generation error: {e}")
        return None
