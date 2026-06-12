# ─── Road Trippin' — Config Template ────────────────────────────
# Copy this file to config.py and fill in your credentials.
# config.py is gitignored and will never be committed.
#
# Setup steps:
#   1. cp config.example.py config.py
#   2. Fill in each value below
#   3. Never commit config.py

# ─── YouTube OAuth ───────────────────────────────────────────────
# Get credentials from Google Cloud Console → APIs & Services → Credentials
# Channel ID: found in YouTube Studio → Settings → Channel → Advanced
YT_CHANNEL_ID    = "YOUR_CHANNEL_ID"
YT_CLIENT_ID     = "YOUR_CLIENT_ID.apps.googleusercontent.com"
YT_CLIENT_SECRET = "YOUR_CLIENT_SECRET"
YT_REFRESH_TOKEN = "YOUR_REFRESH_TOKEN"
# How to get refresh token: use OAuth Playground (developers.google.com/oauthplayground)
# Scopes needed: yt-analytics.readonly + youtube.readonly

# ─── Megaphone API ───────────────────────────────────────────────
# Token: Megaphone CMS → click your initials (lower-left) → User Settings → API Tokens
MEGAPHONE_TOKEN      = "YOUR_MEGAPHONE_API_TOKEN"
MEGAPHONE_NETWORK_ID = "YOUR_NETWORK_UUID"   # from cms.megaphone.fm/api/networks URL
MEGAPHONE_PODCAST_ID = "YOUR_PODCAST_UUID"   # from cms.megaphone.fm URL when viewing show
MEGAPHONE_API_BASE   = "https://cms.megaphone.fm/api"