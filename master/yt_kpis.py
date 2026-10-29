"""
RDM — YouTube KPIs shared by every show's tracker and dashboard
================================================================
collect(creds, months, cache_csv, videos)  → saved in tracker JSON as "yt_kpis":
    monthly[YYYY-MM][VIDS|SHORTS|LIVES|ALL] = views, engaged_views, watch_hours, avg_view_sec,
                                             avg_pct_viewed, likes, comments, shares
    reach[YYYY-MM][VIDS|SHORTS|ALL]         = impressions, ctr   (thumbnail impressions + click-through)
    reach_through                           = last day with reach data

Monthly KPIs come from the YouTube Analytics API (engagedViews included — no more Studio entry).
Impressions / CTR aren't in the Analytics API: they come from the YouTube Reporting API, which delivers one
CSV per day (channel_reach_basic_a1). Reports expire after a while, so every day we download the new ones and
keep a per-day summary in cache_csv (date, type, impressions, clicks) — that file is the history. A new
reporting job takes ~2 days to start producing, and YouTube backfills only a limited window before that.

kpi_html(kpis, fmt) → a card for a dashboard's YouTube tab.
"""

import csv
import io
import os
import re
from collections import defaultdict
from datetime import date, timedelta


TYPES = {"videoOnDemand": "VIDS", "shorts": "SHORTS", "liveStream": "LIVES"}
LABEL = {"VIDS": "Videos", "EPISODES": "Full episodes", "CLIPS": "Clips", "SHORTS": "Shorts", "LIVES": "Lives", "ALL": "All"}
# Full-episode playlists per channel: VIDS (YouTube's long-form) is split into EPISODES (these) and CLIPS (the rest)
EPISODE_PLAYLISTS = {
    "UCSes4X8uDrpc4X46hJKjejg": ["PLX3ZLYz4-6vE2_ZNLW5AfzbHTd1jTskDl", "PLX3ZLYz4-6vHA_GG37kXNZowGAKqu94Sh",
                                 "PLX3ZLYz4-6vFapW85GvTgNr-4rJjgkzqi"],          # RT group, Perk Unplugged, Mailbag
    "UCLh4znMEEDzabMHw-Ob0Cpg": ["PLcPj2Bidz6D4"],                                  # Girls Tripp
    "UCWcbo7_7Qiu0VtXPjpp-SDA": ["PLOZ-AJjs7IGw"],                                  # Football Related
    "UCD50DP5meQbRD0ug-dm1p1g": ["PL-57LJk452aiG43ygafeNcBCb8vZAv-4U"],             # The Schultz Report
}
METRICS = "views,engagedViews,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,shares"
REACH_TYPE = "channel_reach_basic_a1"
REACH_TYPES_OK = ("channel_reach_basic_a1", "channel_reach_combined_a1")
REPORTING = "https://youtubereporting.googleapis.com/v1"


# ── Analytics API: monthly KPIs by content type ──────────────────────────────
def _rows(ya, start, end, dims):
    r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics=METRICS,
                           dimensions=dims).execute(num_retries=3)
    names = [h["name"] for h in r["columnHeaders"]]
    return [dict(zip(names, row)) for row in r.get("rows", [])]


def _entry(r):
    return {"views": r["views"], "engaged_views": r["engagedViews"],
            "watch_hours": round(r["estimatedMinutesWatched"] / 60, 1), "avg_view_sec": r["averageViewDuration"],
            "avg_pct_viewed": r["averageViewPercentage"], "likes": r["likes"], "comments": r["comments"],
            "shares": r["shares"]}


def _all(by_type):
    t = list(by_type.values())
    views = sum(x["views"] for x in t)
    eng = sum(x["engaged_views"] for x in t)
    if not views:
        return None
    return {"views": views, "engaged_views": sum(x["engaged_views"] for x in t),
            "watch_hours": round(sum(x["watch_hours"] for x in t), 1),
            # YouTube's average view duration / % viewed are per ENGAGED view (watch time / engaged views)
            "avg_view_sec": round(sum(x["watch_hours"] for x in t) * 3600 / eng) if eng else None,
            "avg_pct_viewed": round(sum(x["avg_pct_viewed"] * x["engaged_views"] for x in t) / eng, 2) if eng else None,
            "likes": sum(x["likes"] for x in t), "comments": sum(x["comments"] for x in t),
            "shares": sum(x["shares"] for x in t)}


def episode_ids(creds):
    """Video IDs in this channel's full-episode playlists (EPISODE_PLAYLISTS)."""
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds)
    me = yt.channels().list(part="id", mine=True).execute(num_retries=3)["items"][0]["id"]
    ids = set()
    for pid in EPISODE_PLAYLISTS.get(me, []):
        tok = None
        while True:
            r = yt.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=50, pageToken=tok).execute(num_retries=3)
            ids |= {i["contentDetails"]["videoId"] for i in r["items"]}
            tok = r.get("nextPageToken")
            if not tok:
                break
    return sorted(ids)


def _filtered(ya, start, end, dims, ids):
    """Monthly (or period) totals for a set of videos, chunked; ratio metrics re-weighted by engaged views."""
    acc = defaultdict(lambda: defaultdict(float))
    for n in range(0, len(ids), 150):
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end, metrics=METRICS,
                               dimensions=dims or None, filters="video==" + ",".join(ids[n:n + 150])).execute(num_retries=3)
        names = [h["name"] for h in r["columnHeaders"]]
        for row in r.get("rows", []):
            x = dict(zip(names, row))
            a = acc[x.get("month", "period")]
            for k in ("views", "engagedViews", "estimatedMinutesWatched", "likes", "comments", "shares"):
                a[k] += x[k]
            a["pct_w"] += x["averageViewPercentage"] * x["engagedViews"]
    return acc


def _from_acc(a):
    eng = a["engagedViews"]
    return {"views": int(a["views"]), "engaged_views": int(eng), "watch_hours": round(a["estimatedMinutesWatched"] / 60, 1),
            "avg_view_sec": round(a["estimatedMinutesWatched"] * 60 / eng) if eng else None,
            "avg_pct_viewed": round(a["pct_w"] / eng, 2) if eng else None,
            "likes": int(a["likes"]), "comments": int(a["comments"]), "shares": int(a["shares"])}


def _minus(vids, eps):
    """CLIPS = VIDS − EPISODES (ratio metrics re-derived from the remaining totals)."""
    if not vids:
        return None
    ve, ee = vids["engaged_views"], eps["engaged_views"]
    eng = ve - ee
    mins = vids["watch_hours"] * 60 - eps["watch_hours"] * 60
    out = {k: max(vids[k] - eps[k], 0) for k in ("views", "engaged_views", "likes", "comments", "shares")}
    out["watch_hours"] = round(max(mins, 0) / 60, 1)
    out["avg_view_sec"] = round(mins * 60 / eng) if eng > 0 else None
    out["avg_pct_viewed"] = (round((vids["avg_pct_viewed"] * ve - eps["avg_pct_viewed"] * ee) / eng, 2)
                             if eng > 0 and vids.get("avg_pct_viewed") is not None and eps.get("avg_pct_viewed") is not None else None)
    return out


def monthly_kpis(ya, months, episodes=None):
    """months: 'YYYY-MM' (any order). Complete months by the `month` dimension (its dates must be 1st-of-month);
    the current month to date by its own query."""
    months = sorted(months)
    today = date.today()
    cur = today.strftime("%Y-%m")
    out = defaultdict(dict)
    done = [m for m in months if m < cur]
    if done:
        for r in _rows(ya, f"{done[0]}-01", f"{done[-1]}-01", "month,creatorContentType"):
            t = TYPES.get(r["creatorContentType"])
            if t and r["month"] in done:
                out[r["month"]][t] = _entry(r)
    yesterday = today - timedelta(days=1)
    if cur in months and yesterday.strftime("%Y-%m") == cur:
        for r in _rows(ya, f"{cur}-01", yesterday.isoformat(), "creatorContentType"):
            t = TYPES.get(r["creatorContentType"])
            if t:
                out[cur][t] = _entry(r)
    for m in out:
        a = _all(out[m])
        if a:
            out[m]["ALL"] = a
    if episodes:                                   # split long-form into full episodes and clips
        eps = {}
        if done:
            eps.update(_filtered(ya, f"{done[0]}-01", f"{done[-1]}-01", "month", episodes))
        if cur in months and yesterday.strftime("%Y-%m") == cur:
            got = _filtered(ya, f"{cur}-01", yesterday.isoformat(), None, episodes)
            if "period" in got:
                eps[cur] = got["period"]
        for m, a in eps.items():
            if m in out and out[m].get("VIDS"):
                out[m]["EPISODES"] = _from_acc(a)
                out[m]["CLIPS"] = _minus(out[m]["VIDS"], out[m]["EPISODES"])
    return dict(out)


# ── Reporting API: thumbnail impressions + CTR, cached per day ───────────────
def _job(headers):
    import requests   # lazy: the shared repo's build-only workflow has no third-party packages
    jobs = requests.get(f"{REPORTING}/jobs", headers=headers, timeout=30).json().get("jobs", [])
    for j in jobs:
        if j.get("reportTypeId") in REACH_TYPES_OK:
            return j["id"], False
    r = requests.post(f"{REPORTING}/jobs", headers=headers, timeout=30,
                      json={"reportTypeId": REACH_TYPE, "name": "RDM reach (impressions, CTR)"})
    r.raise_for_status()
    return r.json()["id"], True


def _load_types(cache_csv):
    if not os.path.exists(cache_csv):
        return {}
    with open(cache_csv, encoding="utf-8-sig", newline="") as f:
        return {r["video_id"]: r["type"] for r in csv.DictReader(f)}


def _save_types(cache_csv, known):
    os.makedirs(os.path.dirname(cache_csv) or ".", exist_ok=True)
    with open(cache_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["video_id", "type"])
        w.writerows(sorted(known.items()))


def video_types(ya, cache_csv, months=15):
    """{video_id: SHORTS|LIVES|VIDS} as YouTube classifies them (creatorContentType — Studio's Videos / Shorts / Live),
    cached in cache_csv. The API returns at most the top 200 videos per query and can't page, so it asks month by
    month (last `months` months, each content type)."""
    known = _load_types(cache_csv)
    first = date.today().replace(day=1)
    for n in range(months):
        y, m = divmod(first.year * 12 + first.month - 1 - n, 12)
        s_ = date(y, m + 1, 1)
        e_ = min((date(y + (m + 1) // 12, (m + 1) % 12 + 1, 1) - timedelta(days=1)), date.today() - timedelta(days=1))
        if e_ < s_:
            continue
        for ctype, label in (("shorts", "SHORTS"), ("liveStream", "LIVES"), ("videoOnDemand", "VIDS")):
            r = ya.reports().query(ids="channel==MINE", startDate=s_.isoformat(), endDate=e_.isoformat(), metrics="views",
                                   dimensions="video", filters=f"creatorContentType=={ctype}", sort="-views",
                                   maxResults=200).execute(num_retries=3)
            for vid, _ in r.get("rows", []):
                known[vid] = label
    _save_types(cache_csv, known)
    return known


def classify_unknown(creds, ids, cache_csv):
    """Fallback for videos the monthly lists missed: YouTube Data API — live-stream details → LIVES,
    3 minutes or shorter → SHORTS (YouTube's Shorts limit), else VIDS. Cached with the rest."""
    from googleapiclient.discovery import build
    known = _load_types(cache_csv)
    todo = [i for i in ids if i and i not in known]
    if not todo:
        return known
    yt = build("youtube", "v3", credentials=creds)
    for n in range(0, len(todo), 50):
        r = yt.videos().list(part="contentDetails,liveStreamingDetails", id=",".join(todo[n:n + 50])).execute(num_retries=3)
        for v in r.get("items", []):
            dur = v.get("contentDetails", {}).get("duration", "")
            m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur)
            sec = sum(int(x or 0) * k for x, k in zip(m.groups(), (86400, 3600, 60, 1))) if m else 0
            known[v["id"]] = "LIVES" if v.get("liveStreamingDetails") else "SHORTS" if 0 < sec <= 180 else "VIDS"
    _save_types(cache_csv, known)
    return known


def _read_cache(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {(r["date"], r["type"]): r for r in csv.DictReader(f)}


def update_reach(creds, cache_csv, video_types, rebuild=False, types_csv=None):
    """Download reach reports not cached yet (rebuild=True: every report YouTube still has, re-sorted by type;
    days it no longer has keep their cached values). video_types: {video_id: 'VIDS'|'SHORTS'|'LIVES'}."""
    import requests   # lazy: the shared repo's build-only workflow has no third-party packages
    headers = {"Authorization": f"Bearer {creds.token}"}
    job_id, created = _job(headers)
    if created:
        return f"created reporting job {job_id} — first reports in ~2 days"
    cache = _read_cache(cache_csv)
    have = {d for d, _ in cache}
    reports, token = [], None
    while True:
        params = {"pageSize": 100, **({"pageToken": token} if token else {})}
        j = requests.get(f"{REPORTING}/jobs/{job_id}/reports", headers=headers, params=params, timeout=30).json()
        reports += j.get("reports", [])
        token = j.get("nextPageToken")
        if not token:
            break
    latest = {}                                     # one report per day: the newest version
    for r in reports:
        d = r["startTime"][:10]
        if d not in latest or r.get("createTime", "") > latest[d].get("createTime", ""):
            latest[d] = r
    texts = {}
    for d, r in sorted(latest.items()):
        if d in have and not rebuild:
            continue
        dl = requests.get(r["downloadUrl"], headers=headers, timeout=120)
        if dl.status_code == 200:
            texts[d] = list(csv.DictReader(io.StringIO(dl.text)))
    if types_csv:                                   # classify videos the type lists don't cover yet
        ids = {row.get("video_id") for rows in texts.values() for row in rows} - set(video_types)
        try:
            video_types = {**classify_unknown(creds, ids, types_csv), **video_types}   # passed-in types (EPISODES) win
        except Exception as e:
            print(f"    ⚠ video type fallback: {e}")
    new = 0
    for d, rows in sorted(texts.items()):
        agg = defaultdict(lambda: [0, 0.0])
        for row in rows:
            imp = int(float(row.get("video_thumbnail_impressions") or 0))
            ctr = float(row.get("video_thumbnail_impressions_ctr") or 0)
            t = video_types.get(row.get("video_id"), "VIDS")
            for k in (t, "ALL"):
                agg[k][0] += imp
                agg[k][1] += imp * ctr
        for k in [k for k in cache if k[0] == d]:      # replace the whole day
            del cache[k]
        for t, (imp, clicks) in agg.items():
            cache[(d, t)] = {"date": d, "type": t, "impressions": imp, "clicks": round(clicks, 2)}
        if not agg:
            cache[(d, "ALL")] = {"date": d, "type": "ALL", "impressions": 0, "clicks": 0}
        new += 1
    os.makedirs(os.path.dirname(cache_csv), exist_ok=True)
    with open(cache_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "type", "impressions", "clicks"], lineterminator="\r\n")
        w.writeheader()
        w.writerows(cache[k] for k in sorted(cache))
    return f"{new} new day(s) cached · {len({d for d, _ in cache})} days total"


def reach_monthly(cache_csv):
    out = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    days = []
    per_month = defaultdict(set)
    for (d, t), r in _read_cache(cache_csv).items():
        a = out[d[:7]][t]
        a[0] += int(float(r["impressions"]))
        a[1] += float(r["clicks"])
        days.append(d)
        per_month[d[:7]].add(d)
    res = {m: {t: {"impressions": imp, "ctr": round(cl / imp, 4) if imp else None, "days": len(per_month[m])}
               for t, (imp, cl) in v.items()} for m, v in out.items()}
    return res, (max(days) if days else None)


def retention_monthly(data_dir):
    """% still watching at 0:30 / 1:00 by month published, EPISODES and CLIPS, view-weighted — from the show's content
    grades file (content.json / content_sr.json, written after the tracker, so one day behind)."""
    import json
    for name in ("content.json", "content_sr.json"):
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            break
    else:
        return {}
    acc = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    for v in (json.load(open(p, encoding="utf-8")).get("videos") or {}).values():
        vals = (v.get("grade") or {}).get("values") or {}
        t = {"episode": "EPISODES", "clip": "CLIPS"}.get(v.get("format"))
        w = vals.get("views") or 0
        if t and w and vals.get("r30") is not None:
            a = acc[v["published"][:7]][t]
            a[0] += w * vals["r30"]
            a[1] += w * (vals.get("r60") or 0)
            a[2] += w
    return {m: {t: {"r30": round(a[0] / a[2], 4), "r60": round(a[1] / a[2], 4)} for t, a in d.items() if a[2]} for m, d in acc.items()}


def collect(creds, months, cache_csv, videos):
    """Everything for the tracker JSON. Failures in one half don't lose the other."""
    from googleapiclient.discovery import build
    out = {"monthly": {}, "reach": {}, "reach_through": None, "notes": []}
    eps = []
    try:
        eps = episode_ids(creds)
    except Exception as e:
        out["notes"].append(f"episode playlists: {e}")
    try:
        ya = build("youtubeAnalytics", "v2", credentials=creds)
        known = _load_types(os.path.join(os.path.dirname(cache_csv), "yt_video_types.csv"))
        eps = [v for v in eps if known.get(v, "VIDS") == "VIDS"]     # a live or Short in the playlist stays in its own type
        out["monthly"] = monthly_kpis(ya, months, eps)
        print(f"  ✓ YouTube KPIs: {len(out['monthly'])} months (engaged views, watch time, retention, likes …)")
    except Exception as e:
        out["notes"].append(f"monthly KPIs failed: {e}")
        print(f"  ✗ YouTube KPIs: {e}")
    try:
        types_csv = os.path.join(os.path.dirname(cache_csv), "yt_video_types.csv")
        # Type per video as YouTube classifies it (Studio's Videos / Shorts / Live); tracker list as fallback
        vt = {v["id"]: ("SHORTS" if v.get("type") == "short" else "VIDS") for v in videos or [] if v.get("id")}
        try:
            vt.update(video_types(ya, types_csv))
        except Exception as e:
            out["notes"].append(f"video types: {e}")
        vt.update({v: "EPISODES" for v in eps})        # impressions split: full episodes vs clips (VIDS = clips)
        cached = _read_cache(cache_csv)                 # re-sort once if most cached days predate the episode split
        ep_days = sum(1 for _, t in cached if t == "EPISODES")
        rebuild = bool(eps) and ep_days < sum(1 for _, t in cached if t == "VIDS") / 2
        note = update_reach(creds, cache_csv, vt, rebuild=rebuild, types_csv=types_csv)
        out["reach"], out["reach_through"] = reach_monthly(cache_csv)
        out["retention"] = retention_monthly(os.path.dirname(cache_csv))
        print(f"  ✓ Reach (impressions/CTR): {note}")
        out["notes"].append(note)
    except Exception as e:
        out["notes"].append(f"reach failed: {e}")
        print(f"  ✗ Reach: {e}")
    return out


# ── Dashboard card ───────────────────────────────────────────────────────────
def _mon(m):
    from datetime import datetime
    d = datetime.strptime(m, "%Y-%m")
    return d.strftime("%b") + ("" if d.year == date.today().year else d.strftime(" %y"))


def _dur(sec):
    if sec is None:
        return "—"
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def kpi_html(kpis, fmt, n_months=6):
    monthly = {m: dict(v) for m, v in ((kpis or {}).get("monthly") or {}).items()}
    for m, v in monthly.items():                       # recompute "All" on the engaged-view basis (older JSON had it per view)
        a = _all({t: x for t, x in v.items() if t in ("VIDS", "SHORTS", "LIVES")})
        if a:
            v["ALL"] = a
    reach = (kpis or {}).get("reach") or {}
    months = sorted(monthly)[-n_months:][::-1]          # newest first
    if not months:
        return ""
    cur = months[0]

    def g(m, t, k):
        return (monthly.get(m, {}).get(t) or {}).get(k)

    def rg(m, t, k):
        rm = reach.get(m, {})
        if t == "CLIPS":                      # reach VIDS = clips once episodes are split out
            t = "VIDS" if "EPISODES" in rm else None
        return (rm.get(t) or {}).get(k) if t else None
    retention = (kpis or {}).get("retention") or {}
    rr = lambda m, t, k: (retention.get(m, {}).get(t) or {}).get(k)

    pct = lambda v: "—" if v is None else f"{v * 100:.1f}%"

    def partial(m):                                    # reach cache missing days in a finished month
        import calendar
        d = (reach.get(m, {}).get("ALL") or {}).get("days")
        if d is None or m >= date.today().strftime("%Y-%m"):
            return False
        y, mo = map(int, m.split("-"))
        return d < calendar.monthrange(y, mo)[1]
    rows_def = [
        ("Views", lambda m, t: fmt(g(m, t, "views"))),
        ("Engaged views", lambda m, t: fmt(g(m, t, "engaged_views"))),
        ("Engaged %", lambda m, t: pct(g(m, t, "engaged_views") / g(m, t, "views")) if g(m, t, "views") else "—"),
        ("Watch time (hrs)", lambda m, t: fmt(g(m, t, "watch_hours"))),
        ("Avg view duration*", lambda m, t: _dur(g(m, t, "avg_view_sec"))),
        ("Avg % viewed*", lambda m, t: "—" if g(m, t, "avg_pct_viewed") is None else f'{g(m, t, "avg_pct_viewed"):.1f}%'),
        ("Likes", lambda m, t: fmt(g(m, t, "likes"))),
        ("Comments", lambda m, t: fmt(g(m, t, "comments"))),
        ("Shares", lambda m, t: fmt(g(m, t, "shares"))),
        ("Impressions", lambda m, t: fmt(rg(m, t, "impressions")) + (" †" if partial(m) else "")),
        ("Impressions CTR", lambda m, t: pct(rg(m, t, "ctr"))),
        ("Still watching at 0:30‡", lambda m, t: pct(rr(m, t, "r30"))),
        ("Still watching at 1:00‡", lambda m, t: pct(rr(m, t, "r60"))),
    ]
    split = any(g(m, "EPISODES", "views") is not None for m in months)
    types = [t for t in (("EPISODES", "CLIPS") if split else ("VIDS",)) + ("SHORTS", "LIVES") if any(g(m, t, "views") for m in months)]
    head = "".join(f"<th>{_mon(m)}</th>" for m in months)
    body = ""
    for t in types:
        body += (f'<tr><td style="font-weight:700;text-align:left">{LABEL[t]}</td>' + "".join("<td></td>" for _ in months) + "</tr>")
        for name, fn in rows_def:
            if name.startswith("Impressions") and not any(rg(m, t, "impressions") for m in months):
                continue
            if name.startswith("Still watching") and not any(rr(m, t, "r30") is not None for m in months):
                continue
            body += f'<tr><td style="text-align:left;padding-left:18px">{name}</td>' + "".join(f"<td>{fn(m, t)}</td>" for m in months) + "</tr>"

    def card(label, value, sub=""):
        return (f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{value}</div>'
                f'<div class="metric-delta" style="color:var(--text2)">{sub}</div></div>')
    cards = (card(f"Watch time · {_mon(cur)}", f'{fmt(g(cur, "ALL", "watch_hours"))} hrs',
                  f'videos avg {_dur(g(cur, "VIDS", "avg_view_sec"))} · {g(cur, "VIDS", "avg_pct_viewed") or 0:.0f}% viewed')
             + card(f"Engaged views · {_mon(cur)}", fmt(g(cur, "ALL", "engaged_views")),
                    pct(g(cur, "ALL", "engaged_views") / g(cur, "ALL", "views")) + " of views" if g(cur, "ALL", "views") else "")
             + card(f"Impressions · {_mon(cur)}", fmt(rg(cur, "ALL", "impressions")) if rg(cur, "ALL", "impressions") else "—",
                    f'CTR {pct(rg(cur, "ALL", "ctr"))}' if rg(cur, "ALL", "ctr") is not None else "Reporting API — fills in daily")
             + card(f"Likes · comments · shares", fmt((g(cur, "ALL", "likes") or 0) + (g(cur, "ALL", "comments") or 0) + (g(cur, "ALL", "shares") or 0)),
                    f'{fmt(g(cur, "ALL", "likes"))} · {fmt(g(cur, "ALL", "comments"))} · {fmt(g(cur, "ALL", "shares"))} in {_mon(cur)}'))
    through = (kpis or {}).get("reach_through")
    return f"""
    <div class="card">
      <div class="card-title">YouTube KPIs · by month</div>
      <div class="metrics">{cards}</div>
      <div class="table-scroll"><table class="data-table"><thead><tr><th style="text-align:left">Metric</th>{head}</tr></thead>
      <tbody>{body}</tbody></table></div>
      <div class="metric-delta" style="color:var(--text2);margin-top:8px">YouTube Analytics API · {_mon(cur)} to date.
        * per engaged view (YouTube's definition: watch time ÷ engaged views). Full episodes = the show's full-episode
        playlists; clips = other long-form. † month only partly covered by daily reports. ‡ still watching = organic viewers at 0:30 / 1:00 on long-form uploads published
        that month (view-weighted, from each video's retention curve).
        Impressions / CTR = thumbnail impressions from the YouTube Reporting API{f" (through {through})" if through else " — filling in from daily reports"}.</div>
    </div>"""
