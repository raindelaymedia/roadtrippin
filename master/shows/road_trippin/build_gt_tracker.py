"""
Girls Tripp — YouTube Tracker Builder
Pulls the Girls Tripp channel from the YouTube Analytics + Data APIs and writes
data/girls_tripp/tracker_data_gt.json in the same schema as RT's tracker_data.json,
so build_gt_dashboard.py can read it directly.

On top of the RT pull, this adds Road Trippin' attribution: what share of GT's
views were referred by RT, via
  - Suggested videos  (RELATED_VIDEO → referring video ID → its channel)
  - Channel pages     (YT_CHANNEL    → referring channel ID)
End screen and playlist detail aren't supported by the API for this channel.

Usage (from repo root):
    python master/shows/road_trippin/build_tracker_gt.py
    python master/shows/road_trippin/build_tracker_gt.py --months 12

Credentials come from config_gt.py (gitignored), same names as RT's config.py:
    YT_CHANNEL_ID, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
Optional in config_gt.py:
    RT_CHANNEL_ID            — Road Trippin's channel ID (auto-detected if missing)
    GT_EPISODES_PLAYLIST_ID  — GT "Full Episodes" playlist (falls back to 30+ min videos)
"""

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as build_api

try:
    import config_gt as _cfg
    CHANNEL_ID    = _cfg.YT_CHANNEL_ID
    CLIENT_ID     = _cfg.YT_CLIENT_ID
    CLIENT_SECRET = _cfg.YT_CLIENT_SECRET
    REFRESH_TOKEN = _cfg.YT_REFRESH_TOKEN
    RT_CHANNEL_ID = getattr(_cfg, "RT_CHANNEL_ID", None)
    EPISODES_PLAYLIST_ID = getattr(_cfg, "GT_EPISODES_PLAYLIST_ID", None)
except (ImportError, AttributeError) as e:
    raise SystemExit(f"\n⚠  config_gt.py missing or incomplete ({e}).\n"
                     "   Needs YT_CHANNEL_ID, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.\n")

# Any RT video works here — used only to look up RT's channel ID if it isn't in config_gt.py
RT_REFERENCE_VIDEO = "BeZUS-lZ4qs"

# Traffic sources whose detail rows can be traced back to a channel
COLLAB_SOURCES = {
    "RELATED_VIDEO": "suggested",
    "YT_CHANNEL":    "channel_page",
}

# Live-stream QA filters (same as RT)
LIVE_TEST_TITLE_KEYWORDS = ("test", "do not publish", "dnp")
LIVE_MIN_DURATION_SEC = 300
LIVE_MIN_VIEWS = 25


# ─── Helpers ─────────────────────────────────────────────────────
def get_month_keys(n=22):
    now = datetime.now().replace(day=1)
    return [(now - relativedelta(months=i)).strftime("%Y-%m") for i in range(n)]


def month_bounds(ym):
    """First and last day of a month, capped at yesterday."""
    first = datetime.strptime(ym, "%Y-%m").date()
    last = first + relativedelta(months=1) - timedelta(days=1)
    yesterday = date.today() - timedelta(days=1)
    return first.isoformat(), min(last, yesterday).isoformat()


def iso_dur_to_sec(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mn, s = m.groups()
    return int(h or 0) * 3600 + int(mn or 0) * 60 + int(s or 0)


def chunks(seq, n=50):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def authenticate():
    creds = Credentials(
        token=None, refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.readonly"])
    creds.refresh(Request())
    return creds


# ─── Analytics API: channel totals ───────────────────────────────
def pull_monthly(yta, start, end):
    resp = yta.reports().query(
        ids="channel==MINE", startDate=start, endDate=end,
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
        dimensions="month", sort="month").execute()
    return {r[0]: {"views": r[1], "watch_hrs": round(r[2] / 60, 1),
                   "subs_gained": r[3], "subs_lost": r[4]} for r in resp.get("rows", [])}


def pull_by_content_type(yta, start, end):
    resp = yta.reports().query(
        ids="channel==MINE", startDate=start, endDate=end,
        metrics="views", dimensions="month,creatorContentType", sort="month").execute()
    key_map = {"videoOnDemand": "VIDEO_ON_DEMAND", "shorts": "SHORTS", "liveStream": "LIVE_STREAM"}
    data = defaultdict(lambda: {"VIDEO_ON_DEMAND": 0, "SHORTS": 0, "LIVE_STREAM": 0})
    for m, ctype, views in resp.get("rows", []):
        key = key_map.get(ctype)
        if key:
            data[m][key] += views
    return dict(data)


def pull_daily(yta, start, end):
    tot = yta.reports().query(
        ids="channel==MINE", startDate=start, endDate=end,
        metrics="views,estimatedMinutesWatched,subscribersGained,subscribersLost",
        dimensions="day", sort="day").execute()
    typ = yta.reports().query(
        ids="channel==MINE", startDate=start, endDate=end,
        metrics="views", dimensions="day,creatorContentType", sort="day").execute()
    key_map = {"videoOnDemand": "vod_views", "shorts": "shorts_views", "liveStream": "live_views"}
    daily = defaultdict(dict)
    for d, v, mins, sg, sl in tot.get("rows", []):
        daily[d].update({"total_views": v, "watch_hrs": round(mins / 60, 1),
                         "subs_gained": sg, "subs_lost": sl})
    for d, ctype, v in typ.get("rows", []):
        key = key_map.get(ctype)
        if key:
            daily[d][key] = daily[d].get(key, 0) + v
    return dict(sorted(daily.items()))


def pull_traffic_and_device(yta, start, end):
    """Monthly views by traffic source type and by device.
    Returns ({month: {source: views}}, {month: {device: views}})."""
    src = defaultdict(lambda: defaultdict(int))
    resp = yta.reports().query(
        ids="channel==MINE", startDate=start, endDate=end,
        metrics="views", dimensions="day,insightTrafficSourceType", sort="day").execute()
    for d, s, v in resp.get("rows", []):
        src[d[:7]][s] += v

    dev = defaultdict(lambda: defaultdict(int))
    resp = yta.reports().query(
        ids="channel==MINE", startDate=start, endDate=end,
        metrics="views", dimensions="day,deviceType", sort="day").execute()
    for d, t, v in resp.get("rows", []):
        dev[d[:7]][t] += v
    return {m: dict(v) for m, v in src.items()}, {m: dict(v) for m, v in dev.items()}


# ─── Collab attribution ──────────────────────────────────────────
def pull_source_details(yta, months):
    """Top 25 referrers per collab-traceable source, per month.
    (The API caps traffic-source detail at 25 rows per query.)
    Returns {month: {source_type: [(detail_id, views), ...]}}."""
    out = {}
    for m in months:
        start, end = month_bounds(m)
        if start > end:
            continue
        out[m] = {}
        for stype in COLLAB_SOURCES:
            try:
                resp = yta.reports().query(
                    ids="channel==MINE", startDate=start, endDate=end,
                    metrics="views", dimensions="insightTrafficSourceDetail",
                    filters=f"insightTrafficSourceType=={stype}",
                    sort="-views", maxResults=25).execute()
                out[m][stype] = [(r[0], r[1]) for r in resp.get("rows", [])]
            except Exception as e:
                print(f"    ⚠ {m} {stype} detail failed: {e}")
                out[m][stype] = []
    return out


def resolve_owners(youtube, details):
    """Map every referring video / channel ID to (channel_id, channel_title)."""
    vids, chans = set(), set()
    for per_type in details.values():
        for stype, rows in per_type.items():
            ids = {r[0] for r in rows}
            if stype == "RELATED_VIDEO":
                vids |= ids
            elif stype == "YT_CHANNEL":
                chans |= ids

    owner = {}
    for batch in chunks(vids):
        for it in youtube.videos().list(part="snippet", id=",".join(batch)).execute().get("items", []):
            owner[it["id"]] = (it["snippet"]["channelId"], it["snippet"]["channelTitle"])

    # Channel IDs referenced directly, plus any owners we still need names for
    chans |= {c for c, _ in owner.values()}
    names = {}
    for batch in chunks(c for c in chans if c.startswith("UC")):
        for it in youtube.channels().list(part="snippet", id=",".join(batch)).execute().get("items", []):
            names[it["id"]] = it["snippet"]["title"]
    for c in chans:
        owner.setdefault(c, (c, names.get(c, c)))
    return owner


def build_collab(months, traffic, details, owner, rt_id, gt_id):
    """Per-month RT share of views, plus other referring channels."""
    out = {}
    for m in months:
        src_totals = traffic.get(m, {})
        total = sum(src_totals.values())
        if not total:
            continue
        rt_by = {v: 0 for v in COLLAB_SOURCES.values()}
        coverage = {}
        by_channel = defaultdict(int)
        ch_names = {}
        for stype, key in COLLAB_SOURCES.items():
            rows = details.get(m, {}).get(stype, [])
            covered = 0
            for detail_id, views in rows:
                covered += views
                ch_id, ch_name = owner.get(detail_id, (None, None))
                if not ch_id or ch_id == gt_id:
                    continue  # unresolved, or GT referring to itself
                by_channel[ch_id] += views
                ch_names[ch_id] = ch_name
                if ch_id == rt_id:
                    rt_by[key] += views
            stotal = src_totals.get(stype, 0)
            coverage[key] = round(covered / stotal, 4) if stotal else None

        rt_views = sum(rt_by.values())
        ext_views = sum(by_channel.values())
        top = sorted(by_channel.items(), key=lambda x: -x[1])[:5]
        out[m] = {
            "total_views":   total,
            "rt_views":      rt_views,
            "rt_pct":        round(rt_views / total, 4),
            "rt_by_source":  rt_by,
            "collab_views":  ext_views,                       # all other channels, RT included
            "collab_pct":    round(ext_views / total, 4),
            "top_channels":  [{"id": c, "name": ch_names[c], "views": v, "is_rt": c == rt_id} for c, v in top],
            "detail_coverage": coverage,
        }
    return out


# ─── Data API: single uploads walk ───────────────────────────────
def walk_uploads(youtube, channel_id, oldest_month):
    """One pass over the uploads playlist → every video since oldest_month,
    with type (short/mid/long) and live-stream info."""
    cutoff = f"{oldest_month}-01T00:00:00Z"
    ch = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    videos, seen, page = [], set(), None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads, maxResults=50, pageToken=page).execute()
        ids = [it["contentDetails"]["videoId"] for it in resp.get("items", [])]
        if not ids:
            break
        det = youtube.videos().list(
            part="snippet,statistics,contentDetails,liveStreamingDetails,status",
            id=",".join(ids)).execute()
        stop = False
        for v in det.get("items", []):
            if v["id"] in seen:
                continue
            seen.add(v["id"])
            pub = v["snippet"]["publishedAt"]
            if pub < cutoff:
                stop = True
                continue
            dur_iso = v.get("contentDetails", {}).get("duration", "")
            if not dur_iso:
                continue  # active live, premiere, or post
            secs = iso_dur_to_sec(dur_iso)
            vtype = "short" if secs <= 180 else "mid" if secs <= 1800 else "long"
            th = v["snippet"].get("thumbnails", {})
            stats = v.get("statistics", {})
            videos.append({
                "id": v["id"],
                "title": v["snippet"]["title"],
                "published": pub[:10],
                "month": pub[:7],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "duration_sec": secs,
                "thumbnail": (th.get("maxres", {}).get("url") or th.get("high", {}).get("url")
                              or f"https://img.youtube.com/vi/{v['id']}/hqdefault.jpg"),
                "url": f"https://youtu.be/{v['id']}",
                "type": vtype,
                "_live": bool((v.get("liveStreamingDetails") or {}).get("actualStartTime")),
                "_privacy": v.get("status", {}).get("privacyStatus", "public"),
            })
        page = resp.get("nextPageToken")
        if stop or not page:
            break
    return videos


def playlist_ids(youtube, pid):
    ids, page = set(), None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=pid, maxResults=50, pageToken=page).execute()
        ids |= {it["contentDetails"]["videoId"] for it in resp.get("items", [])}
        page = resp.get("nextPageToken")
        if not page:
            return ids


def derive_from_videos(videos, episode_ids):
    """Shorts counts, live counts, episode/VOD counts, top content, best of."""
    shorts_count, lives, eps, vods = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
    live_excluded = []
    for v in videos:
        m = v["month"]
        if v["type"] == "short":
            shorts_count[m] += 1
        is_ep = (v["id"] in episode_ids) if episode_ids is not None else v["type"] == "long"
        if is_ep:
            eps[m] += 1
            vods[m] += 1
        elif v["type"] == "mid":
            vods[m] += 1
        if v["_live"]:
            is_test = (any(re.search(r"\b" + re.escape(k) + r"\b", v["title"].lower())
                           for k in LIVE_TEST_TITLE_KEYWORDS)
                       or v["_privacy"] in ("private", "unlisted")
                       or v["duration_sec"] < LIVE_MIN_DURATION_SEC
                       or v["views"] < LIVE_MIN_VIEWS)
            if is_test:
                live_excluded.append(v["title"])
            else:
                lives[m] += 1

    clean = [{k: val for k, val in v.items() if not k.startswith("_")} for v in videos]

    top = {}
    for v in clean:
        top.setdefault(v["month"], {"long": [], "mid": [], "short": []})[v["type"]].append(v)
    for m in top:
        for t in top[m]:
            top[m][t] = sorted(top[m][t], key=lambda x: -x["views"])[:10]

    this_month = datetime.now().strftime("%Y-%m")
    best = {"long": [], "mid": [], "short": []}
    for v in clean:
        if v["month"] == this_month:
            best[v["type"]].append({**{k: v[k] for k in ("id", "title", "published", "views",
                                                        "likes", "thumbnail", "url")},
                                    "type": v["type"].upper(), "show": "GT"})
    for t in best:
        best[t] = sorted(best[t], key=lambda x: -x["views"])[:5]

    return dict(shorts_count), dict(lives), live_excluded, dict(eps), dict(vods), top, best, clean


# ─── Main ────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Girls Tripp — YouTube Tracker Builder")
    ap.add_argument("--months", type=int, default=22)
    ap.add_argument("--output", default=None, help="Override path to tracker_data_gt.json")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = args.output or os.path.join(script_dir, "data", "girls_tripp", "tracker_data_gt.json")

    print("=" * 60)
    print("GIRLS TRIPP — YOUTUBE TRACKER BUILDER")
    print("=" * 60)

    months = get_month_keys(args.months)
    start = f"{months[-1]}-01"
    end = (date.today() - timedelta(days=1)).isoformat()
    month_end = date.today().replace(day=1).isoformat()   # month dimension needs 1st-of-month dates
    print(f"Window: {start} → {end}\n")

    creds = authenticate()
    youtube = build_api("youtube", "v3", credentials=creds)
    yta = build_api("youtubeAnalytics", "v2", credentials=creds)

    def step(label, fn, default):
        try:
            result = fn()
            print(f"  ✓ {label}")
            return result
        except Exception as e:
            print(f"  ✗ {label} failed: {e}")
            return default

    print("[1/3] Channel analytics")
    monthly = step("Monthly totals", lambda: pull_monthly(yta, start, month_end), {})
    content = step("Views by content type", lambda: pull_by_content_type(yta, start, month_end), {})
    daily = step("Daily (last 90 days)", lambda: pull_daily(
        yta, (date.today() - timedelta(days=91)).isoformat(), end), {})
    traffic, device = step("Traffic sources + devices", lambda: pull_traffic_and_device(yta, start, end), ({}, {}))
    current_subs = step("Subscriber count", lambda: int(youtube.channels().list(
        part="statistics", id=CHANNEL_ID).execute()["items"][0]["statistics"].get("subscriberCount", 0)), 0)

    # Trim leading months before the channel had any views
    active = [m for m in months if (monthly.get(m, {}).get("views") or 0) > 0 or sum(traffic.get(m, {}).values()) > 0]
    if active:
        months = months[:months.index(active[-1]) + 1]
    print(f"  Months with data: {months[-1]} → {months[0]} ({len(months)})")

    print("\n[2/3] Content (Data API)")
    videos = step("Uploads walk", lambda: walk_uploads(youtube, CHANNEL_ID, months[-1]), [])
    ep_ids = None
    if EPISODES_PLAYLIST_ID:
        ep_ids = step("Full Episodes playlist", lambda: playlist_ids(youtube, EPISODES_PLAYLIST_ID), None)
    else:
        print("  · No GT_EPISODES_PLAYLIST_ID set — counting 30+ min videos as episodes")
    shorts_count, lives, live_excl, eps, vods, top_content, best_of, all_videos = derive_from_videos(videos, ep_ids)
    print(f"  ✓ {len(all_videos)} videos · {sum(lives.values())} lives ({len(live_excl)} test broadcasts filtered)")

    print("\n[3/3] Road Trippin' attribution")
    rt_id = RT_CHANNEL_ID
    if not rt_id:
        rt_id = step("RT channel ID lookup", lambda: youtube.videos().list(
            part="snippet", id=RT_REFERENCE_VIDEO).execute()["items"][0]["snippet"]["channelId"], None)
    print(f"  RT channel: {rt_id}")
    details = step("Traffic source details (top 25 per source/month)",
                   lambda: pull_source_details(yta, months), {})
    owner = step("Resolve referring videos/channels", lambda: resolve_owners(youtube, details), {})
    collab = build_collab(months, traffic, details, owner, rt_id, CHANNEL_ID)
    for m in months[:4]:
        c = collab.get(m)
        if c:
            print(f"    {m}: {c['rt_pct']*100:5.1f}% from RT ({c['rt_views']:,} of {c['total_views']:,})")

    kpis = {"shorts_count": {}, "ctr": {}, "search_pct": {}, "tv_pct": {}}
    for m in months:
        t, d = traffic.get(m, {}), device.get(m, {})
        tt, dt = sum(t.values()), sum(d.values())
        kpis["shorts_count"][m] = shorts_count.get(m)
        kpis["ctr"][m] = None  # impressions CTR isn't exposed by the Analytics API
        kpis["search_pct"][m] = round(t.get("YT_SEARCH", 0) / tt, 4) if tt else None
        kpis["tv_pct"][m] = round((d.get("TV", 0) + d.get("GAME_CONSOLE", 0)) / dt, 4) if dt else None

    ct = lambda m, k: content.get(m, {}).get(k)
    tracker = {
        "generated": datetime.now().isoformat(),
        "channel_id": CHANNEL_ID,
        "rt_channel_id": rt_id,
        "months": months,
        "yt": {
            "vids":        {m: ct(m, "VIDEO_ON_DEMAND") for m in months},
            "shorts":      {m: ct(m, "SHORTS") for m in months},
            "lives":       {m: ct(m, "LIVE_STREAM") for m in months},
            "subs_gained": {m: monthly.get(m, {}).get("subs_gained") for m in months},
            "subs_lost":   {m: monthly.get(m, {}).get("subs_lost") for m in months},
            "watch_hrs":   {m: monthly.get(m, {}).get("watch_hrs") for m in months},
        },
        "audio": {"downloads": {m: None for m in months},
                  "streams":   {m: None for m in months},
                  "episodes":  {m: None for m in months}},
        "kpis": kpis,
        "collab": {
            key: {m: collab.get(m, {}).get(key) for m in months}
            for key in ("total_views", "rt_views", "rt_pct", "rt_by_source",
                        "collab_views", "collab_pct", "top_channels", "detail_coverage")
        },
        "traffic_sources": {m: traffic.get(m, {}) for m in months},
        "best_of": {"label": datetime.now().strftime("%b 01 – %b %d, %Y"), **best_of},
        "audience": {"eps":   {m: eps.get(m) for m in months},
                     "vods":  {m: vods.get(m) for m in months},
                     "lives": {m: lives.get(m) for m in months}},
        "top_content_monthly": top_content,
        "all_videos": all_videos,
        "current_subs": current_subs,
        "daily_yt": daily,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2, default=str)
    print(f"\n✓ Saved: {out_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()