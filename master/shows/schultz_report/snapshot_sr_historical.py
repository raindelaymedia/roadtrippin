"""
The Schultz Report — Historical Snapshot
One-time script to capture all channel data BEFORE RDM management (Aug 19, 2026).
Saves to data/sr_historical_snapshot.json — reference baseline, not actively tracked.

Usage:
    python snapshot_sr_historical.py
"""

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from dateutil.relativedelta import relativedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as build_api

from config_sr import (
    YT_CHANNEL_ID    as CHANNEL_ID,
    YT_CLIENT_ID     as CLIENT_ID,
    YT_CLIENT_SECRET as CLIENT_SECRET,
    YT_REFRESH_TOKEN as REFRESH_TOKEN,
)

RDM_START = "2026-08-18"  # anything before this = "pre-RDM"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data_sr")
os.makedirs(DATA_DIR, exist_ok=True)


def authenticate():
    creds = Credentials(
        token=None, refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.readonly"])
    creds.refresh(Request())
    return creds


def iso_dur_to_sec(iso):
    if not iso: return 0
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m: return 0
    return int(m.group(1) or 0)*3600 + int(m.group(2) or 0)*60 + int(m.group(3) or 0)


def main():
    print("=" * 55)
    print("SCHULTZ REPORT — HISTORICAL SNAPSHOT")
    print(f"Capturing all data before RDM start: {RDM_START}")
    print("=" * 55)

    creds = authenticate()
    youtube = build_api("youtube", "v3", credentials=creds)
    yt_analytics = build_api("youtubeAnalytics", "v2", credentials=creds)

    # ── Channel info ──
    print("\n[1/5] Channel info...")
    ch_resp = youtube.channels().list(part="snippet,statistics", id=CHANNEL_ID).execute()
    ch = ch_resp["items"][0]
    channel_info = {
        "title": ch["snippet"]["title"],
        "subscribers": int(ch["statistics"]["subscriberCount"]),
        "total_views": int(ch["statistics"]["viewCount"]),
        "video_count": int(ch["statistics"]["videoCount"]),
        "created": ch["snippet"]["publishedAt"],
        "snapshot_date": datetime.now().isoformat(),
    }
    print(f"  ✓ {channel_info['title']}: {channel_info['subscribers']:,} subs, {channel_info['total_views']:,} views")

    # ── Monthly analytics (as far back as API allows → Aug 18 2026) ──
    print("\n[2/5] Monthly analytics...")
    # API goes back ~22 months from today
    api_start = (datetime.now() - relativedelta(months=22)).replace(day=1).strftime("%Y-%m-%d")
    api_end = "2026-08-01"
    print(f"  Range: {api_start} → {api_end}")

    # Total monthly views + subs
    resp = yt_analytics.reports().query(
        ids=f"channel==MINE", startDate=api_start, endDate=api_end,
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
        dimensions="month", sort="month").execute()
    monthly = {}
    for row in resp.get("rows", []):
        monthly[row[0]] = {
            "views": row[1], "watch_hrs": round(row[2]/60, 1),
            "subs_gained": row[3], "subs_lost": row[4],
        }
    print(f"  ✓ Monthly totals: {len(monthly)} months")

    # Views by content type
    resp = yt_analytics.reports().query(
        ids=f"channel==MINE", startDate=api_start, endDate=api_end,
        metrics="views,estimatedMinutesWatched",
        dimensions="month,creatorContentType", sort="month").execute()
    KEY_MAP = {"videoOnDemand": "vod", "shorts": "shorts", "liveStream": "live"}
    content_type = defaultdict(dict)
    for row in resp.get("rows", []):
        key = KEY_MAP.get(row[1], row[1])
        content_type[row[0]][key] = row[2]
    content_type = dict(content_type)
    print(f"  ✓ Content types: {len(content_type)} months")

    # ── Daily analytics (last 90 days before RDM, or as much as available) ──
    print("\n[3/5] Daily analytics (pre-RDM window)...")
    daily_start = "2026-05-19"  # ~3 months before RDM start
    daily_end = "2026-08-18"
    resp = yt_analytics.reports().query(
        ids=f"channel==MINE", startDate=daily_start, endDate=daily_end,
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
        dimensions="day", sort="day").execute()
    daily = {}
    for row in resp.get("rows", []):
        daily[row[0]] = {"views": row[1], "watch_hrs": round(row[2]/60, 1),
                         "subs_gained": row[3], "subs_lost": row[4]}
    print(f"  ✓ Daily data: {len(daily)} days")

    # ── All videos (Data API — full uploads walk) ──
    print("\n[4/5] Walking all uploads...")
    ch_detail = youtube.channels().list(part="contentDetails", id=CHANNEL_ID).execute()
    uploads_id = ch_detail["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    all_videos = []
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails,snippet", playlistId=uploads_id,
            maxResults=50, pageToken=next_page).execute()
        video_ids = [it["contentDetails"]["videoId"] for it in resp["items"]]
        if not video_ids:
            break

        details = youtube.videos().list(
            part="snippet,statistics,contentDetails", id=",".join(video_ids)).execute()
        for v in details.get("items", []):
            pub = v["snippet"].get("publishedAt", "")
            dur_sec = iso_dur_to_sec(v.get("contentDetails", {}).get("duration", ""))
            stats = v.get("statistics", {})

            # Classify: short (<=180s), mid (3-30min), long (>30min)
            if dur_sec <= 180:
                vtype = "short"
            elif dur_sec <= 1800:
                vtype = "mid"
            else:
                vtype = "long"

            # Flag pre-RDM vs post-RDM
            is_pre_rdm = pub < f"{RDM_START}T00:00:00Z"

            all_videos.append({
                "id": v["id"],
                "title": v["snippet"].get("title", ""),
                "published": pub[:10],
                "month": pub[:7],
                "duration_sec": dur_sec,
                "type": vtype,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "pre_rdm": is_pre_rdm,
            })

        next_page = resp.get("nextPageToken")
        if not next_page:
            break

    pre_rdm = [v for v in all_videos if v["pre_rdm"]]
    post_rdm = [v for v in all_videos if not v["pre_rdm"]]
    print(f"  ✓ Total videos: {len(all_videos)} ({len(pre_rdm)} pre-RDM, {len(post_rdm)} post-RDM)")

    # Top 20 pre-RDM videos by views
    top_pre = sorted(pre_rdm, key=lambda x: x["views"], reverse=True)[:20]
    print(f"  Top pre-RDM video: {top_pre[0]['views']:,} views — {top_pre[0]['title'][:60]}" if top_pre else "  No pre-RDM videos found")

    # ── Summary stats ──
    print("\n[5/5] Computing summary...")
    pre_rdm_views = sum(v["views"] for v in pre_rdm)
    pre_rdm_shorts = [v for v in pre_rdm if v["type"] == "short"]
    pre_rdm_longs = [v for v in pre_rdm if v["type"] == "long"]
    pre_rdm_mids = [v for v in pre_rdm if v["type"] == "mid"]

    summary = {
        "total_videos_pre_rdm": len(pre_rdm),
        "total_views_pre_rdm": pre_rdm_views,
        "shorts_count": len(pre_rdm_shorts),
        "mids_count": len(pre_rdm_mids),
        "longs_count": len(pre_rdm_longs),
        "avg_views_per_video": round(pre_rdm_views / len(pre_rdm)) if pre_rdm else 0,
        "top_20_videos": top_pre,
    }
    print(f"  Pre-RDM: {len(pre_rdm)} videos, {pre_rdm_views:,} total views")
    print(f"  Breakdown: {len(pre_rdm_longs)} long / {len(pre_rdm_mids)} mid / {len(pre_rdm_shorts)} short")
    print(f"  Avg views/video: {summary['avg_views_per_video']:,}")

    # ── Save ──
    snapshot = {
        "snapshot_date": datetime.now().isoformat(),
        "rdm_start_date": RDM_START,
        "channel": channel_info,
        "monthly_analytics": monthly,
        "monthly_content_type": content_type,
        "daily_pre_rdm": daily,
        "all_videos": all_videos,
        "summary": summary,
    }

    out_path = os.path.join(DATA_DIR, "sr_historical_snapshot.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)

    print(f"\n✓ Saved: {out_path}")
    print(f"  {os.path.getsize(out_path) / 1024:.0f} KB")
    print("=" * 55)


if __name__ == "__main__":
    main()