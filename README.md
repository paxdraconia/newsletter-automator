# Nerd Out Automator

A Streamlit app for managing newsletter content using Google Sheets as a database.

## Prerequisites

- **Python 3.10+** (you have 3.14 — that works)
- **A Google account** (your regular Gmail/Google account)
- **A Google AI Studio account** (for future Gemini AI features — optional for now)

## Setup Guide

### Step 1: Install Python Dependencies

Open a terminal in this project folder and run:

```bash
pip install -r requirements.txt
```

This installs Streamlit (the app framework), gspread (Google Sheets library), and other dependencies.

### Step 2: Set Up Google Cloud (Service Account)

A "service account" is like a robot Google account that your app uses to read/write Google Sheets. Here's how to create one:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click **Select a project** (top bar) > **New Project**
3. Name it something like `newsletter-automator` and click **Create**
4. Wait for it to be created, then make sure it's selected in the top bar

#### Enable the APIs

5. In the left sidebar, go to **APIs & Services** > **Library**
6. Search for **Google Sheets API** and click **Enable**
7. Search for **Google Drive API** and click **Enable**

#### Create the Service Account

8. In the left sidebar, go to **APIs & Services** > **Credentials**
9. Click **+ Create Credentials** > **Service Account**
10. Name it `newsletter-bot` (or anything you like) and click **Create and Continue**
11. Skip the "Grant access" step — click **Continue**
12. Skip the "Grant users access" step — click **Done**

#### Download the JSON Key

13. You'll see your new service account in the list. Click on its email address
14. Go to the **Keys** tab
15. Click **Add Key** > **Create new key** > **JSON** > **Create**
16. A `.json` file will download — **keep this file safe, it's like a password!**
17. Move it somewhere secure (NOT inside this project folder — it's in .gitignore but best to keep it elsewhere)

#### Note the Service Account Email

18. On the service account details page, copy the **email address** (it looks like `newsletter-bot@your-project.iam.gserviceaccount.com`)
19. You'll need this in the next step

### Step 3: Create Your Google Sheet

1. Go to [Google Sheets](https://sheets.google.com/) and create a new spreadsheet
2. Name it exactly: **NerdOut_DB**
3. Click **Share** (top right)
4. Paste the service account email from Step 2.18
5. Set the permission to **Editor**
6. Uncheck "Notify people" and click **Share**

The app will automatically create the required tabs (Inbound_Backlog, Book_Ledger, Draft_State) on first run.

### Step 4: Configure Local Development

1. Copy the template file:
   ```bash
   cp .env.template .env
   ```

2. Open `.env` and fill in your values:
   ```
   GOOGLE_SERVICE_ACCOUNT_FILE=C:/Users/yourname/path/to/your-key.json
   GEMINI_API_KEY=your-gemini-api-key-here
   ```

   - For the JSON path, use the full path to the file you downloaded in Step 2.16
   - For the Gemini key, get it from [Google AI Studio](https://aistudio.google.com/apikey) (optional for now)

### Step 5: Run the App

```bash
streamlit run app.py
```

The app will open in your browser. You should see the dashboard with the sidebar.

## Deploying to Streamlit Community Cloud

Once you've tested locally and are ready to deploy:

1. **Push to GitHub** (make sure `.gitignore` is committed first!)
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```
   Then create a repo on GitHub and push.

2. **Connect to Streamlit Cloud**
   - Go to [share.streamlit.io](https://share.streamlit.io/)
   - Click **New app** and connect your GitHub repo
   - Set the main file to `app.py`

3. **Configure Secrets**
   - In your deployed app, go to **Settings** > **Secrets**
   - Paste the contents following the format in `.streamlit/secrets.toml.template`
   - For the `[gcp_service_account]` section, copy the entire contents of your JSON key file and format it as TOML (the template shows the format)

## Project Structure

| File | Purpose |
|---|---|
| `app.py` | Main Streamlit app — the UI you interact with |
| `config.py` | Authentication — connects to Google (works locally and in the cloud) |
| `sheets.py` | Data layer — all Google Sheets reading/writing |
| `requirements.txt` | Python dependencies |
| `.env.template` | Template for local development secrets |
| `.streamlit/secrets.toml.template` | Template for Streamlit Cloud secrets |

## Troubleshooting

**"Could not authenticate with Google Sheets"**
- Make sure your `.env` file exists and `GOOGLE_SERVICE_ACCOUNT_FILE` points to the right JSON file
- Make sure the JSON file actually exists at that path

**"SpreadsheetNotFound"**
- Make sure your Google Sheet is named exactly `NerdOut_DB`
- Make sure you shared it with the service account email (Editor permission)

**"APIError: PERMISSION_DENIED"**
- Make sure you enabled both the Google Sheets API AND Google Drive API in your Google Cloud project
