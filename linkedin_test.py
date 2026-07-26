"""
Quick test to verify the LinkedIn token works for posting.
Bypasses the Streamlit app entirely.
"""
import os
from dotenv import load_dotenv
import requests
import json

load_dotenv(override=True)

token = os.environ.get("LINKEDIN_ACCESS_TOKEN")
urn = os.environ.get("LINKEDIN_PERSON_URN")

print(f"Token (first 20 chars): {token[:20] if token else 'NOT SET'}...")
print(f"Token length: {len(token) if token else 0}")
print(f"Person URN: {urn}")
print()

if not token or not urn:
    print("ERROR: Missing token or URN in .env")
    exit()

# Test 1: Verify token by calling userinfo
print("--- Test 1: Verify token via /v2/userinfo ---")
r = requests.get(
    "https://api.linkedin.com/v2/userinfo",
    headers={"Authorization": f"Bearer {token}"}
)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:300]}")
print()

# Test 2: Try to post a tiny test message
print("--- Test 2: Try to POST a test message ---")
payload = {
    "author": urn,
    "lifecycleState": "PUBLISHED",
    "specificContent": {
        "com.linkedin.ugc.ShareContent": {
            "shareCommentary": {"text": "Test post from API - please ignore"},
            "shareMediaCategory": "NONE",
        }
    },
    "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
}
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "X-Restli-Protocol-Version": "2.0.0",
}
r = requests.post(
    "https://api.linkedin.com/v2/ugcPosts",
    json=payload,
    headers=headers
)
print(f"Status: {r.status_code}")
print(f"Response: {r.text[:500]}")
