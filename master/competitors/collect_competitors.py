"""
RDM — Competitor snapshot (internal)
====================================
Once a day, records public YouTube stats for every channel in competitors.csv —
our shows included, measured the same public way so the comparison is fair.
The YouTube API only ever returns today's totals, so the history exists only
because this runs every day: start it early, never skip.

Writes (all under master/competitors/data/):
    channel_daily.csv            date, channel_id, subs, views, videos, last_upload  (one row per channel per day)
    videos.csv                   video_id, channel_id, published, duration_sec, live, title
    video_daily/YYYY-MM-DD.csv   video_id, views, likes, comments  — videos published in the
                                 last VIDEO_WINDOW_DAYS, one file per day (history is never rewritten)

API key: YT_API_KEY_COMPETITORS (GitHub secret, or master/config_socials.py locally). It
belongs to its own Google Cloud project (rdm-competitors), separate from the shows' projects.
Cost: ~1 unit per 50 channels + ~2 units per page of 50 recent uploads — well under 1% of quota.

Usage (from repo root):
    python master/competitors/collect_competitors.py
    python master/competitors/collect_competitors.py --dry-run
"""

import argparse
import csv
import importlib.util
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
API = "https://www.googleapis.com/youtube/v3"
ET = ZoneInfo("America/New_York")
VIDEO_WINDOW_DAYS = 35      # track each upload's views daily for its first 5 weeks
MAX_PAGES = 30              # safety cap per channel (50 uploads per page)


def load_key():
    key = os.environ.get("YT_API_KEY_COMPETITORS")
    if key:
        return key
    path = os.path.join(ROOT, "master", "config_socials.py")
    if os.path.exists(path):
        spec = importlib.util.spec_from_file_location("config_socials", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "YT_API_KEY_COMPETITORS", None)
    return None


def get(endpoint, key, **params):
    r = requests.get(f"{API}/{endpoint}", params={**params, "key": key}, timeout=30)
    j = r.json()
    if "error" in j:
        raise RuntimeError(f"{endpoint}: {j['error'].get('message', r.status_code)}")
    return j


def iso_sec(iso):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def et_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET).date().isoformat()


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Daily public YouTube snapshot of competitor channels")
    ap.add_argument("--dry-run", action="store_true", help="Pull and summarize, write nothing")
    args = ap.parse_args()

    key = load_key()
    if not key:
        raise SystemExit("No YT_API_KEY_COMPETITORS (not a secret here, not in master/config_socials.py)")

    shows = read_csv(os.path.join(HERE, "competitors.csv"))
    ids = [s["channel_id"] for s in shows]
    today = datetime.now(ET).date()
    cutoff = (today - timedelta(days=VIDEO_WINDOW_DAYS)).isoformat()
    print(f"COMPETITOR SNAPSHOT · {today} · {len(ids)} channels")

    # 1. Channel totals (1 unit per 50 channels)
    channels = {}
    for i in range(0, len(ids), 50):
        for c in get("channels", key, part="statistics,contentDetails", id=",".join(ids[i:i + 50]),
                     maxResults=50).get("items", []):
            channels[c["id"]] = c
    missing = [s["show"] for s in shows if s["channel_id"] not in channels]
    if missing:
        print(f"  ⚠ not returned: {', '.join(missing)}")

    # 2. Recent uploads per channel — page through the uploads playlist until past the window
    recent = {}       # video_id -> channel_id
    last_upload = {}  # channel_id -> latest upload date (even if outside the window)
    for s in shows:
        c = channels.get(s["channel_id"])
        if not c:
            continue
        pid = c["contentDetails"]["relatedPlaylists"]["uploads"]
        page, n = None, 0
        try:
            for _ in range(MAX_PAGES):
                j = get("playlistItems", key, part="contentDetails", playlistId=pid, maxResults=50, pageToken=page or "")
                items = j.get("items", [])
                if page is None and items:
                    last_upload[s["channel_id"]] = max(et_date(it["contentDetails"]["videoPublishedAt"])
                                                        for it in items if it["contentDetails"].get("videoPublishedAt"))
                for it in items:
                    pub = it["contentDetails"].get("videoPublishedAt")
                    if pub and et_date(pub) >= cutoff:
                        recent[it["contentDetails"]["videoId"]] = s["channel_id"]
                        n += 1
                page = j.get("nextPageToken")
                oldest = min((it["contentDetails"].get("videoPublishedAt") or "9" for it in items), default="0")
                if not page or et_date(oldest) < cutoff:
                    break
        except RuntimeError as e:
            print(f"  ⚠ {s['show']}: {e}")
        print(f"  {s['show']:<30} {int(c['statistics'].get('subscriberCount', 0)):>10,} subs · {n:>4} uploads in {VIDEO_WINDOW_DAYS}d")

    # 3. Video details + current stats (1 unit per 50 videos)
    vids = list(recent)
    details = {}
    for i in range(0, len(vids), 50):
        for v in get("videos", key, part="snippet,contentDetails,statistics,liveStreamingDetails",
                     id=",".join(vids[i:i + 50]), maxResults=50).get("items", []):
            details[v["id"]] = v
    print(f"  {len(details)} recent videos · {sum(1 for v in details.values() if iso_sec(v['contentDetails'].get('duration')) <= 180)} Shorts-length")

    if args.dry_run:
        print("Dry run — nothing written.")
        return

    # channel_daily.csv — replace today's rows on a re-run
    cd_path = os.path.join(DATA, "channel_daily.csv")
    rows = [r for r in read_csv(cd_path) if r["date"] != today.isoformat()]
    for cid, c in channels.items():
        st = c["statistics"]
        rows.append({"date": today.isoformat(), "channel_id": cid, "subs": st.get("subscriberCount", ""),
                     "views": st.get("viewCount", ""), "videos": st.get("videoCount", ""),
                     "last_upload": last_upload.get(cid, "")})
    write_csv(cd_path, ["date", "channel_id", "subs", "views", "videos", "last_upload"], rows)

    # videos.csv — metadata, upserted
    v_path = os.path.join(DATA, "videos.csv")
    meta = {r["video_id"]: r for r in read_csv(v_path)}
    for vid, v in details.items():
        meta[vid] = {"video_id": vid, "channel_id": recent[vid],
                     "published": et_date(v["snippet"]["publishedAt"]),
                     "duration_sec": iso_sec(v["contentDetails"].get("duration")),
                     "live": int(bool((v.get("liveStreamingDetails") or {}).get("actualStartTime"))),
                     "title": v["snippet"]["title"]}
    write_csv(v_path, ["video_id", "channel_id", "published", "duration_sec", "live", "title"],
              sorted(meta.values(), key=lambda r: (r["published"], r["video_id"])))

    # video_daily/<date>.csv — today's views for every recent upload
    write_csv(os.path.join(DATA, "video_daily", f"{today.isoformat()}.csv"), ["video_id", "views", "likes", "comments"],
              [{"video_id": vid, "views": v["statistics"].get("viewCount", ""),
                "likes": v["statistics"].get("likeCount", ""), "comments": v["statistics"].get("commentCount", "")}
               for vid, v in details.items()])
    print(f"✓ Saved {len(channels)} channels, {len(details)} videos for {today}")


if __name__ == "__main__":
    main()
