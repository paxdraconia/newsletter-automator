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
import logging
import requests
from bs4 import BeautifulSoup
from google import genai
from config import get_gemini_api_key
from constants import GEMINI_MODEL

logger = logging.getLogger(__name__)


def _call_gemini(client, prompt, response_schema, result_key):
    """Call Gemini with structured JSON output.

    Shared wrapper for all Gemini API calls in this module. Handles
    error logging and JSON parsing in one place.

    Args:
        client: The genai Client instance
        prompt: The prompt string to send
        response_schema: JSON schema dict for structured output
        result_key: The top-level key to extract from the JSON response

    Returns:
        A tuple of (result, error_message). On success, result is the parsed
        list or dict and error_message is None. On failure, result is None
        and error_message is a string describing the error.
    """
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": response_schema,
            },
        )
        result = json.loads(response.text)
        return result[result_key], None
    except Exception as e:
        logger.error("Gemini API error (%s): %s", result_key, e)
        return None, str(e)


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
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                )
            },
            allow_redirects=True,
        )
        response.raise_for_status()

        # Only parse HTML content
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            # Use .get_text() instead of .string — .string returns None when
            # the <title> tag has nested elements (common on YouTube, news sites)
            text = title_tag.get_text(strip=True)
            if text:
                return text
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


def cluster_entries(entries, publication_name="Nerd Out"):
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
        Returns (result, error) tuple. On failure, result is None and error
        is a string. Returns (None, None) if the API key is not configured.
    """
    client = get_gemini_client()
    if not client:
        return None, None

    # Build the prompt with the user's entries
    entries_text = ""
    for entry in entries:
        entries_text += (
            f"- ID: {entry['ID']}\n"
            f"  URL: {entry['URL']}\n"
            f"  Category: {entry['Category']}\n"
            f"  Reflection: {entry['Reflection']}\n\n"
        )

    prompt = f"""You are helping organize links for a newsletter called "{publication_name}."

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

    return _call_gemini(client, prompt, response_schema, "clusters")


def suggest_affiliate_books(clusters, book_ledger_entries, publication_name="Nerd Out"):
    """
    Asks Gemini to score each book in the Book Ledger for relevance to the
    episode's topic clusters. Returns a ranked list of suggestions.

    Gemini only handles relevance scoring. Recency weighting (how recently a
    book was used) is applied separately in app.py using the Last_Used and
    Times_Used fields from the Book Ledger.

    Args:
        clusters: List of selected cluster dicts with cluster_name, description
        book_ledger_entries: List of dicts from read_book_ledger() — each has
                            Title, Link, Categories, Description, Store,
                            Last_Used, Times_Used

    Returns:
        A list of suggestion dicts on success, sorted by relevance:
        [
            {"title": "Book Title", "relevance_score": 0.92,
             "reasoning": "Directly relates to..."},
            ...
        ]
        Returns (result, error) tuple. On failure, result is None and error
        is a string. Returns (None, None) if the API key is not configured.
    """
    client = get_gemini_client()
    if not client:
        return None, None

    # Build cluster context for the prompt
    clusters_text = ""
    for cluster in clusters:
        clusters_text += (
            f"- {cluster['cluster_name']}: {cluster['description']}\n"
        )

    # Build book catalog for the prompt (exclude usage stats — that's handled
    # in Python, not by Gemini, to keep the scoring purely about relevance)
    books_text = ""
    for book in book_ledger_entries:
        books_text += (
            f"- Title: {book.get('Title', 'Untitled')}\n"
            f"  Category: {book.get('Categories', 'N/A')}\n"
            f"  Description: {book.get('Description', 'N/A')}\n\n"
        )

    prompt = f"""You are helping select affiliate book recommendations for a newsletter
called "{publication_name}" — a curated digest about tech, learning, design, and culture.

The current episode covers these themes:
{clusters_text}

Here is the book catalog:
{books_text}

Score each book from 0.0 to 1.0 on how relevant it is to THIS episode's themes.
- 0.8-1.0: Directly related to a cluster topic
- 0.5-0.7: Somewhat related, tangential connection
- 0.2-0.4: Loosely related at best
- 0.0-0.1: No meaningful connection

For each book, provide:
- title: The exact book title as given
- relevance_score: A float from 0.0 to 1.0
- reasoning: A brief 1-sentence explanation of why this score

Return ALL books, even those with low relevance scores.
"""

    response_schema = {
        "type": "object",
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "The exact book title",
                        },
                        "relevance_score": {
                            "type": "number",
                            "description": "Relevance score 0.0-1.0",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Brief explanation of the score",
                        },
                    },
                    "required": ["title", "relevance_score", "reasoning"],
                },
            }
        },
        "required": ["suggestions"],
    }

    return _call_gemini(client, prompt, response_schema, "suggestions")


def generate_draft(selected_clusters, entries_lookup, url_titles=None, publication_name="Nerd Out"):
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
        Returns (result, error) tuple. On failure, result is None and error
        is a string. Returns (None, None) if the API key is not configured.
    """
    client = get_gemini_client()
    if not client:
        return None, None

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

    prompt = f"""You are writing a newsletter called "{publication_name}" — a curated digest
for curious people who love learning about tech, science, culture, and more.

The tone is: enthusiastic but not hype-y, smart but accessible, like a friend
who reads a lot and wants to share the best stuff they found this week.

Here are the topic clusters and their entries:
{clusters_text}

Generate a complete newsletter draft in Markdown with these sections:

1. "Intro" — A 2-3 sentence opening that teases the themes in this issue.
   Make it inviting and energetic.

2. One section per topic cluster (use the cluster name as the section heading).
   For each section, format EACH entry like this example:

   > [Article Title](https://example.com/article)

   Your 1-2 sentence commentary about why this matters and what the reader
   should take away from it. Use the curator's reflection as inspiration
   but write fresh copy.

   Rules for entries:
   - Start each entry with a blockquote line containing ONLY the linked title
   - Use the provided Article Title as the link text
   - If no Article Title was provided, use the Category as the link text
   - After the blockquote link, add a blank line, then the commentary paragraph
   - Do NOT embed links inside the commentary text

3. "Closing" — A 1-2 sentence sign-off that encourages readers to share
   or reply with their own finds.

Important:
- Use Markdown formatting (## for headings, **bold** for emphasis)
- Every link MUST be formatted as > [Article Title](URL) on its own blockquote line
- Never use raw URLs — always use [Title](URL) format
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

    return _call_gemini(client, prompt, response_schema, "sections")
