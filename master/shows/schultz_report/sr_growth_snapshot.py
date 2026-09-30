"""
Schultz Report — Growth Snapshot
Pulls a batch of channel-growth "points of interest" for a date window and
writes them to one readable report, so we can pick the flattering stats
without clicking around Studio.

Usage (from repo root):
    python master/shows/schultz_report/sr_growth_snapshot.py
    python master/shows/schultz_report/sr_growth_snapshot.py --start 2026-08-18 --end 2026-09-24

Output: prints the report and saves it to data_sr/sr_growth_snapshot_<start>_<end>.md
"""

import argparse
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build as build_api

from config_sr import (
    YT_CHANNEL_ID    as CHANNEL_ID,
    YT_CLIENT_ID     as CLIENT_ID,
    YT_CLIENT_SECRET as CLIENT_SECRET,
    YT_REFRESH_TOKEN as REFRESH_TOKEN,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data_sr")

PAID = {"ADVERTISING", "PROMOTED"}
SOURCE_NAMES = {
    "SHORTS": "Shorts feed", "RELATED_VIDEO": "Suggested videos", "SUBSCRIBER": "Browse features / home",
    "YT_SEARCH": "YouTube search", "ADVERTISING": "YouTube advertising (paid)", "EXT_URL": "External",
    "YT_CHANNEL": "Channel pages", "NO_LINK_OTHER": "Direct / unknown", "PLAYLIST": "Playlists",
    "NOTIFICATION": "Notifications", "YT_OTHER_PAGE": "Other YouTube features", "END_SCREEN": "End screens",
    "HASHTAGS": "Hashtag pages", "SOUND_PAGE": "Sound pages", "SHORTS_CONTENT_LINKS": "Shorts related-video links",
    "VIDEO_REMIXES": "Remixes", "YT_PLAYLIST_PAGE": "Playlist pages", "CAMPAIGN_CARD": "Campaign cards",
}
CT_NAMES = {"videoOnDemand": "Videos", "shorts": "Shorts", "liveStream": "Live", "posts": "Posts"}


# ─── Plumbing ────────────────────────────────────────────────────
def authenticate():
    creds = Credentials(
        token=None, refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.readonly"])
    creds.refresh(Request())
    return creds


def q(yta, start, end, metrics, dims=None, **kw):
    """Analytics query → list of rows. Dates are YYYY-MM-DD strings or dates."""
    params = dict(ids="channel==MINE", startDate=str(start), endDate=str(end), metrics=metrics, **kw)
    if dims:
        params["dimensions"] = dims
    return yta.reports().query(**params).execute(num_retries=3).get("rows", []) or []


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date() if isinstance(s, str) else s


def n(v):
    if v is None:
        return "—"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.1f}"
    return f"{int(v):,}"


def pct(a, b):
    return f"{a / b * 100:.1f}%" if b else "—"


def change(cur, prev):
    if not prev:
        return "new" if cur else "—"
    return f"{(cur - prev) / prev * 100:+,.0f}%"


def mmss(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def iso_dur_to_sec(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0) if m else 0


class Report:
    def __init__(self):
        self.lines = []

    def h(self, t):
        self.lines += ["", f"## {t}", ""]

    def p(self, t=""):
        self.lines.append(t)

    def table(self, head, rows):
        self.lines.append("| " + " | ".join(head) + " |")
        self.lines.append("|" + "|".join("---" for _ in head) + "|")
        for r in rows:
            self.lines.append("| " + " | ".join(str(c) for c in r) + " |")
        self.lines.append("")

    def section(self, title, fn):
        self.h(title)
        try:
            fn()
        except Exception as e:
            self.p(f"_Could not pull this section: {e}_")

    def text(self):
        return "\n".join(self.lines)


# ─── Pulls ───────────────────────────────────────────────────────
TOTAL_METRICS = ("views,estimatedMinutesWatched,averageViewDuration,subscribersGained,"
                 "subscribersLost,likes,comments,shares")


def window_totals(yta, start, end):
    rows = q(yta, start, end, TOTAL_METRICS)
    keys = TOTAL_METRICS.split(",")
    t = dict(zip(keys, rows[0])) if rows else {k: 0 for k in keys}
    src = dict(q(yta, start, end, "views", "insightTrafficSourceType"))
    t["paid"] = sum(v for k, v in src.items() if k in PAID)
    t["organic"] = sum(src.values()) - t["paid"]
    t["sources"] = src
    try:
        t["engagedViews"] = q(yta, start, end, "engagedViews")[0][0]
    except Exception:
        t["engagedViews"] = None
    return t


def daily_series(yta, first, last):
    """Daily views / subs / paid over a long range, pulled a year at a time."""
    views, subs, paid = defaultdict(int), defaultdict(int), defaultdict(int)
    cur = first
    while cur <= last:
        stop = min(cur + timedelta(days=364), last)
        for day, v, sg, sl in q(yta, cur, stop, "views,subscribersGained,subscribersLost", "day", sort="day"):
            views[day] += v
            subs[day] += sg - sl
        for day, s, v in q(yta, cur, stop, "views", "day,insightTrafficSourceType", sort="day"):
            if s in PAID:
                paid[day] += v
        cur = stop + timedelta(days=1)
    return views, subs, paid


def rolling_best_since(series, start, end):
    """Sum of `series` over [start, end], and the most recent earlier window of the
    same length (ending before `start`) that matched or beat it."""
    length = (end - start).days + 1
    days = sorted(series)
    if not days:
        return 0, None
    first = d(days[0])
    total = lambda s: sum(series.get((s + timedelta(days=i)).isoformat(), 0) for i in range(length))
    cur = total(start)
    probe = start - timedelta(days=length)       # latest window that ends before `start`
    best_since = None
    # walk backwards day by day, using a running sum for speed
    run = total(probe) if probe >= first else None
    while probe >= first:
        if run >= cur:
            best_since = probe
            break
        probe -= timedelta(days=1)
        if probe < first:
            break
        run += series.get(probe.isoformat(), 0) - series.get((probe + timedelta(days=length)).isoformat(), 0)
    return cur, best_since


def uploads(youtube, since):
    ch = youtube.channels().list(part="contentDetails,snippet", id=CHANNEL_ID).execute(num_retries=3)
    item = ch["items"][0]
    up_id = item["contentDetails"]["relatedPlaylists"]["uploads"]
    created = item["snippet"]["publishedAt"][:10]
    vids, page = [], None
    while True:
        r = youtube.playlistItems().list(part="contentDetails", playlistId=up_id,
                                         maxResults=50, pageToken=page).execute(num_retries=3)
        ids = [i["contentDetails"]["videoId"] for i in r.get("items", [])]
        if not ids:
            break
        det = youtube.videos().list(part="snippet,contentDetails", id=",".join(ids)).execute(num_retries=3)
        stop = False
        for v in det.get("items", []):
            pub = v["snippet"]["publishedAt"][:10]
            if pub < since:
                stop = True
                continue
            secs = iso_dur_to_sec(v.get("contentDetails", {}).get("duration"))
            vids.append({"id": v["id"], "title": v["snippet"]["title"], "published": pub,
                         "type": "Short" if secs <= 180 else "Video", "live":
                         v["snippet"].get("liveBroadcastContent") != "none"})
        page = r.get("nextPageToken")
        if stop or not page:
            break
    return vids, created


def titles(youtube, ids):
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 50):
        r = youtube.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute(num_retries=3)
        for v in r.get("items", []):
            out[v["id"]] = (v["snippet"]["title"], v["snippet"]["publishedAt"][:10])
    return out


# ─── Main ────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Schultz Report — Growth Snapshot")
    ap.add_argument("--start", default="2026-08-18")
    ap.add_argument("--end", default="2026-09-24")
    args = ap.parse_args()

    start, end = d(args.start), d(args.end)
    length = (end - start).days + 1
    prev_start, prev_end = start - timedelta(days=length), start - timedelta(days=1)
    ly_start, ly_end = start.replace(year=start.year - 1), end.replace(year=end.year - 1)

    creds = authenticate()
    yta = build_api("youtubeAnalytics", "v2", credentials=creds)
    youtube = build_api("youtube", "v3", credentials=creds)

    r = Report()
    r.p(f"# Schultz Report — Growth Snapshot")
    r.p(f"**Window:** {start:%b %d} – {end:%b %d, %Y} ({length} days) · generated {datetime.now():%b %d, %Y %H:%M}")

    print("Pulling window totals...")
    cur = window_totals(yta, start, end)
    prev = window_totals(yta, prev_start, prev_end)
    ly = window_totals(yta, ly_start, ly_end)

    # 1. Headline totals
    def headline():
        r.p(f"Compared with the previous {length} days ({prev_start:%b %d} – {prev_end:%b %d}) "
            f"and the same window last year ({ly_start:%b %d} – {ly_end:%b %d, %Y}).")
        r.p()
        rows = []
        def add(label, k, fmt=n):
            c, p_, l_ = cur.get(k), prev.get(k), ly.get(k)
            rows.append([label, fmt(c), fmt(p_), change(c or 0, p_ or 0), fmt(l_), change(c or 0, l_ or 0)])
        add("Views", "views")
        add("Organic views (excl. ads)", "organic")
        add("Engaged views", "engagedViews")
        cur["hrs"], prev["hrs"], ly["hrs"] = (x["estimatedMinutesWatched"] / 60 for x in (cur, prev, ly))
        add("Watch time (hours)", "hrs")
        add("Subscribers gained", "subscribersGained")
        cur["net"], prev["net"], ly["net"] = (x["subscribersGained"] - x["subscribersLost"] for x in (cur, prev, ly))
        add("Net subscribers", "net")
        add("Likes", "likes")
        add("Comments", "comments")
        add("Shares", "shares")
        add("Avg view duration", "averageViewDuration", mmss)
        r.table(["Metric", "This window", "Prev window", "vs prev", "Last year", "vs last year"], rows)
        r.p(f"- **Organic share:** {pct(cur['organic'], cur['views'])} organic / {pct(cur['paid'], cur['views'])} paid")
        r.p(f"- **Subscribers per 1,000 views:** {cur['subscribersGained'] / cur['views'] * 1000:.1f}"
            if cur["views"] else "- Subscribers per 1,000 views: —")
        per_day = cur["views"] / length
        r.p(f"- **Average views per day:** {n(per_day)}")
    r.section("1. Headline numbers", headline)

    # 2. Traffic sources
    def traffic():
        src = sorted(cur["sources"].items(), key=lambda x: -x[1])
        tot = sum(cur["sources"].values())
        r.table(["Source", "Views", "Share"],
                [[SOURCE_NAMES.get(k, k), n(v), pct(v, tot)] for k, v in src])
        algo = sum(cur["sources"].get(k, 0) for k in ("SHORTS", "RELATED_VIDEO", "SUBSCRIBER"))
        r.p(f"- **Algorithmic discovery** (Shorts feed + suggested + browse): {pct(algo, tot)} of views")
    r.section("2. Where the views came from", traffic)

    # 3. Content mix + uploads
    print("Pulling content mix and uploads...")
    vids, created = uploads(youtube, since=min(prev_start, ly_start).isoformat())

    def content():
        ct = dict(q(yta, start, end, "views", "creatorContentType"))
        tot = sum(ct.values())
        r.table(["Format", "Views", "Share"],
                [[CT_NAMES.get(k, k), n(v), pct(v, tot)] for k, v in sorted(ct.items(), key=lambda x: -x[1])])
        in_win = [v for v in vids if start.isoformat() <= v["published"] <= end.isoformat()]
        in_prev = [v for v in vids if prev_start.isoformat() <= v["published"] <= prev_end.isoformat()]
        shorts = sum(1 for v in in_win if v["type"] == "Short")
        r.p(f"- **Uploads in window:** {len(in_win)} ({len(in_win) - shorts} videos, {shorts} Shorts) "
            f"vs {len(in_prev)} in the previous {length} days")
        if in_win:
            r.p(f"- **Views per upload:** {n(cur['views'] / len(in_win))}")
    r.section("3. Content mix and output", content)

    # 4. Top videos in window
    def top_videos():
        rows = q(yta, start, end, "views,subscribersGained,averageViewPercentage,likes",
                 "video", sort="-views", maxResults=15)
        meta = titles(youtube, [x[0] for x in rows])
        out = []
        for vid, views, subs, avp, likes in rows:
            t, pub = meta.get(vid, (vid, ""))
            new = "✓" if pub and start.isoformat() <= pub <= end.isoformat() else ""
            out.append([t[:70], pub, new, n(views), n(subs), f"{avp:.0f}%", n(likes)])
        r.table(["Video", "Published", "New in window", "Views (window)", "Subs gained", "Avg % viewed", "Likes"], out)
        subs_tot = cur["subscribersGained"]
        if rows and subs_tot:
            best = max(rows, key=lambda x: x[2])
            r.p(f"- **Top subscriber driver:** {meta.get(best[0], (best[0],))[0][:70]} — "
                f"{n(best[2])} subs ({pct(best[2], subs_tot)} of all subs gained)")
    r.section("4. Top videos in the window", top_videos)

    # 5. All-time context
    print("Pulling lifetime data for records (can take a minute)...")
    life_start = max(d(created), date(2006, 1, 1))

    def records():
        views, subs, paid = daily_series(yta, life_start, end)
        organic = {k: views[k] - paid.get(k, 0) for k in views}
        r.p(f"Channel created {d(created):%b %d, %Y}. For each metric: this window's total, "
            f"and the last time any {length}-day stretch matched it.")
        r.p()
        rows = []
        for label, s in (("Views", views), ("Organic views", organic), ("Net subscribers", subs)):
            total, since = rolling_best_since(s, start, end)
            verdict = f"Best since {since:%b %Y}" if since else "**All-time best**"
            rows.append([label, n(total), verdict])
        r.table([f"Metric ({length} days)", "This window", "Record check"], rows)

        in_win = {k: v for k, v in views.items() if start.isoformat() <= k <= end.isoformat()}
        if in_win:
            best_day, best_v = max(in_win.items(), key=lambda x: x[1])
            earlier = [k for k, v in views.items() if k < start.isoformat() and v >= best_v]
            since = f"best since {max(earlier)}" if earlier else "**biggest day in channel history**"
            r.p(f"- **Biggest single day:** {best_day} with {n(best_v)} views — {since}")

        monthly = defaultdict(int)
        for k, v in organic.items():
            monthly[k[:7]] += v
        m_cur = end.strftime("%Y-%m")
        ranked = sorted(monthly.items(), key=lambda x: -x[1])
        pos = next((i + 1 for i, (m, _) in enumerate(ranked) if m == m_cur), None)
        if pos:
            r.p(f"- **{end:%B %Y} organic views** ({n(monthly[m_cur])}, through {end:%b %d}) rank "
                f"#{pos} of {len(ranked)} months on record")
    r.section("5. Records and all-time context", records)

    def lifetime_top():
        rows = q(yta, life_start, end, "views", "video", sort="-views", maxResults=50)
        meta = titles(youtube, [x[0] for x in rows])
        hits = []
        for rank, (vid, views) in enumerate(rows, 1):
            t, pub = meta.get(vid, (vid, ""))
            if pub and start.isoformat() <= pub <= end.isoformat():
                hits.append([f"#{rank}", t[:70], pub, n(views)])
        if hits:
            r.p(f"{len(hits)} video(s) published in this window are already in the channel's all-time top 50:")
            r.p()
            r.table(["All-time rank", "Video", "Published", "Lifetime views"], hits)
        else:
            r.p("No videos from this window in the channel's all-time top 50 yet.")
    r.section("6. All-time top 50 check", lifetime_top)

    # 7. Audience
    def audience():
        sub = dict(q(yta, start, end, "views", "subscribedStatus"))
        tot = sum(sub.values())
        r.p(f"- **Views from non-subscribers:** {pct(sub.get('UNSUBSCRIBED', 0), tot)} "
            f"(reach beyond the existing audience)")
        countries = q(yta, start, end, "views", "country", sort="-views", maxResults=5)
        ctot = cur["views"]
        r.p("- **Top countries:** " + ", ".join(f"{c} {pct(v, ctot)}" for c, v in countries))
        ages = q(yta, start, end, "viewerPercentage", "ageGroup", sort="ageGroup")
        if ages:
            r.p("- **Age:** " + ", ".join(f"{a.replace('age', '')} {v:.0f}%" for a, v in ages if v >= 1))
        gender = q(yta, start, end, "viewerPercentage", "gender")
        if gender:
            r.p("- **Gender:** " + ", ".join(f"{g.lower()} {v:.0f}%" for g, v in gender))
    r.section("7. Audience", audience)

    out = r.text()
    print(out)
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"sr_growth_snapshot_{start}_{end}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"\n✓ Saved: {path}")


if __name__ == "__main__":
    main()