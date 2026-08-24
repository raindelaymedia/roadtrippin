"""
Schultz Report — API Connection Test
Pings YouTube Data API + YouTube Analytics API once each to verify credentials.
No data saved — just prints results to terminal.

Usage:
    python test_sr_api.py
"""

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as build_api

from config_sr import (
    YT_CHANNEL_ID    as CHANNEL_ID,
    YT_CLIENT_ID     as CLIENT_ID,
    YT_CLIENT_SECRET as CLIENT_SECRET,
    YT_REFRESH_TOKEN as REFRESH_TOKEN,
)

print("=" * 50)
print("SCHULTZ REPORT — API CONNECTION TEST")
print("=" * 50)

# ── Auth ──
print("\n1. Authenticating...")
try:
    creds = Credentials(
        token=None, refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.readonly"])
    creds.refresh(Request())
    print("   ✓ OAuth token refreshed successfully")
except Exception as e:
    print(f"   ✗ Auth failed: {e}")
    raise SystemExit(1)

# ── Test 1: YouTube Data API (public channel info) ──
print("\n2. YouTube Data API — channel info...")
try:
    youtube = build_api("youtube", "v3", credentials=creds)
    resp = youtube.channels().list(part="snippet,statistics", id=CHANNEL_ID).execute()
    ch = resp["items"][0]
    print(f"   ✓ Channel: {ch['snippet']['title']}")
    print(f"   ✓ Subscribers: {int(ch['statistics']['subscriberCount']):,}")
    print(f"   ✓ Total views: {int(ch['statistics']['viewCount']):,}")
    print(f"   ✓ Video count: {ch['statistics']['videoCount']}")
except Exception as e:
    print(f"   ✗ Data API failed: {e}")

# ── Test 2: YouTube Analytics API (private channel metrics) ──
print("\n3. YouTube Analytics API — last 7 days views...")
try:
    yt_analytics = build_api("youtubeAnalytics", "v2", credentials=creds)
    from datetime import datetime, timedelta
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    resp = yt_analytics.reports().query(
        ids="channel==MINE",
        startDate=start, endDate=end,
        metrics="views,estimatedMinutesWatched",
        dimensions="day", sort="day").execute()
    rows = resp.get("rows", [])
    print(f"   ✓ Got {len(rows)} days of data")
    for row in rows:
        print(f"     {row[0]}: {row[1]:,} views, {round(row[2]/60,1)} hrs watch time")
except Exception as e:
    print(f"   ✗ Analytics API failed: {e}")

print("\n" + "=" * 50)
print("Done. If both checks show ✓, you're good to go.")
print("=" * 50)