"""
RDM — content grades for any show's YouTube channel
=====================================================
Grades every upload against the show's own recent uploads of the same format at the same age (same method as the
shared Schultz dashboard, see master/shows/schultz_report/pull_content_sr.py):

  • Per video, per day (YouTube Analytics): views, engaged views, watch minutes, likes, comments, shares, subs —
    with YouTube-ADVERTISING traffic split out, so everything graded is ORGANIC.
  • Per video, per day (YouTube Reporting API daily files): thumbnail impressions + clicks, organic.
  • Score = weighted percentile ranks within the comparison group (same format, published in the previous
    90 days, measured at the same age): % viewed .35 · CTR .35 (Shorts: engaged %) · views .15 · engagement .10
    · subs per 1K .05 → A (top 20%) … F (bottom 20%).

Formats: episode = in one of the show's full-episode playlists · short = YouTube Short · clip = other long-form.
Caches in <show data>/content/ (video_daily.csv, video_reach_daily.csv) are the history — YouTube's daily report
files expire. Only videos up to UPDATE_DAYS old are re-pulled each day (grades only need the first AGES days).
Writes <show data>/content.json (every graded upload in the window) for that show's dashboard Content tab.

    python master/content_grades.py --show rt      (rt | gt | fr)
"""

import argparse
import csv
import importlib.util
import io
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yt_kpis                                       # noqa: E402

RT = os.path.join(HERE, "shows", "road_trippin")
SHOWS = {
    "rt": {"tracker": os.path.join(RT, "build_tracker.py"), "auth": "authenticate_yt", "data": os.path.join(RT, "data"),
           "tracker_json": "tracker_data.json",
           "episodes": ["PLX3ZLYz4-6vE2_ZNLW5AfzbHTd1jTskDl",      # RT Full Episodes (group)
                        "PLX3ZLYz4-6vHA_GG37kXNZowGAKqu94Sh",      # Perk Unplugged
                        "PLX3ZLYz4-6vFapW85GvTgNr-4rJjgkzqi"]},    # Channing's Mailbag
    "gt": {"tracker": os.path.join(RT, "build_gt_tracker.py"), "auth": "authenticate",
           "data": os.path.join(RT, "data", "girls_tripp"), "tracker_json": "tracker_data_gt.json",
           "episodes": ["PLcPj2Bidz6D4"]},
    "fr": {"tracker": os.path.join(RT, "data", "football_related", "build_fr_tracker.py"), "auth": "authenticate",
           "data": os.path.join(RT, "data", "football_related", "data_fr"), "tracker_json": "tracker_data_fr.json",
           "episodes": ["PLOZ-AJjs7IGw"]},
}
WINDOW_DAYS = 150          # uploads tracked per video (covers the 90-day comparison group + 28-day ages + slack)
UPDATE_DAYS = 35           # re-pull a video's daily stats until it's this old
REPULL_DAYS = 5            # Analytics revises recent days
AGES = 28
PEER_DAYS = 90
PAID = {"1"}               # Reporting API traffic_source_type 1 = YouTube advertising
WEIGHTS = {"retention": 0.35, "ctr": 0.35, "views": 0.15, "engagement": 0.10, "subs": 0.05}
DAILY_FIELDS = ["video_id", "date", "views", "engaged", "minutes", "likes", "comments", "shares", "subs",
                "paid_views", "paid_engaged", "paid_minutes"]
REACH_FIELDS = ["date", "video_id", "impressions", "clicks", "org_impressions", "org_clicks"]
RET_FIELDS = ["video_id", "pulled", "age", "duration_sec", "r30", "r60"]


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


def _num(r, k):
    try:
        return float(r[k])
    except (KeyError, TypeError, ValueError):
        return 0.0


def _org(r, k):
    return _num(r, k) - _num(r, "paid_" + k) if k in ("views", "engaged", "minutes") else _num(r, k)


def week_start(d):
    return (d - timedelta(days=d.weekday())).isoformat()


def authenticate(cfg):
    d = os.path.dirname(cfg["tracker"])
    sys.path.insert(0, d)
    cwd = os.getcwd()
    os.chdir(d)
    try:
        spec = importlib.util.spec_from_file_location("tracker_" + os.path.basename(d), cfg["tracker"])
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        creds = getattr(mod, cfg["auth"])()
    finally:
        os.chdir(cwd)
    if not getattr(creds, "token", None):
        from google.auth.transport.requests import Request
        creds.refresh(Request())
    return creds


def playlist_ids(yt, pid):
    ids, tok = [], None
    while True:
        r = yt.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50, pageToken=tok).execute(num_retries=3)
        ids += [i["contentDetails"]["videoId"] for i in r["items"]]
        tok = r.get("nextPageToken")
        if not tok:
            return ids


def update_daily(ya, videos, end, cdir):
    """Per-video daily stats (organic + paid split). Videos older than UPDATE_DAYS keep their cached days."""
    path = os.path.join(cdir, "video_daily.csv")
    rows = {(r["video_id"], r["date"]): r for r in read_csv(path)}
    last = defaultdict(str)
    for (vid, d) in rows:
        last[vid] = max(last[vid], d)
    stop = (date.fromisoformat(end) - timedelta(days=UPDATE_DAYS)).isoformat()
    fetched = 0
    for vid, v in videos.items():
        if last[vid] and v["published"] < stop:
            continue                                  # history complete for grading
        start = v["published"]
        if last[vid]:
            start = max(start, (date.fromisoformat(last[vid]) - timedelta(days=REPULL_DAYS)).isoformat())
        if start > end:
            continue
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions="day", filters=f"video=={vid}",
                               metrics="views,engagedViews,estimatedMinutesWatched,likes,comments,shares,subscribersGained"
                               ).execute(num_retries=3)
        rp = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, dimensions="day,insightTrafficSourceType",
                                filters=f"video=={vid}", metrics="views,engagedViews,estimatedMinutesWatched").execute(num_retries=3)
        paid = {d: (pv, pe, pm) for d, src, pv, pe, pm in rp.get("rows", []) if src == "ADVERTISING"}
        for d, views, eng, mins, likes, com, sh, subs in r.get("rows", []):
            pv, pe, pm = paid.get(d, (0, 0, 0))
            rows[(vid, d)] = {"video_id": vid, "date": d, "views": views, "engaged": eng, "minutes": mins, "likes": likes,
                              "comments": com, "shares": sh, "subs": subs, "paid_views": pv, "paid_engaged": pe, "paid_minutes": pm}
        fetched += 1
    write_csv(path, DAILY_FIELDS, [rows[k] for k in sorted(rows)])
    return fetched


def update_reach(creds, cdir, keep_ids):
    """Per-video daily organic impressions/clicks from the Reporting API files not cached yet (tracked videos only)."""
    import requests
    path = os.path.join(cdir, "video_reach_daily.csv")
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
        dl = requests.get(r["downloadUrl"], headers=h, timeout=180)
        if dl.status_code != 200:
            continue
        agg = defaultdict(lambda: [0, 0.0, 0, 0.0])
        for row in csv.DictReader(io.StringIO(dl.text)):
            if row.get("video_id") not in keep_ids:
                continue
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
    return new


def _interp(points, x):
    """Linear interpolation on [(ratio, value)] with (0, 1.0) as the start."""
    pts = [(0.0, 1.0)] + sorted(points)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * ((x - x0) / (x1 - x0) if x1 > x0 else 0)
    return pts[-1][1]


def update_retention(ya, videos, through, cdir):
    """% of organic viewers still watching at 0:30 and 1:00, per long-form upload, from YouTube's retention curve
    (audienceWatchRatio by elapsedVideoTimeRatio, 100 points). Re-read weekly until day 28, then kept."""
    path = os.path.join(cdir, "retention.csv")
    rows = {r["video_id"]: r for r in read_csv(path)}
    end = date.fromisoformat(through)
    n = 0
    for vid, v in videos.items():
        dur = v.get("duration_sec") or 0
        if v["format"] == "short" or dur < 90:
            continue
        age = (end - date.fromisoformat(v["published"])).days + 1
        old = rows.get(vid)
        if age < 2 or (old and (int(old["age"]) >= AGES or age - int(old["age"]) < 7)):
            continue
        try:
            r = ya.reports().query(ids="channel==MINE", startDate=v["published"], endDate=through, metrics="audienceWatchRatio",
                                   dimensions="elapsedVideoTimeRatio", filters=f"video=={vid};audienceType==ORGANIC"
                                   ).execute(num_retries=3)
        except Exception:
            continue
        pts = [(float(x), float(y)) for x, y in r.get("rows", [])]
        if not pts:
            continue
        cap = lambda y: round(min(y, 1.0), 4)
        rows[vid] = {"video_id": vid, "pulled": through, "age": min(age, AGES), "duration_sec": dur,
                     "r30": cap(_interp(pts, 30 / dur)), "r60": cap(_interp(pts, 60 / dur))}
        n += 1
    write_csv(path, RET_FIELDS, [rows[k] for k in sorted(rows)])
    return n


def _scores(x, dur, fmt):
    eng, views = x.get("engaged", 0), x.get("views", 0)
    s = {"views": views,
         "retention": (x.get("minutes", 0) / (eng * dur / 60)) if eng and dur else None,
         "engagement": ((x.get("likes", 0) + x.get("comments", 0) + x.get("shares", 0)) / views) if views else None,
         "subs": (x.get("subs", 0) / views * 1000) if views else None,
         "avd": (x.get("minutes", 0) * 60 / eng) if eng else None}      # average view duration (sec), YouTube's basis
    if fmt == "short":
        s["ctr"] = (eng / views) if views else None
    else:
        s["ctr"] = (x.get("org_clicks", 0) / x["org_impressions"]) if x.get("org_impressions", 0) >= 100 else None
    return s


def _pct_rank(v, peers):
    peers = [p for p in peers if p is not None]
    if v is None or len(peers) < 5:
        return None
    return sum(1 for p in peers if p < v) / len(peers) + 0.5 * sum(1 for p in peers if p == v) / len(peers)


def grade(videos, cdir, through):
    ret = {r["video_id"]: r for r in read_csv(os.path.join(cdir, "retention.csv"))}
    daily, reach = defaultdict(dict), defaultdict(dict)
    for r in read_csv(os.path.join(cdir, "video_daily.csv")):
        daily[r["video_id"]][r["date"]] = r
    for r in read_csv(os.path.join(cdir, "video_reach_daily.csv")):
        reach[r["video_id"]][r["date"]] = r
    by_age = {}
    for vid, v in videos.items():
        pub, cum, out = date.fromisoformat(v["published"]), defaultdict(float), []
        for age in range(1, AGES + 1):
            d = (pub + timedelta(days=age - 1)).isoformat()
            if d > through:
                break
            r, rr = daily[vid].get(d, {}), reach[vid].get(d, {})
            for k in ("views", "engaged", "minutes", "likes", "comments", "shares", "subs"):
                cum[k] += _org(r, k)
            cum["paid_views"] += _num(r, "paid_views")
            for k in ("org_impressions", "org_clicks"):
                cum[k] += _num(rr, k)
            out.append(dict(cum))
        by_age[vid] = out
    graded = {}
    for vid, v in videos.items():
        age = len(by_age[vid])
        if not age or not daily[vid]:
            continue
        cur = _scores(by_age[vid][-1], v["duration_sec"], v["format"])
        lo = (date.fromisoformat(v["published"]) - timedelta(days=PEER_DAYS)).isoformat()
        peers = [p for p, pv in videos.items() if p != vid and pv["format"] == v["format"]
                 and lo <= pv["published"] < v["published"] and len(by_age[p]) >= age and daily[p]]
        if len(peers) < 5:
            peers = [p for p, pv in videos.items() if p != vid and pv["format"] == v["format"] and len(by_age[p]) >= age and daily[p]]
        ps = [_scores(by_age[p][age - 1], videos[p]["duration_sec"], videos[p]["format"]) for p in peers]
        ranks = {k: _pct_rank(cur[k], [s[k] for s in ps]) for k in WEIGHTS}
        used = {k: r for k, r in ranks.items() if r is not None}
        wsum = sum(WEIGHTS[k] for k in used)
        score = sum(WEIGHTS[k] * r for k, r in used.items()) / wsum if wsum else None
        rt = ret.get(vid) or {}
        cur["r30"] = float(rt["r30"]) if rt.get("r30") not in (None, "") else None
        cur["r60"] = float(rt["r60"]) if rt.get("r60") not in (None, "") else None
        graded[vid] = {**v, "week": week_start(date.fromisoformat(v["published"])),
                       "paid_views": by_age[vid][-1].get("paid_views", 0),
                       "grade": {"age_days": age, "peers": len(peers), "score": round(score, 3) if score is not None else None,
                                 "letter": None if score is None else "A" if score >= .8 else "B" if score >= .6
                                 else "C" if score >= .4 else "D" if score >= .2 else "F",
                                 "ranks": {k: (round(r, 2) if r is not None else None) for k, r in ranks.items()},
                                 "values": {k: (round(x, 4) if isinstance(x, float) else x) for k, x in cur.items()}}}
    return graded


def run(show):
    from googleapiclient.discovery import build
    cfg = SHOWS[show]
    cdir = os.path.join(cfg["data"], "content")
    creds = authenticate(cfg)
    yt = build("youtube", "v3", credentials=creds)
    ya = build("youtubeAnalytics", "v2", credentials=creds)
    through = (date.today() - timedelta(days=1)).isoformat()
    since = (date.today() - timedelta(days=WINDOW_DAYS)).isoformat()

    episodes = set()
    for pid in cfg["episodes"]:
        episodes |= set(playlist_ids(yt, pid))
    tj = json.load(open(os.path.join(cfg["data"], cfg["tracker_json"]), encoding="utf-8"))
    tpath = os.path.join(cfg["data"], "yt_video_types.csv")
    types = yt_kpis._load_types(tpath)
    if not types:
        types = yt_kpis.video_types(ya, tpath)
    videos = {}
    for v in tj.get("all_videos", []):
        if v.get("published", "") < since or types.get(v["id"]) == "LIVES":
            continue
        fmt = ("episode" if v["id"] in episodes else "short" if types.get(v["id"]) == "SHORTS"
               or (v["id"] not in types and v.get("type") == "short") else "clip")
        videos[v["id"]] = {"title": v["title"], "published": v["published"], "duration_sec": v.get("duration_sec") or 0,
                           "format": fmt}
    print(f"CONTENT GRADES · {show.upper()} · {len(videos)} uploads since {since} "
          f"({sum(v['format'] == 'episode' for v in videos.values())} episodes, "
          f"{sum(v['format'] == 'clip' for v in videos.values())} clips, {sum(v['format'] == 'short' for v in videos.values())} Shorts)")
    n = update_daily(ya, videos, through, cdir)
    print(f"  ✓ daily stats refreshed for {n} uploads")
    print(f"  ✓ retention (0:30 / 1:00) read for {update_retention(ya, videos, through, cdir)} long-form uploads")
    try:
        new = update_reach(creds, cdir, set(videos))
        print(f"  ✓ impressions: {new} new day(s)")
    except Exception as e:
        print(f"  ⚠ impressions skipped: {e}")
    graded = grade(videos, cdir, through)
    # Every graded upload in the window: the Content tab filters by any date range. A grade is taken at the upload's
    # age, capped at day AGES — so it's Provisional (<7 days), Working (7–28) or Final (28+, locked at day 28).
    out = {"generated": datetime.now().isoformat(timespec="minutes"), "through": through, "weights": WEIGHTS,
           "peer_days": PEER_DAYS, "final_age": AGES, "videos": graded}
    json.dump(out, open(os.path.join(cfg["data"], "content.json"), "w", encoding="utf-8"), indent=1)
    print(f"✓ content.json · {len(out['videos'])} recent uploads graded")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Content grades for a show's YouTube uploads")
    ap.add_argument("--show", required=True, choices=sorted(SHOWS))
    run(ap.parse_args().show)
