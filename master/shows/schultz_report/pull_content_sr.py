"""
SR — content performance for the shared dashboard (KPI framework + weekly content grades)
==========================================================================================
Per video, per day, from YouTube:
    content/video_daily.csv        views, engaged views, watch minutes, likes, comments, shares, subs gained
                                   (YouTube Analytics, one query per video; recent days re-pulled as they settle)
    content/video_reach_daily.csv  thumbnail impressions + clicks, total and ORGANIC (all traffic except
                                   YouTube advertising), from the Reporting API's daily files — they expire,
                                   so this cache is the history
Views, engaged views and watch minutes are ORGANIC (YouTube-advertising traffic subtracted; SR runs paid
promotion) — paid views are kept alongside. Likes/comments/shares can't be split by source.
Then builds content_sr.json (pushed to The-Schultz-Report):
    kpis      by week (Mon–Sun) and month, per format: % viewed (KPI 1), organic CTR (KPI 2), avg minutes …
    videos    each recent upload: format, lifetime-to-date stats, cumulative stats by age (days 1–28),
              first-day CTR, and a grade for the week it was published in

Formats: episode = in the Full Episodes playlist (any length) · short = YouTube Short · clip = other long-form.
% viewed = watch time ÷ (engaged views × length) — YouTube's own basis (matches averageViewPercentage).

    python master/shows/schultz_report/pull_content_sr.py
"""

import csv
import io
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests
from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import build_tracker_sr as tracker          # noqa: E402  (OAuth for the SR channel)
import yt_kpis                              # noqa: E402
from content_grades import update_retention  # noqa: E402  (0:30 / 1:00 retention, shared with the other shows)

DATA = os.path.join(HERE, "data_sr")
CDIR = os.path.join(DATA, "content")
EPISODE_PLAYLIST = "PL-57LJk452aiG43ygafeNcBCb8vZAv-4U"
SINCE = "2026-07-01"            # uploads tracked per video from here (+ every playlist episode)
PAID = {"1"}                    # Reporting API traffic_source_type 1 = YouTube advertising
REPULL_DAYS = 5                 # Analytics revises recent days
AGES = 28                       # cumulative stats kept for days 1..AGES after publishing
PEER_DAYS = 90                  # grades compare against uploads of the same format from the previous 90 days
WEIGHTS = {"retention": 0.35, "ctr": 0.35, "views": 0.15, "engagement": 0.10, "subs": 0.05}
DAILY_FIELDS = ["video_id", "date", "views", "engaged", "minutes", "likes", "comments", "shares", "subs",
                "paid_views", "paid_engaged", "paid_minutes"]      # paid = traffic source ADVERTISING
REACH_FIELDS = ["date", "video_id", "impressions", "clicks", "org_impressions", "org_clicks"]


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)


def playlist_ids(yt, pid):
    ids, tok = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50, pageToken=tok).execute(num_retries=3)
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        tok = r.get("nextPageToken")
        if not tok:
            return ids


def video_meta(yt, ids):
    """{id: {title, published, duration_sec}} from the Data API."""
    import re
    out = {}
    for n in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,contentDetails", id=",".join(ids[n:n + 50])).execute(num_retries=3)
        for v in r.get("items", []):
            m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", v["contentDetails"].get("duration", ""))
            sec = sum(int(x or 0) * k for x, k in zip(m.groups(), (86400, 3600, 60, 1))) if m else 0
            out[v["id"]] = {"title": v["snippet"]["title"], "published": v["snippet"]["publishedAt"][:10], "duration_sec": sec}
    return out


# ── per-video daily Analytics ────────────────────────────────────────────────
def update_daily(ya, videos, end):
    path = os.path.join(CDIR, "video_daily.csv")
    rows = {(r["video_id"], r["date"]): r for r in read_csv(path)}
    last = defaultdict(str)
    for (vid, d), r in rows.items():
        if r.get("paid_views") in (None, ""):          # cached before the paid split existed: re-pull from the start
            last[vid] = ""
            continue
        last[vid] = max(last[vid], d)
    for vid in [v for v in last if not last[v]]:
        for k in [k for k in rows if k[0] == vid]:
            del rows[k]
    fetched = 0
    for vid, v in videos.items():
        start = v["published"]
        if last[vid]:
            start = max(start, (date.fromisoformat(last[vid]) - timedelta(days=REPULL_DAYS)).isoformat())
        if start > end:
            continue
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions="day", filters=f"video=={vid}",
                               metrics="views,engagedViews,estimatedMinutesWatched,likes,comments,shares,subscribersGained"
                               ).execute(num_retries=3)
        paid = {}
        rp = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions="day,insightTrafficSourceType",
                                filters=f"video=={vid}",
                                metrics="views,engagedViews,estimatedMinutesWatched").execute(num_retries=3)
        for d, src, pv, pe, pm in rp.get("rows", []):
            if src == "ADVERTISING":
                paid[d] = (pv, pe, pm)
        for d, views, eng, mins, likes, com, sh, subs in r.get("rows", []):
            pv, pe, pm = paid.get(d, (0, 0, 0))
            rows[(vid, d)] = {"video_id": vid, "date": d, "views": views, "engaged": eng, "minutes": mins, "likes": likes,
                              "comments": com, "shares": sh, "subs": subs, "paid_views": pv, "paid_engaged": pe, "paid_minutes": pm}
        fetched += 1
    write_csv(path, DAILY_FIELDS, [rows[k] for k in sorted(rows)])
    return fetched, len(rows)


# ── per-video daily reach (Reporting API) ────────────────────────────────────
def update_reach(creds):
    path = os.path.join(CDIR, "video_reach_daily.csv")
    rows = read_csv(path)
    have = {r["date"] for r in rows}
    h = {"Authorization": f"Bearer {creds.token}"}
    job_id, _ = yt_kpis._job(h)
    reports, tok = [], None
    while True:
        j = requests.get(f"{yt_kpis.REPORTING}/jobs/{job_id}/reports", headers=h,
                         params={"pageSize": 100, **({"pageToken": tok} if tok else {})}, timeout=30).json()
        reports += j.get("reports", [])
        tok = j.get("nextPageToken")
        if not tok:
            break
    latest = {}
    for r in reports:
        d = r["startTime"][:10]
        if d not in latest or r.get("createTime", "") > latest[d].get("createTime", ""):
            latest[d] = r
    new = 0
    for d, r in sorted(latest.items()):
        if d in have:
            continue
        dl = requests.get(r["downloadUrl"], headers=h, timeout=120)
        if dl.status_code != 200:
            continue
        agg = defaultdict(lambda: [0, 0.0, 0, 0.0])
        for row in csv.DictReader(io.StringIO(dl.text)):
            imp = int(float(row.get("video_thumbnail_impressions") or 0))
            clk = imp * float(row.get("video_thumbnail_impressions_ctr") or 0)
            a = agg[row["video_id"]]
            a[0] += imp
            a[1] += clk
            if row.get("traffic_source_type") not in PAID:
                a[2] += imp
                a[3] += clk
        rows += [{"date": d, "video_id": v, "impressions": a[0], "clicks": round(a[1], 2), "org_impressions": a[2],
                  "org_clicks": round(a[3], 2)} for v, a in agg.items() if a[0]]
        new += 1
    rows.sort(key=lambda r: (r["date"], r["video_id"]))
    write_csv(path, REACH_FIELDS, rows)
    return new, len({r["date"] for r in rows})


# ── assemble ─────────────────────────────────────────────────────────────────
def _num(r, k):
    try:
        return float(r[k])
    except (KeyError, TypeError, ValueError):
        return 0.0


def _org(r, k):
    """Organic value: total minus YouTube-advertising traffic (views, engaged, minutes)."""
    return _num(r, k) - _num(r, "paid_" + k) if k in ("views", "engaged", "minutes") else _num(r, k)


def week_start(d):
    return (d - timedelta(days=d.weekday())).isoformat()


def build_output(videos, through, fmt_of=None):
    daily = defaultdict(dict)
    for r in read_csv(os.path.join(CDIR, "video_daily.csv")):
        daily[r["video_id"]][r["date"]] = r
    reach = defaultdict(dict)
    for r in read_csv(os.path.join(CDIR, "video_reach_daily.csv")):
        reach[r["video_id"]][r["date"]] = r
    reach_through = max((d for v in reach.values() for d in v), default=None)

    # KPIs per period × format: % viewed (engaged basis), avg minutes per engaged view, organic CTR
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for vid, v in videos.items():
        f, dur = v["format"], v["duration_sec"]
        for d, r in daily[vid].items():
            dd = date.fromisoformat(d)
            for key in (("week", week_start(dd)), ("month", d[:7])):
                a = per[key][f]
                a["views"] += _org(r, "views")
                a["paid_views"] += _num(r, "paid_views")
                a["engaged"] += _org(r, "engaged")
                a["minutes"] += _org(r, "minutes")
                a["possible"] += _org(r, "engaged") * dur / 60       # minutes if every engaged view watched it all
    # Impressions / CTR: every video in the daily reports (back catalogue too, like Studio), not just tracked uploads
    for vid, days in reach.items():
        f = videos[vid]["format"] if vid in videos else (fmt_of(vid) if fmt_of else None)
        if not f:
            continue
        for d, r in days.items():
            dd = date.fromisoformat(d)
            for key in (("week", week_start(dd)), ("month", d[:7])):
                a = per[key][f]
                for k in ("impressions", "clicks", "org_impressions", "org_clicks"):
                    a[k] += _num(r, k)
    kpis = {"week": {}, "month": {}}
    for (kind, period), fmts in per.items():
        out = {}
        for f, a in fmts.items():
            out[f] = {"views": round(a["views"]), "paid_views": round(a["paid_views"]), "engaged": round(a["engaged"]),
                      "pct_viewed": round(a["minutes"] / a["possible"], 4) if a["possible"] else None,
                      "avg_minutes": round(a["minutes"] / a["engaged"], 2) if a["engaged"] else None,
                      "impressions": round(a["org_impressions"]),
                      "ctr_organic": round(a["org_clicks"] / a["org_impressions"], 4) if a["org_impressions"] else None,
                      "ctr_all": round(a["clicks"] / a["impressions"], 4) if a["impressions"] else None}
        lf = [fmts[f] for f in ("episode", "clip") if f in fmts]           # long-form = episodes + clips
        if lf:
            s = lambda k: sum(x[k] for x in lf)
            out["longform"] = {"views": round(s("views")),
                               "pct_viewed": round(s("minutes") / s("possible"), 4) if s("possible") else None,
                               "avg_minutes": round(s("minutes") / s("engaged"), 2) if s("engaged") else None,
                               "impressions": round(s("org_impressions")),
                               "ctr_organic": round(s("org_clicks") / s("org_impressions"), 4) if s("org_impressions") else None}
        kpis[kind][period] = out

    # Per video: cumulative by age, lifetime-to-date, first-day CTR
    vout = {}
    for vid, v in videos.items():
        pub = date.fromisoformat(v["published"])
        cum = defaultdict(float)
        by_age = []
        for age in range(1, AGES + 1):
            d = pub + timedelta(days=age - 1)
            if d.isoformat() > through:
                break
            r, rr = daily[vid].get(d.isoformat(), {}), reach[vid].get(d.isoformat(), {})
            for k in ("views", "engaged", "minutes", "likes", "comments", "shares", "subs"):
                cum[k] += _org(r, k)
            cum["paid_views"] += _num(r, "paid_views")
            for k in ("org_impressions", "org_clicks"):
                cum[k] += _num(rr, k)
            by_age.append({k: round(x, 2) for k, x in cum.items()})
        life = defaultdict(float)
        for r in daily[vid].values():
            for k in ("views", "engaged", "minutes", "likes", "comments", "shares", "subs"):
                life[k] += _org(r, k)
            life["paid_views"] += _num(r, "paid_views")
        for r in reach[vid].values():
            for k in ("org_impressions", "org_clicks"):
                life[k] += _num(r, k)
        d1 = [reach[vid].get((pub + timedelta(days=i)).isoformat(), {}) for i in (0, 1)]
        d1i, d1c = sum(_num(r, "org_impressions") for r in d1), sum(_num(r, "org_clicks") for r in d1)
        vout[vid] = {**v, "week": week_start(pub), "by_age": by_age, "life": {k: round(x, 2) for k, x in life.items()},
                     "first_day_ctr": round(d1c / d1i, 4) if d1i >= 100 else None}
    grade_week(vout, through)
    return {"generated": datetime.now().isoformat(timespec="minutes"), "through": through, "reach_through": reach_through,
            "weights": WEIGHTS, "peer_days": PEER_DAYS, "kpis": kpis, "videos": vout}


# ── grading ──────────────────────────────────────────────────────────────────
def _scores(x, dur, fmt):
    """Metric values from a cumulative snapshot."""
    eng, views = x.get("engaged", 0), x.get("views", 0)
    s = {"views": views,
         "retention": (x.get("minutes", 0) / (eng * dur / 60)) if eng and dur else None,
         "engagement": ((x.get("likes", 0) + x.get("comments", 0) + x.get("shares", 0)) / views) if views else None,
         "subs": (x.get("subs", 0) / views * 1000) if views else None,
         "avd": (x.get("minutes", 0) * 60 / eng) if eng else None}      # average view duration (sec)
    if fmt == "short":      # Shorts aren't clicked from thumbnails: use the share of views that were engaged
        s["ctr"] = (eng / views) if views else None
    else:
        s["ctr"] = (x.get("org_clicks", 0) / x["org_impressions"]) if x.get("org_impressions", 0) >= 100 else None
    return s


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct_rank(v, peers):
    peers = [p for p in peers if p is not None]
    if v is None or len(peers) < 5:
        return None
    return sum(1 for p in peers if p < v) / len(peers) + 0.5 * sum(1 for p in peers if p == v) / len(peers)


def grade_week(vout, through):
    """Grade each upload at its current age against same-format uploads from the previous PEER_DAYS at that same age."""
    ret = {r["video_id"]: r for r in read_csv(os.path.join(CDIR, "retention.csv"))}
    for vid, v in vout.items():
        age = len(v["by_age"])
        if not age:
            continue
        cur = _scores(v["by_age"][-1], v["duration_sec"], v["format"])
        pub = v["published"]
        lo = (date.fromisoformat(pub) - timedelta(days=PEER_DAYS)).isoformat()
        peers = [p for p in vout.values() if p is not v and p["format"] == v["format"] and lo <= p["published"] < pub
                 and len(p["by_age"]) >= age]
        if len(peers) < 5:                          # not enough history before it: compare with everything comparable
            peers = [p for p in vout.values() if p is not v and p["format"] == v["format"] and len(p["by_age"]) >= age]
        pscores = [_scores(p["by_age"][age - 1], p["duration_sec"], p["format"]) for p in peers]
        ranks = {k: _pct_rank(cur[k], [s[k] for s in pscores]) for k in WEIGHTS}
        used = {k: r for k, r in ranks.items() if r is not None}
        wsum = sum(WEIGHTS[k] for k in used)
        score = sum(WEIGHTS[k] * r for k, r in used.items()) / wsum if wsum else None
        v["grade"] = {"age_days": age, "peers": len(peers), "score": round(score, 3) if score is not None else None,
                      "letter": None if score is None else "A" if score >= .8 else "B" if score >= .6 else "C" if score >= .4
                      else "D" if score >= .2 else "F",
                      "ranks": {k: (round(r, 2) if r is not None else None) for k, r in ranks.items()},
                      "values": {**{k: (round(x, 4) if isinstance(x, float) else x) for k, x in cur.items()},
                                 "r30": _f(ret.get(vid, {}).get("r30")), "r60": _f(ret.get(vid, {}).get("r60"))}}


def main():
    creds = tracker.authenticate()
    yt = build("youtube", "v3", credentials=creds)
    ya = build("youtubeAnalytics", "v2", credentials=creds)
    through = (date.today() - timedelta(days=1)).isoformat()

    episodes = set(playlist_ids(yt, EPISODE_PLAYLIST))
    tj = json.load(open(os.path.join(DATA, "tracker_data_sr.json"), encoding="utf-8"))
    types = yt_kpis._load_types(os.path.join(DATA, "yt_video_types.csv"))
    meta = {v["id"]: {"title": v["title"], "published": v["published"], "duration_sec": v.get("duration_sec") or 0}
            for v in tj.get("all_videos", []) if v.get("published", "") >= SINCE or v["id"] in episodes}
    missing = [e for e in episodes if e not in meta]
    if missing:
        meta.update(video_meta(yt, missing))
    videos = {}
    for vid, m in meta.items():
        if types.get(vid) == "LIVES":
            continue
        fmt = "episode" if vid in episodes else "short" if types.get(vid) == "SHORTS" else "clip"
        videos[vid] = {**m, "format": fmt}
    print(f"CONTENT · {len(videos)} uploads ({sum(v['format'] == 'episode' for v in videos.values())} episodes, "
          f"{sum(v['format'] == 'clip' for v in videos.values())} clips, {sum(v['format'] == 'short' for v in videos.values())} Shorts)")

    n, total = update_daily(ya, videos, through)
    print(f"  ✓ per-video daily stats: {n} videos refreshed · {total:,} video-days")
    print(f"  ✓ retention (0:30 / 1:00) read for {update_retention(ya, videos, through, CDIR)} long-form uploads")
    new, days = update_reach(creds)
    print(f"  ✓ per-video impressions: {new} new day(s) · {days} days cached")
    fmt_of = lambda vid: (None if types.get(vid) == "LIVES" else "episode" if vid in episodes
                          else "short" if types.get(vid) == "SHORTS" else "clip")
    out = build_output(videos, through, fmt_of)
    json.dump(out, open(os.path.join(DATA, "content_sr.json"), "w", encoding="utf-8"), separators=(",", ":"))
    graded = [v for v in out["videos"].values() if (v.get("grade") or {}).get("letter")]
    print(f"✓ content_sr.json · {len(out['videos'])} uploads · {len(graded)} graded · KPIs for "
          f"{len(out['kpis']['week'])} weeks / {len(out['kpis']['month'])} months")


if __name__ == "__main__":
    main()
