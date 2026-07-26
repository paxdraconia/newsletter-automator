"""
Threads OAuth: exchange code -> short-lived token -> long-lived token -> user ID.
"""
import os
import requests
import json

# One-off OAuth setup script - run locally to exchange an auth code for a
# token. Reads from env vars rather than hardcoding secrets so this is safe
# to commit. Set these in your shell (or a local, gitignored .env you source)
# before running: THREADS_SETUP_APP_ID, THREADS_SETUP_APP_SECRET,
# THREADS_SETUP_CODE (the ?code= param from the OAuth redirect).
THREADS_APP_ID = os.environ["THREADS_SETUP_APP_ID"]
THREADS_APP_SECRET = os.environ["THREADS_SETUP_APP_SECRET"]
CODE = os.environ["THREADS_SETUP_CODE"]

# Step 1: Exchange code for short-lived token
print("--- Step 1: Code -> short-lived token ---")
short_resp = requests.post(
    "https://graph.threads.net/oauth/access_token",
    data={
        "client_id": THREADS_APP_ID,
        "client_secret": THREADS_APP_SECRET,
        "grant_type": "authorization_code",
        "redirect_uri": "http://localhost:8501/threads-callback/",
        "code": CODE,
    }
)
print(f"Status: {short_resp.status_code}")
print(f"Response: {short_resp.text[:300]}\n")

short_data = short_resp.json()
short_token = short_data["access_token"]
user_id = short_data["user_id"]
print(f"✓ Short-lived token: {short_token[:30]}...")
print(f"✓ User ID: {user_id}\n")

# Step 2: Exchange short-lived for long-lived (60-day) token
print("--- Step 2: Short-lived -> long-lived (60-day) token ---")
long_resp = requests.get(
    "https://graph.threads.net/access_token",
    params={
        "grant_type": "th_exchange_token",
        "client_secret": THREADS_APP_SECRET,
        "access_token": short_token,
    }
)
print(f"Status: {long_resp.status_code}")
print(f"Response: {long_resp.text[:300]}\n")

long_data = long_resp.json()
long_token = long_data["access_token"]
print(f"✓ Long-lived token: {long_token[:30]}...")
print(f"✓ Expires in: {long_data.get('expires_in', '?')} seconds (~60 days)\n")

# Step 3: Done!
print("=" * 60)
print("Add these to your .env file:")
print(f"META_LONG_LIVED_TOKEN={long_token}")
print(f"THREADS_USER_ID={user_id}")