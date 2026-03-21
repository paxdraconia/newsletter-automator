# Newsletter Automator

A Streamlit app for managing newsletter content using Google Sheets as a database and Gemini AI for intelligent drafting.

## Features

- **AI-powered topic clustering** — Gemini groups your saved links into thematic clusters
- **Automated newsletter drafting** — Generate section-by-section drafts with editable text areas
- **Affiliate book recommendations** — Gemini scores your book catalog for relevance, with recency weighting
- **Cross-device persistence** — Start a draft on your PC, finish on your phone (Google Sheets as backend)
- **Multi-publication support** — Manage multiple newsletters from one app
- **One-click Streamlit Cloud deployment** — Works locally and in the cloud with zero code changes

## Prerequisites

- **Python 3.10+**
- **A Google account** (your regular Gmail/Google account)
- **A Google AI Studio account** (for Gemini AI features) — get a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

## Setup Guide

### Step 1: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Set Up Google Cloud (Service Account)

A "service account" is like a robot Google account that your app uses to read/write Google Sheets.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** > **New Project**
3. Name it something like `newsletter-automator` and click **Create**

#### Enable the APIs

4. Go to **APIs & Services** > **Library**
5. Search for **Google Sheets API** and click **Enable**
6. Search for **Google Drive API** and click **Enable**

#### Create the Service Account

7. Go to **APIs & Services** > **Credentials**
8. Click **+ Create Credentials** > **Service Account**
9. Name it `newsletter-bot` and click **Create and Continue**
10. Skip the "Grant access" steps — click **Done**

#### Download the JSON Key

11. Click on the service account email in the list
12. Go to the **Keys** tab > **Add Key** > **Create new key** > **JSON** > **Create**
13. **Keep this file safe** — move it somewhere secure, NOT inside this project folder

#### Note the Service Account Email

14. Copy the service account email (e.g., `newsletter-bot@your-project.iam.gserviceaccount.com`)

### Step 3: Create Your Google Sheet

1. Go to [Google Sheets](https://sheets.google.com/) and create a new spreadsheet
2. Name it exactly: **NerdOut_DB** (or `YourName_DB` for a custom publication)
3. Click **Share** > paste the service account email > set to **Editor** > **Share**

The app will automatically create the required tabs on first run.

### Step 4: Configure Local Development

1. Copy the template:
   ```bash
   cp .env.template .env
   ```

2. Fill in your values:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=C:/Users/yourname/path/to/your-key.json
   GEMINI_API_KEY=your-gemini-api-key-here
   ```

### Step 5: Run the App

```bash
streamlit run app.py
```

## Deploying to Streamlit Community Cloud

1. **Push to GitHub** (make sure `.gitignore` is committed first!)
2. Go to [share.streamlit.io](https://share.streamlit.io/) > **New app** > connect your repo
3. Set the main file to `app.py`
4. Go to **Settings** > **Secrets** and paste values following `.streamlit/secrets.toml.template`

## Project Structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI — page rendering and user interaction |
| `config.py` | Authentication — credential loading for local + cloud |
| `sheets.py` | Data layer — all Google Sheets CRUD operations |
| `gemini.py` | AI layer — Gemini API for clustering, drafting, and book suggestions |
| `constants.py` | Shared constants — session keys, section names, defaults |
| `requirements.txt` | Python dependencies |
| `.env.template` | Template for local development secrets |
| `.streamlit/secrets.toml.template` | Template for Streamlit Cloud secrets |
| `starter_books.json.template` | Template for bulk book import (optional) |

## Starter Books (Optional)

To use the bulk book import feature, create a `starter_books.json` file in the project root. See `starter_books.json.template` for the expected format. This file is gitignored since it contains personal content.

## Troubleshooting

**"Could not authenticate with Google Sheets"**
- Make sure your `.env` file exists and `GOOGLE_SERVICE_ACCOUNT_FILE` points to the right JSON file

**"SpreadsheetNotFound"**
- Make sure your Google Sheet is named exactly `NerdOut_DB` (or `YourPublication_DB`)
- Make sure you shared it with the service account email (Editor permission)

**"APIError: PERMISSION_DENIED"**
- Make sure you enabled both the Google Sheets API AND Google Drive API in Google Cloud

## Design Decisions

Key decisions made during development and the reasoning behind them:

| Decision | Why |
|---|---|
| **Google Sheets as database** | Cross-device access with zero infrastructure — start a draft on your PC, finish on your phone. No database server to manage. |
| **Gemini for AI** | Free tier is generous for hobby projects. Structured JSON output mode eliminates fragile text parsing. |
| **`google-genai` SDK** | The newer SDK replaces the deprecated `google-generativeai` package. |
| **Pre-written affiliate blurbs** | AI-generated blurbs lack the curator's authentic voice. Blurbs are stored in the Book Ledger and inserted verbatim. |
| **Recency weighting in Python** | Gemini scores books on topical relevance only. Recency (how recently a book was featured) is a deterministic formula applied in Python, not an AI judgment call. |
| **Section-name-based widget keys** | Index-based Streamlit keys (`draft_section_0`) cause content to bleed between sections when new sections are inserted mid-list. Name-based keys (`draft_section_Footer`) are stable. |
| **Service account auth** | Simpler than OAuth — no user login flow. The bot account gets Editor access to one spreadsheet. |
| **`starter_books.json` gitignored** | Contains personal book recommendations. A `.json.template` is provided for forks. |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and code conventions.

## License

MIT License — see [LICENSE](LICENSE) for details.
