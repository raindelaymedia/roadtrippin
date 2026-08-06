#!/usr/bin/env python3
"""
channel_baselines.py — Pull normalizing data for each channel:
  • Subscriber count (current)
  • Total video count (current)
  • Median + mean views of the last N non-live VODs (default 50)

Used to compute "successful live" relative metrics:
  • Live views as % of subscribers (audience penetration)
  • Live views vs. channel's own VOD baseline (does this live beat the channel's usual content?)
  • Live engagement rate vs. channel's VOD engagement baseline

Output: data/channel_baselines.csv with one row per channel.

Run from master/shows/road_trippin/:
    python channel_baselines.py
    python channel_baselines.py --vod-sample 100   # use last 100 VODs per channel for baseline

Quota cost: ~20–50 units total. Negligible.
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
except ImportError:
    print("Missing deps. Install with: pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

try:
    from config import YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, YT_CHANNEL_ID as CHANNEL_ID
except ImportError:
    print("config.py not found — run from master/shows/road_trippin/")
    sys.exit(1)


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
    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def channel_facts(yt, channel_id=None, handle=None):
    """Get subscriber count, total video count, and uploads playlist ID."""
    if channel_id:
        resp = yt.channels().list(part="statistics,contentDetails,snippet", id=channel_id).execute()
    elif handle:
        resp = yt.channels().list(part="statistics,contentDetails,snippet", forHandle=handle).execute()
    else:
        return None
    items = resp.get("items", [])
    if not items:
        return None
    it = items[0]
    return {
        "channel_id":       it["id"],
        "channel_title":    it["snippet"]["title"],
        "subs":             int(it["statistics"].get("subscriberCount", 0)),
        "total_videos":     int(it["statistics"].get("videoCount",      0)),
        "uploads_playlist": it["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def vod_baseline(yt, uploads_playlist, sample_size):
    """Walk the uploads playlist, skip lives, return view stats of the next
    `sample_size` non-live VODs found."""
    vod_views, vod_likes, vod_comments = [], [], []
    next_page = None
    while len(vod_views) < sample_size:
        try:
            resp = yt.playlistItems().list(
                part="contentDetails", playlistId=uploads_playlist,
                maxResults=50, pageToken=next_page,
            ).execute()
        except Exception as e:
            print(f"    ✗ playlist page failed: {e}")
            break
        ids = [it["contentDetails"]["videoId"] for it in resp.get("items", [])]
        if not ids:
            break
        try:
            details = yt.videos().list(
                part="statistics,liveStreamingDetails", id=",".join(ids),
            ).execute()
        except Exception as e:
            print(f"    ✗ video detail failed: {e}")
            break
        for v in details.get("items", []):
            # Skip if this was a live stream (we want VOD baseline)
            lsd = v.get("liveStreamingDetails") or {}
            if lsd.get("actualStartTime"):
                continue
            stats = v.get("statistics", {})
            vw = int(stats.get("viewCount", 0))
            if vw < 1:
                continue
            vod_views.append(vw)
            vod_likes.append(int(stats.get("likeCount", 0)))
            vod_comments.append(int(stats.get("commentCount", 0)))
            if len(vod_views) >= sample_size:
                break
        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    if not vod_views:
        return None

    def median(xs):
        s = sorted(xs); n = len(s)
        return s[n//2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2

    n = len(vod_views)
    engagement = [(l + c) / v for v, l, c in zip(vod_views, vod_likes, vod_comments) if v]
    return {
        "vod_n":            n,
        "vod_median_views": int(median(vod_views)),
        "vod_mean_views":   int(sum(vod_views) / n),
        "vod_median_eng":   round(median(engagement), 4) if engagement else 0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vod-sample", type=int, default=50,
                    help="How many recent non-live VODs to sample per channel (default: 50)")
    ap.add_argument("--output", default="data/channel_baselines.csv")
    args = ap.parse_args()

    yt = yt_client()
    rows = []
    print("=" * 60)
    print("CHANNEL BASELINES — gathering normalizing data")
    print("=" * 60)

    for name, handle, cid in CHANNELS:
        print(f"\n[{name}]")
        facts = channel_facts(yt, channel_id=cid, handle=handle)
        if not facts:
            print(f"  ✗ couldn't resolve")
            continue
        print(f"  ✓ {facts['subs']:>9,} subs · {facts['total_videos']:>5,} videos total")
        baseline = vod_baseline(yt, facts['uploads_playlist'], args.vod_sample)
        if baseline:
            print(f"  ✓ VOD baseline (last {baseline['vod_n']} non-lives): "
                  f"median {baseline['vod_median_views']:,} views, "
                  f"engagement {baseline['vod_median_eng']*100:.2f}%")
        else:
            print(f"  ⚠ no VOD baseline could be computed")
            baseline = {"vod_n": 0, "vod_median_views": 0, "vod_mean_views": 0, "vod_median_eng": 0}
        rows.append({
            "channel_name":     name,
            **{k: facts[k] for k in ('channel_id','channel_title','subs','total_videos')},
            **baseline,
        })

    if not rows:
        print("\nNo data — exiting")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    print("\n" + "=" * 60)
    print(f"✓ Wrote {len(rows)} channel baselines → {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()