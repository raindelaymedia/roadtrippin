#!/usr/bin/env python3
"""
pull_video_features.py — Per-video feature + growth-attribution pull for the
Live vs VOD growth-strategy research.

For every RT video published in the two eras under comparison:
    VOD era:  2025-07-01 → 2025-12-31
    Live era: 2026-01-01 → 2026-06-30
this pulls:
  - Content type: episode (Full Episodes playlist) / live (liveStreamingDetails,
    same test-broadcast filtering as build_tracker.py's pull_live_counts) /
    short (<3min) / vod (everything else — mid-length clips)
  - Simple, objective title features: character length, word count, caps
    ratio, has "!", has "?" — deliberately avoids hand-picked hype-keyword
    lists, which would be noisy/overfit at this sample size
  - Publish timing: day of week, hour (ET)
  - Growth attribution: subscribersGained, subscribersLost, and views —
    each in a FIXED window after publish (default 28 days), not lifetime-
    to-date. This matters: without a fixed window, older videos would look
    like better subscriber-drivers just because they've had more time to
    accumulate — the same age-bias problem the Live vs VOD deep dive found
    with lifetime views vs first-24hr views.

Cost note: subscriber attribution needs ONE Analytics API call per video
(each video has its own publish-date-anchored window, so these can't be
batched the way Data API pulls can). Scoped to the two eras (~600-700
videos) rather than full history — expect this to take a few minutes.

Videos published within `--window-days` of today are skipped (their
attribution window hasn't fully elapsed yet) and reported at the end.

Run from master/shows/road_trippin/:
    python pull_video_features.py
    python pull_video_features.py --window-days 14
    python pull_video_features.py --output data/video_growth_features.csv
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

# Reuse the same constants build_tracker.py uses, so classification here
# matches the dashboard exactly (same Episodes playlist, same test-broadcast
# filters for lives).
EPISODES_PLAYLIST_ID = "PLX3ZLYz4-6vE2_ZNLW5AfzbHTd1jTskDl"
LIVE_TEST_TITLE_KEYWORDS = ("test", "do not publish", "dnp")
LIVE_MIN_DURATION_SEC = 300
LIVE_MIN_VIEWS = 25
SHORT_MAX_DURATION_SEC = 180

ERAS = {
    "VOD":  ("2025-07-01", "2025-12-31"),
    "LIVE": ("2026-01-01", "2026-06-30"),
}


def yt_clients():
    """Build authenticated Data API + Analytics API clients from config.py creds."""
    creds = Credentials(
        token=None,
        refresh_token=YT_REFRESH_TOKEN,
        client_id=YT_CLIENT_ID,
        client_secret=YT_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    youtube = build("youtube", "v3", credentials=creds)
    analytics = build("youtubeAnalytics", "v2", credentials=creds)
    return youtube, analytics


_DUR_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")
def iso_duration_to_sec(iso):
    if not iso:
        return 0
    m = _DUR_RE.match(iso)
    if not m:
        return 0
    h, mn, s = m.groups()
    return int(h or 0) * 3600 + int(mn or 0) * 60 + int(s or 0)


def to_et(iso_utc):
    if not iso_utc:
        return None
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    try:
        from zoneinfo import ZoneInfo
        return dt.astimezone(ZoneInfo("America/New_York"))
    except ImportError:
        return dt.astimezone(timezone(timedelta(hours=-5)))


def title_features(title):
    """Simple, objective title features — no hand-picked keyword lists."""
    letters = [c for c in title if c.isalpha()]
    caps = [c for c in letters if c.isupper()]
    return {
        "title_len_chars": len(title),
        "title_word_count": len(title.split()),
        "title_caps_ratio": round(len(caps) / len(letters), 3) if letters else 0,
        "title_has_exclaim": "!" in title,
        "title_has_question": "?" in title,
    }


def pull_episode_playlist_ids(youtube, playlist_id):
    ids = set()
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=playlist_id,
            maxResults=50, pageToken=next_page).execute()
        for item in resp.get("items", []):
            ids.add(item["contentDetails"]["videoId"])
        next_page = resp.get("nextPageToken")
        if not next_page:
            break
    return ids


def classify(v, episode_ids):
    """live / episode / short / vod — live-status is checked FIRST, before
    playlist membership. This matters a lot post-pivot: most "episodes" now
    ARE the archived live broadcast for that week, so checking playlist
    membership first would silently swallow most real lives into the
    episode bucket and never test them against the live criteria at all."""
    lsd = v.get("liveStreamingDetails") or {}
    if lsd.get("actualStartTime"):
        title_lower = v["snippet"].get("title", "").lower()
        privacy = v.get("status", {}).get("privacyStatus", "public")
        dur = iso_duration_to_sec(v.get("contentDetails", {}).get("duration", ""))
        views = int(v.get("statistics", {}).get("viewCount", 0))
        is_test = (
            any(re.search(r'\b' + re.escape(kw) + r'\b', title_lower) for kw in LIVE_TEST_TITLE_KEYWORDS) or
            privacy in ("private", "unlisted") or
            dur < LIVE_MIN_DURATION_SEC or
            views < LIVE_MIN_VIEWS
        )
        if not is_test:
            return "live"
        return None  # test broadcast — exclude entirely from the research set

    vid_id = v["id"]
    if vid_id in episode_ids:
        return "episode"

    dur = iso_duration_to_sec(v.get("contentDetails", {}).get("duration", ""))
    return "short" if dur < SHORT_MAX_DURATION_SEC else "vod"


def walk_era_videos(youtube, channel_id, era_start, era_end, episode_ids):
    """Walk the uploads playlist, keep videos published within [era_start, era_end],
    classify each, and attach title features."""
    ch = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    era_start_iso = f"{era_start}T00:00:00Z"
    era_end_iso = f"{era_end}T23:59:59Z"

    out = []
    seen_ids = set()
    next_page = None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_id,
            maxResults=50, pageToken=next_page).execute()
        ids = [it["contentDetails"]["videoId"] for it in resp.get("items", [])]
        if not ids:
            break
        details = youtube.videos().list(
            part="snippet,statistics,liveStreamingDetails,contentDetails,status",
            id=",".join(ids)).execute()

        stop = False
        for v in details.get("items", []):
            vid_id = v["id"]
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)
            pub = v["snippet"].get("publishedAt", "")
            if pub and pub < era_start_iso:
                stop = True
                continue
            if pub > era_end_iso:
                continue  # newer than this era's window, keep walking back

            content_type = classify(v, episode_ids)
            if content_type is None:
                continue  # filtered test broadcast

            pub_et = to_et(pub)
            feats = title_features(v["snippet"].get("title", ""))
            out.append({
                "id": vid_id,
                "title": v["snippet"].get("title", ""),
                "published_at": pub,
                "publish_date": pub[:10],
                "day_of_week": pub_et.strftime("%a") if pub_et else "",
                "hour_et": pub_et.hour if pub_et is not None else "",
                "content_type": content_type,
                "duration_sec": iso_duration_to_sec(v.get("contentDetails", {}).get("duration", "")),
                "lifetime_views": int(v.get("statistics", {}).get("viewCount", 0)),
                "likes": int(v.get("statistics", {}).get("likeCount", 0)),
                "comments": int(v.get("statistics", {}).get("commentCount", 0)),
                "tag_count": len(v["snippet"].get("tags", [])),
                "tags": "|".join(v["snippet"].get("tags", [])),
                "description": v["snippet"].get("description", "").replace("\n", " ").replace("\r", " "),
                "category_id": v["snippet"].get("categoryId", ""),
                **feats,
            })

        next_page = resp.get("nextPageToken")
        if stop or not next_page:
            break

    return out


def pull_subs_attribution(analytics, channel_id, video, window_days):
    """subscribersGained/Lost + views in a fixed window after this video's
    publish date. Returns None if the window hasn't fully elapsed yet."""
    pub_date = datetime.strptime(video["publish_date"], "%Y-%m-%d")
    window_end = pub_date + timedelta(days=window_days)
    if window_end.date() > datetime.now(timezone.utc).date():
        return None  # not enough time has passed yet

    start_str = pub_date.strftime("%Y-%m-%d")
    end_str = window_end.strftime("%Y-%m-%d")

    try:
        resp = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_str,
            endDate=end_str,
            metrics="views,subscribersGained,subscribersLost",
            dimensions="video",
            filters=f"video=={video['id']}",
        ).execute()
    except Exception as e:
        return {"error": str(e)}

    rows = resp.get("rows", [])
    if not rows:
        return {"window_views": 0, "subs_gained": 0, "subs_lost": 0}
    row = rows[0]  # [video_id, views, subscribersGained, subscribersLost]
    return {"window_views": row[1], "subs_gained": row[2], "subs_lost": row[3]}


def main():
    ap = argparse.ArgumentParser(description="Per-video features + subscriber attribution for Live vs VOD research.")
    ap.add_argument("--window-days", type=int, default=28,
                     help="Fixed post-publish attribution window in days (default: 28)")
    ap.add_argument("--output", default="C:/Users/apriest1/Documents/GitHub/data/master/shows/road_trippin/data/video_growth_features.csv")
    args = ap.parse_args()

    print("=" * 60)
    print("VIDEO GROWTH FEATURES — Live vs VOD research pull")
    print("=" * 60)
    print(f"Attribution window: {args.window_days} days post-publish")
    print(f"Eras: VOD {ERAS['VOD']}  |  Live {ERAS['LIVE']}")
    print()

    youtube, analytics = yt_clients()

    print("Pulling Full Episodes playlist...")
    episode_ids = pull_episode_playlist_ids(youtube, EPISODES_PLAYLIST_ID)
    print(f"  ✓ {len(episode_ids)} episodes in playlist")
    print()

    all_videos = []
    for era_name, (start, end) in ERAS.items():
        print(f"Walking {era_name} era videos ({start} → {end})...")
        vids = walk_era_videos(youtube, CHANNEL_ID, start, end, episode_ids)
        for v in vids:
            v["era"] = era_name
        print(f"  ✓ {len(vids)} videos "
              f"({sum(1 for v in vids if v['content_type']=='episode')} episodes, "
              f"{sum(1 for v in vids if v['content_type']=='vod')} vods, "
              f"{sum(1 for v in vids if v['content_type']=='live')} lives, "
              f"{sum(1 for v in vids if v['content_type']=='short')} shorts)")
        all_videos.extend(vids)
    print()

    print(f"Pulling subscriber attribution for {len(all_videos)} videos "
          f"(1 API call each — this is the slow part)...")
    skipped_too_recent = 0
    errors = 0
    for i, v in enumerate(all_videos, 1):
        attr = pull_subs_attribution(analytics, CHANNEL_ID, v, args.window_days)
        if attr is None:
            skipped_too_recent += 1
            v["window_views"] = None
            v["subs_gained"] = None
            v["subs_lost"] = None
        elif "error" in attr:
            errors += 1
            v["window_views"] = None
            v["subs_gained"] = None
            v["subs_lost"] = None
        else:
            v["window_views"] = attr["window_views"]
            v["subs_gained"] = attr["subs_gained"]
            v["subs_lost"] = attr["subs_lost"]
        if i % 50 == 0:
            print(f"  ...{i}/{len(all_videos)}")

    print()
    print(f"  ✓ Done. {skipped_too_recent} skipped (window not elapsed yet), {errors} errors")

    if not all_videos:
        print("\nNo videos found — check credentials/date ranges.")
        return

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(all_videos[0].keys())
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_videos)

    print()
    print("=" * 60)
    print(f"✓ Wrote {len(all_videos):,} videos → {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()