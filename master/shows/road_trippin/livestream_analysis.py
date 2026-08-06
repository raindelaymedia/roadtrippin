#!/usr/bin/env python3
"""
livestream_analysis.py — One-shot pull of live-stream metadata across
Road Trippin' and a set of comparable basketball-podcast channels.

What it does:
  • Resolves each @handle to a YouTube channel ID
  • Walks each channel's uploads playlist back N months (default 24)
  • Keeps only videos that actually streamed live (have actualStartTime)
  • For each live: timing (UTC + ET + day-of-week + hour), duration,
    views, likes, comments
  • Writes one CSV with every live across every channel for analysis

Run from the same directory as config.py:
    cd master/shows/road_trippin
    python livestream_analysis.py
    python livestream_analysis.py --months 36
    python livestream_analysis.py --output data/lives_2025.csv

Quota cost: ~150–500 units total, one-time (well under the 10K daily limit).
"""

import argparse
import csv
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
except ImportError:
    print("Missing dependencies. Install with:")
    print("  pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

try:
    from config import YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, YT_CHANNEL_ID as CHANNEL_ID
except ImportError:
    print("config.py not found — run this from master/shows/road_trippin/")
    sys.exit(1)


# ─── Channels to analyze ──────────────────────────────────────────────────
# (display name, @handle for API resolution, hard-coded channel ID if known)
# Road Trippin' uses the channel ID already in config so we save one API call.
CHANNELS = [
    ("Road Trippin'",             None,                       CHANNEL_ID),
    ("All The Smoke",             "AllTheSmokeProductions",   None),
    ("7PM in Brooklyn",           "7PMinBrooklyn",            None),
    ("The Old Man and the Three", "OLDMANANDTHREE",           None),
    ("Run It Back",               "RunItBackFDTV",            None),
    ("The Draymond Green Show",   "DraymondGreenShow",        None),
    ("Gil's Arena",               "TheArena0",                None),
]


def yt_client():
    """Build an authenticated YouTube Data API client using config.py creds."""
    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def resolve_handle(yt, handle):
    """Look up a channel ID from an @handle."""
    try:
        resp = yt.channels().list(part="id,snippet", forHandle=handle).execute()
    except Exception as e:
        print(f"  ✗ failed to resolve @{handle}: {e}")
        return None
    items = resp.get("items", [])
    if not items:
        print(f"  ✗ no channel found for @{handle}")
        return None
    cid = items[0]["id"]
    print(f"  ✓ @{handle} → {cid}  ({items[0]['snippet']['title']})")
    return cid


def uploads_playlist(yt, channel_id):
    """Get the uploads playlist ID for a channel."""
    resp = yt.channels().list(part="contentDetails", id=channel_id).execute()
    items = resp.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
def iso_duration_to_sec(iso):
    """PT1H30M5S → 5405 seconds."""
    if not iso:
        return 0
    m = _DUR_RE.match(iso)
    if not m:
        return 0
    h, mn, s = m.groups()
    return int(h or 0) * 3600 + int(mn or 0) * 60 + int(s or 0)


def to_et(iso_utc):
    """Parse a YouTube ISO timestamp into an Eastern Time datetime (DST-aware)."""
    if not iso_utc:
        return None
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York"))
    except ImportError:
        # Fallback: rough EST (UTC-5) without DST correction
        return dt.astimezone(timezone(timedelta(hours=-5)))


def pull_lives(yt, channel_name, channel_id, since_iso):
    """Walk a channel's uploads playlist back to `since_iso` and return
    a list of dicts, one per actual live stream."""
    uploads_id = uploads_playlist(yt, channel_id)
    if not uploads_id:
        return []

    lives, next_page = [], None
    pages_walked = 0
    while True:
        try:
            resp = yt.playlistItems().list(
                part="contentDetails,snippet",
                playlistId=uploads_id,
                maxResults=50,
                pageToken=next_page,
            ).execute()
        except Exception as e:
            print(f"  ✗ pagination failed: {e}")
            break
        pages_walked += 1

        ids = [it["contentDetails"]["videoId"] for it in resp.get("items", [])]
        if not ids:
            break

        try:
            details = yt.videos().list(
                part="snippet,statistics,liveStreamingDetails,contentDetails",
                id=",".join(ids),
            ).execute()
        except Exception as e:
            print(f"  ✗ video detail fetch failed: {e}")
            break

        stop = False
        for v in details.get("items", []):
            pub = v["snippet"].get("publishedAt", "")
            if pub and pub < since_iso:
                stop = True
                continue
            lsd = v.get("liveStreamingDetails") or {}
            actual_start = lsd.get("actualStartTime")
            if not actual_start:
                continue  # not a live stream (or it never went live)

            start_et = to_et(actual_start)
            lives.append({
                "channel_name":       channel_name,
                "channel_id":         channel_id,
                "video_id":           v["id"],
                "title":              v["snippet"].get("title", ""),
                "published_at":       pub,
                "actual_start_utc":   actual_start,
                "actual_end_utc":     lsd.get("actualEndTime", ""),
                "scheduled_start_utc": lsd.get("scheduledStartTime", ""),
                "start_et":           start_et.isoformat() if start_et else "",
                "day_of_week":        start_et.strftime("%a") if start_et else "",
                "hour_et":            start_et.hour if start_et is not None else "",
                "duration_sec":       iso_duration_to_sec(v.get("contentDetails", {}).get("duration", "")),
                "views":              int(v.get("statistics", {}).get("viewCount",    0)),
                "likes":              int(v.get("statistics", {}).get("likeCount",    0)),
                "comments":           int(v.get("statistics", {}).get("commentCount", 0)),
                "url":                f"https://youtu.be/{v['id']}",
            })

        next_page = resp.get("nextPageToken")
        if stop or not next_page:
            break
        if pages_walked > 200:
            print(f"  ⚠ stopped at 200 pages (safety cap)")
            break

    return lives


def main():
    ap = argparse.ArgumentParser(description="Pull live-stream data for RT + competitors.")
    ap.add_argument("--months", type=int, default=24,
                    help="How many months of history to include (default: 24)")
    ap.add_argument("--output", default="data/livestream_analysis.csv",
                    help="Output CSV path (default: data/livestream_analysis.csv)")
    args = ap.parse_args()

    since = datetime.now(timezone.utc) - timedelta(days=args.months * 30)
    since_iso = since.isoformat()

    print("=" * 60)
    print("LIVESTREAM ANALYSIS — data gathering")
    print("=" * 60)
    print(f"Window:   last {args.months} months ({since.strftime('%Y-%m-%d')} → today)")
    print(f"Channels: {len(CHANNELS)}")
    print()

    yt = yt_client()

    all_lives = []
    summary = []
    for name, handle, cid in CHANNELS:
        print(f"[{name}]")
        if cid is None:
            cid = resolve_handle(yt, handle)
            if not cid:
                summary.append((name, "—", 0))
                continue
        lives = pull_lives(yt, name, cid, since_iso)
        print(f"  ✓ {len(lives)} lives pulled")
        summary.append((name, cid, len(lives)))
        all_lives.extend(lives)

    if not all_lives:
        print("\nNo lives found across any channel. Check credentials + handles.")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(all_lives[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_lives)

    print()
    print("=" * 60)
    print(f"✓ Wrote {len(all_lives):,} lives → {out_path}")
    print("=" * 60)
    print()
    print(f"{'Channel':<32}{'Lives':>8}{'Channel ID':>30}")
    print("-" * 70)
    for name, cid, n in sorted(summary, key=lambda x: -x[2]):
        print(f"{name:<32}{n:>8}  {cid}")


if __name__ == "__main__":
    main()