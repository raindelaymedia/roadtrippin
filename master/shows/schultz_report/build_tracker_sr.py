"""
The Schultz Report — Analytics Tracker Builder
Same architecture as RT's build_tracker.py, stripped down:
  - YouTube Analytics API (monthly + daily + content types)
  - YouTube Data API (subs, shorts count, top content, all videos)
  - No Megaphone / audio (not a podcast)
  - No Fanatics-specific logic
  - Tracks from RDM start date (Aug 19, 2026) forward

Usage:
    python build_tracker_sr.py
    python build_tracker_sr.py --months 12

Requirements:
    pip install google-auth google-auth-oauthlib google-api-python-client python-dateutil
"""

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
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

RDM_START = "2026-08-18"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data_sr")
os.makedirs(DATA_DIR, exist_ok=True)


# ─── Helpers ─────────────────────────────────────────────────────

def get_month_keys(n=12):
    now = datetime.now().replace(day=1)
    return [(now - relativedelta(months=i)).strftime("%Y-%m") for i in range(n)]


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


def _clean(v):
    if v is None: return None
    if isinstance(v, (int, float)): return v
    s = str(v).strip()
    if s in ('N/A', '—', '', 'None'): return None
    try: return float(s.replace(',', '')) if '.' in s else int(s.replace(',', ''))
    except: return s


# ─── YouTube Analytics API ───────────────────────────────────────

def pull_monthly(yt_analytics, start, end):
    resp = yt_analytics.reports().query(
        ids=f"channel==MINE", startDate=start, endDate=end,
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
        dimensions="month", sort="month").execute()
    data = {}
    for row in resp.get("rows", []):
        data[row[0]] = {"views": row[1], "watch_hrs": round(row[2]/60, 1),
                        "subs_gained": row[3], "subs_lost": row[4]}
    return data


def pull_content_type(yt_analytics, start, end):
    resp = yt_analytics.reports().query(
        ids=f"channel==MINE", startDate=start, endDate=end,
        metrics="views,estimatedMinutesWatched",
        dimensions="month,creatorContentType", sort="month").execute()
    KEY_MAP = {"videoOnDemand": "VIDEO_ON_DEMAND", "shorts": "SHORTS", "liveStream": "LIVE_STREAM"}
    data = defaultdict(lambda: {"VIDEO_ON_DEMAND": 0, "SHORTS": 0, "LIVE_STREAM": 0})
    for row in resp.get("rows", []):
        key = KEY_MAP.get(row[1], row[1])
        data[row[0]][key] = data[row[0]].get(key, 0) + row[2]
    return dict(data)


def pull_daily(yt_analytics, start, end):
    resp = yt_analytics.reports().query(
        ids=f"channel==MINE", startDate=start, endDate=end,
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
        dimensions="day", sort="day").execute()
    data = {}
    for row in resp.get("rows", []):
        data[row[0]] = {"total_views": row[1], "watch_hrs": round(row[2]/60, 1),
                        "subs_gained": row[3], "subs_lost": row[4]}
    return data


def pull_daily_content_type(yt_analytics, start, end):
    resp = yt_analytics.reports().query(
        ids=f"channel==MINE", startDate=start, endDate=end,
        metrics="views",
        dimensions="day,creatorContentType", sort="day").execute()
    KEY_MAP = {"videoOnDemand": "vod_views", "shorts": "shorts_views", "liveStream": "live_views"}
    data = defaultdict(dict)
    for row in resp.get("rows", []):
        key = KEY_MAP.get(row[1])
        if key:
            data[row[0]][key] = data[row[0]].get(key, 0) + row[2]
    return dict(data)


def pull_subscriber_total(youtube):
    resp = youtube.channels().list(part="statistics", id=CHANNEL_ID).execute()
    return int(resp["items"][0]["statistics"].get("subscriberCount", 0))


def pull_shorts_count(youtube):
    ch = youtube.channels().list(part="contentDetails", id=CHANNEL_ID).execute()
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    counts = defaultdict(int)
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_id,
            maxResults=50, pageToken=next_page).execute()
        video_ids = [it["contentDetails"]["videoId"] for it in resp["items"]]
        details = youtube.videos().list(
            part="contentDetails,snippet", id=",".join(video_ids)).execute()
        for vid in details["items"]:
            dur = vid.get("contentDetails", {}).get("duration", "")
            if not dur: continue
            sec = iso_dur_to_sec(dur)
            if sec <= 180:
                pub_month = vid["snippet"]["publishedAt"][:7]
                counts[pub_month] += 1
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return dict(counts)


def pull_traffic_sources(yt_analytics, start, end):
    """Pull full traffic source breakdown per month via Analytics API.
    Returns dict keyed by month with source percentages and paid vs organic split.
    
    Key sources the API returns:
      ADVERTISING / PROMOTED  = paid promotion
      YT_SEARCH              = YouTube search (organic)
      SUGGESTED / RELATED    = suggested/related videos (organic)
      BROWSE                 = browse features / home (organic)
      EXT_URL                = external websites
      SUBSCRIBER             = subscriber feed
      NOTIFICATION           = push notifications
      PLAYLIST / YT_PLAYLIST = playlist plays
      NO_LINK_OTHER          = direct/unknown
    """
    data = {}

    try:
        resp = yt_analytics.reports().query(
            ids=f"channel==MINE", startDate=start, endDate=end,
            metrics="views",
            dimensions="day,insightTrafficSourceType", sort="day").execute()

        monthly = defaultdict(lambda: defaultdict(int))
        for row in resp.get("rows", []):
            day, source, views = row[0], row[1], row[2]
            month = day[:7]  # YYYY-MM-DD → YYYY-MM
            monthly[month][source] += views

        PAID_SOURCES = {"ADVERTISING", "PROMOTED"}
        ORGANIC_SEARCH = {"YT_SEARCH"}
        ORGANIC_SUGGESTED = {"SUGGESTED", "RELATED_VIDEO", "RELATED"}
        ORGANIC_BROWSE = {"BROWSE", "BROWSE_FEATURES"}

        for m, sources in monthly.items():
            total = sum(sources.values())
            if total == 0:
                continue

            paid = sum(v for s, v in sources.items() if s in PAID_SOURCES)
            search = sum(v for s, v in sources.items() if s in ORGANIC_SEARCH)
            suggested = sum(v for s, v in sources.items() if s in ORGANIC_SUGGESTED)
            browse = sum(v for s, v in sources.items() if s in ORGANIC_BROWSE)
            organic = total - paid

            data[m] = {
                "total_views":    total,
                "paid_views":     paid,
                "organic_views":  organic,
                "paid_pct":       round(paid / total, 4) if total else None,
                "organic_pct":    round(organic / total, 4) if total else None,
                "search_views":   search,
                "search_pct":     round(search / total, 4) if total else None,
                "suggested_views": suggested,
                "suggested_pct":  round(suggested / total, 4) if total else None,
                "browse_views":   browse,
                "browse_pct":     round(browse / total, 4) if total else None,
                # Full breakdown for reference
                "sources":        dict(sources),
            }
    except Exception as e:
        print(f"  ⚠ Traffic sources failed: {e}")

    return data


def pull_top_content(youtube, months, top_n=10):
    """Walk uploads, classify, return top N per type per month + full video list."""
    oldest = min(months) if months else "1970-01"
    cutoff = f"{oldest}-01T00:00:00Z"

    ch = youtube.channels().list(part="contentDetails", id=CHANNEL_ID).execute()
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = []
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails,snippet", playlistId=uploads_id,
            maxResults=50, pageToken=next_page).execute()
        video_ids = [it["contentDetails"]["videoId"] for it in resp["items"]]
        if not video_ids: break

        details = youtube.videos().list(
            part="snippet,statistics,contentDetails", id=",".join(video_ids)).execute()

        stop = False
        for v in details.get("items", []):
            pub = v["snippet"].get("publishedAt", "")
            if pub and pub < cutoff:
                stop = True
                continue
            dur = iso_dur_to_sec(v.get("contentDetails", {}).get("duration", ""))
            stats = v.get("statistics", {})
            vtype = "short" if dur <= 180 else ("mid" if dur <= 1800 else "long")

            videos.append({
                "id": v["id"],
                "title": v["snippet"].get("title", ""),
                "published": pub[:10],
                "month": pub[:7],
                "type": vtype,
                "duration_sec": dur,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "thumbnail": v["snippet"].get("thumbnails", {}).get("high", {}).get("url", ""),
            })

        next_page = resp.get("nextPageToken")
        if stop or not next_page:
            break

    # Bucket by month + type, keep top N
    top = {}
    for m in months:
        month_vids = [v for v in videos if v["month"] == m]
        top[m] = {}
        for t in ("long", "mid", "short"):
            typed = sorted([v for v in month_vids if v["type"] == t],
                           key=lambda x: x["views"], reverse=True)
            top[m][t] = typed[:top_n]

    return top, videos


def pull_best_of(youtube, months, n_months=1):
    """Current month's best-performing content by type."""
    target = months[:n_months]
    ch = youtube.channels().list(part="contentDetails", id=CHANNEL_ID).execute()
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    oldest = min(target) if target else datetime.now().strftime("%Y-%m")
    cutoff = f"{oldest}-01T00:00:00Z"

    videos = []
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_id,
            maxResults=50, pageToken=next_page).execute()
        ids = [it["contentDetails"]["videoId"] for it in resp["items"]]
        if not ids: break
        details = youtube.videos().list(
            part="snippet,statistics,contentDetails", id=",".join(ids)).execute()
        stop = False
        for v in details.get("items", []):
            pub = v["snippet"].get("publishedAt", "")
            if pub < cutoff:
                stop = True
                continue
            if pub[:7] not in target:
                continue
            dur = iso_dur_to_sec(v.get("contentDetails", {}).get("duration", ""))
            stats = v.get("statistics", {})
            vtype = "short" if dur <= 180 else ("mid" if dur <= 1800 else "long")
            videos.append({
                "id": v["id"], "title": v["snippet"].get("title", ""),
                "published": pub[:10], "type": vtype,
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "thumbnail": v["snippet"].get("thumbnails", {}).get("high", {}).get("url", ""),
            })
        next_page = resp.get("nextPageToken")
        if stop or not next_page:
            break

    result = {}
    for t in ("long", "mid", "short"):
        typed = sorted([v for v in videos if v["type"] == t],
                       key=lambda x: x["views"], reverse=True)
        result[t] = typed[:5]
    return result


# ─── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="The Schultz Report — Analytics Tracker")
    parser.add_argument("--months", type=int, default=12)
    args = parser.parse_args()

    print("=" * 55)
    print("THE SCHULTZ REPORT — ANALYTICS TRACKER")
    print("=" * 55)

    months = get_month_keys(args.months)
    print(f"Months: {months[0]} → {months[-1]} ({len(months)} months)")

    print("\n[1/2] YouTube APIs...")
    creds = authenticate()
    youtube = build_api("youtube", "v3", credentials=creds)
    yt_analytics = build_api("youtubeAnalytics", "v2", credentials=creds)

    start = f"{months[-1]}-01"
    end = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    print(f"  Date range: {start} → {end}")

    # Monthly totals
    print("  Pulling monthly totals...")
    yt_monthly = pull_monthly(yt_analytics, start, end)
    print(f"  ✓ Monthly: {len(yt_monthly)} months")

    # Content types
    print("  Pulling content types...")
    yt_content = pull_content_type(yt_analytics, start, end)
    print(f"  ✓ Content types: {len(yt_content)} months")

    # Daily (last 90 days)
    print("  Pulling daily data (last 90 days)...")
    daily_end = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    daily_start = (datetime.now() - timedelta(days=91)).strftime("%Y-%m-%d")
    daily_totals = pull_daily(yt_analytics, daily_start, daily_end)
    daily_types = pull_daily_content_type(yt_analytics, daily_start, daily_end)
    daily_yt = {}
    for day in sorted(set(daily_totals.keys()) | set(daily_types.keys())):
        entry = {}
        entry.update(daily_totals.get(day, {}))
        entry.update(daily_types.get(day, {}))
        daily_yt[day] = entry
    print(f"  ✓ Daily: {len(daily_yt)} days")

    # Subscribers
    current_subs = pull_subscriber_total(youtube)
    print(f"  ✓ Subscribers: {current_subs:,}")

    # Shorts count
    print("  Counting Shorts by month...")
    shorts_count = pull_shorts_count(youtube)
    print(f"  ✓ Shorts count: {len(shorts_count)} months")

    # Top content
    print("  Pulling top content monthly...")
    top_content_monthly, all_videos = pull_top_content(youtube, months)
    total_tc = sum(sum(len(b) for b in v.values()) for v in top_content_monthly.values())
    print(f"  ✓ Top content: {total_tc} videos across {len(top_content_monthly)} months ({len(all_videos)} total)")

    # Best of (current month)
    print("  Pulling Best Of...")
    now = datetime.now()
    best_of_label = f"{now.strftime('%b')} {now.year}"
    best_of = pull_best_of(youtube, months, n_months=1)
    total_best = sum(len(v) for v in best_of.values())
    print(f"  ✓ Best Of: {total_best} videos")

    # Traffic sources (paid vs organic — critical for SR)
    print("  Pulling traffic sources (paid vs organic)...")
    traffic = pull_traffic_sources(yt_analytics, start, end)
    if traffic:
        latest = sorted(traffic.keys())[-1]
        t = traffic[latest]
        print(f"  ✓ Traffic sources: {len(traffic)} months")
        print(f"    Latest ({latest}): {t.get('organic_pct',0)*100:.1f}% organic, {t.get('paid_pct',0)*100:.1f}% paid")
        if t.get('sources'):
            top_sources = sorted(t['sources'].items(), key=lambda x: x[1], reverse=True)[:5]
            for src, views in top_sources:
                print(f"      {src}: {views:,} views ({views/t['total_views']*100:.1f}%)")
    else:
        print(f"  ⚠ No traffic source data returned")

    # ── Build tracker JSON ──
    print("\n[2/2] Building tracker_data_sr.json...")

    tracker = {
        "generated": datetime.now().isoformat(),
        "rdm_start": RDM_START,
        "months": months,
        "yt": {
            "vids":        {m: _clean(yt_content.get(m, {}).get("VIDEO_ON_DEMAND")) for m in months},
            "shorts":      {m: _clean(yt_content.get(m, {}).get("SHORTS"))          for m in months},
            "lives":       {m: _clean(yt_content.get(m, {}).get("LIVE_STREAM"))     for m in months},
            "subs_gained": {m: _clean(yt_monthly.get(m, {}).get("subs_gained"))     for m in months},
            "subs_lost":   {m: _clean(yt_monthly.get(m, {}).get("subs_lost"))       for m in months},
        },
        "audio": {
            "downloads": {m: None for m in months},
            "streams":   {m: None for m in months},
            "episodes":  {m: None for m in months},
        },
        "kpis": {
            "shorts_count": {m: shorts_count.get(m) for m in months},
            "search_pct":   {m: traffic.get(m, {}).get("search_pct") for m in months},
        },
        "traffic": {
            # Per-month paid vs organic breakdown — key metric for SR
            "paid_pct":      {m: traffic.get(m, {}).get("paid_pct") for m in months},
            "organic_pct":   {m: traffic.get(m, {}).get("organic_pct") for m in months},
            "paid_views":    {m: traffic.get(m, {}).get("paid_views") for m in months},
            "organic_views": {m: traffic.get(m, {}).get("organic_views") for m in months},
            "search_pct":    {m: traffic.get(m, {}).get("search_pct") for m in months},
            "suggested_pct": {m: traffic.get(m, {}).get("suggested_pct") for m in months},
            "browse_pct":    {m: traffic.get(m, {}).get("browse_pct") for m in months},
            # Full source breakdown per month for deep dives
            "sources":       {m: traffic.get(m, {}).get("sources") for m in months},
        },
        "best_of": {
            "label": best_of_label,
            "long":  best_of.get("long", []),
            "mid":   best_of.get("mid", []),
            "short": best_of.get("short", []),
        },
        "audience": {
            "eps":   {m: None for m in months},
            "vods":  {m: None for m in months},
            "lives": {m: None for m in months},
        },
        "top_content_monthly": top_content_monthly,
        "all_videos":          all_videos,
        "current_subs":        current_subs,
        "daily_yt":            daily_yt,
    }

    json_out = os.path.join(DATA_DIR, "tracker_data_sr.json")
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, default=str)

    print(f"\n✓ Saved: {json_out}")
    print(f"  {os.path.getsize(json_out) / 1024:.0f} KB")
    print("=" * 55)


if __name__ == "__main__":
    main()