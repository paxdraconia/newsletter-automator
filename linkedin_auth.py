import os
import requests
import json

# One-off OAuth setup script - run locally to exchange an auth code for a
# token. Reads from env vars rather than hardcoding secrets so this is safe
# to commit. Set these in your shell (or a local, gitignored .env you source)
# before running: LINKEDIN_SETUP_CLIENT_ID, LINKEDIN_SETUP_CLIENT_SECRET,
# LINKEDIN_SETUP_CODE (the ?code= param from the OAuth redirect).
CLIENT_ID = os.environ["LINKEDIN_SETUP_CLIENT_ID"]
CLIENT_SECRET = os.environ["LINKEDIN_SETUP_CLIENT_SECRET"]
CODE = os.environ["LINKEDIN_SETUP_CODE"]

# Exchange code for token
token_response = requests.post(
    "https://www.linkedin.com/oauth/v2/accessToken",
    data={
        "grant_type": "authorization_code",
        "code": CODE,
        "redirect_uri": "http://localhost:8501/",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
)

print("Token response:")
print(json.dumps(token_response.json(), indent=2))
print()

access_token = token_response.json()["access_token"]

# Get userinfo
user_response = requests.get(
    "https://api.linkedin.com/v2/userinfo",
    headers={"Authorization": f"Bearer {access_token}"}
)
print("User response:")
print(json.dumps(user_response.json(), indent=2))