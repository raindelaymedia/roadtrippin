"""
RDM — Competitive Landscape page (internal)
===========================================
Builds master/competitors/competitors.html from the daily snapshots that
collect_competitors.py writes. Linked from the RDM landing page only.

What it shows: a Monday digest (last Mon–Sun week: where our shows rank, top breakouts), then per group
(Basketball / Football / Women's), our shows highlighted:
  • Rank by views gained over the last 7 days, places moved vs the 7 days before, gap to the show above
  • What's working: every upload scored vs its own show's normal at 48 hours, then compared by topic (names in
    titles), title style, format, and day / time posted (ET)
  • Views gained over 7 and 28 days (channel view-count change) — fills in as history builds
  • Uploads in the last 28 days by format, and the views those uploads have now
  • Median views per full episode, episodes per week, last upload, subscribers
  • Top uploads of the last 7 days across the group

Formats: Short ≤ 3:00 · Clip 3:01–20:00 · Episode > 20:00 (podcast episodes often run 20–30 min,
so the cut-off is lower than the show dashboards' 30 min).

Usage (from repo root):
    python master/competitors/build_competitors.py
"""

import csv
import glob
import json
import os
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "competitors.html")
WINDOW = 28
INACTIVE_DAYS = 30
EPISODE_MIN_SEC = 20 * 60
AGES = (1, 3, 7)            # episode views measured this many days after upload
BREAKOUT_X = 3.0            # breakout = at least this many x the show's normal
BREAKOUT_AGE = 2            # ... measured at 48 hours
BREAKOUT_MIN_VIEWS = 1000   # ignore tiny numbers
BASELINE_MIN = 5            # uploads needed for a same-age baseline
ET = ZoneInfo("America/New_York")
FORMATS = [("episode", "Episodes", "#1E3A5F"), ("clip", "Clips", "#3B82F6"), ("short", "Shorts", "#C9A84C")]


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def fmt(v):
    if v is None:
        return "—"
    a = abs(v)
    if a >= 1e9: return f"{v/1e9:.2f}B"
    if a >= 1e6: return f"{v/1e6:.1f}M"
    if a >= 1e4: return f"{v/1e3:.0f}K"
    if a >= 1e3: return f"{v/1e3:.1f}K"
    return f"{int(v):,}"


def md(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.strftime('%b')} {d.day}"


def hms(secs):
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def video_format(secs):
    return "short" if secs <= 180 else "clip" if secs <= EPISODE_MIN_SEC else "episode"


def load():
    shows = read_csv(os.path.join(HERE, "competitors.csv"))
    daily = defaultdict(dict)                       # date -> channel_id -> row
    for r in read_csv(os.path.join(DATA, "channel_daily.csv")):
        daily[r["date"]][r["channel_id"]] = r
    videos = {r["video_id"]: r for r in read_csv(os.path.join(DATA, "videos.csv"))}
    vdaily = {}                                     # date -> video_id -> views
    for p in sorted(glob.glob(os.path.join(DATA, "video_daily", "*.csv"))):
        vdaily[os.path.basename(p)[:10]] = {r["video_id"]: num(r["views"]) for r in read_csv(p)}
    return shows, daily, videos, vdaily


def gained(daily, dates, cid, days, field="views"):
    """Change in a channel total over `days`, or None until there's that much history."""
    d1 = dates[-1]
    target = (datetime.strptime(d1, "%Y-%m-%d").date() - timedelta(days=days)).isoformat()
    base = next((d for d in reversed(dates) if d <= target), None)
    if not base:
        return None
    a, b = num(daily[d1].get(cid, {}).get(field)), num(daily[base].get(cid, {}).get(field))
    return a - b if a is not None and b is not None else None


def views_at(vdaily, v, age):
    """Views in the snapshot taken `age` days after upload (None if that day wasn't captured)."""
    d = (datetime.strptime(v["published"], "%Y-%m-%d").date() + timedelta(days=age)).isoformat()
    return vdaily.get(d, {}).get(v["video_id"])


def score_uploads(vids, vdaily, today, views_now, since):
    """Every upload published since `since` (and at least a day old) scored against its own show:
    views at 48 hours (or its age, if younger) ÷ the median of the same show's same-format uploads at the same
    age. 1.0 = normal for that show; 3.0+ = breakout. Puts big and small channels on one scale.
    Normal = same-age median once BASELINE_MIN exist; until then the show's recent median (a conservative bar)."""
    out = []
    for v in vids:
        if v["published"] < since:
            continue
        age_now = (today - datetime.strptime(v["published"], "%Y-%m-%d").date()).days
        if age_now < 1:
            continue
        a = min(BREAKOUT_AGE, age_now)
        val = views_at(vdaily, v, a)
        if val is None:
            continue
        same = [o for o in vids if o["video_id"] != v["video_id"] and o["format"] == v["format"]]
        base = [x for x in (views_at(vdaily, o, a) for o in same) if x is not None]
        method = "same age"
        if len(base) < BASELINE_MIN:
            base = [views_now[o["video_id"]] for o in same if views_now.get(o["video_id"]) is not None
                    and (today - datetime.strptime(o["published"], "%Y-%m-%d").date()).days >= a]
            method = "recent median"
        if len(base) < 3:
            continue
        med = statistics.median(base)
        if med > 0:
            out.append({**v, "at": val, "age": a, "ratio": val / med, "normal": med, "method": method})
    return out


def find_breakouts(scores, today):
    """Uploads from the last 7 days running BREAKOUT_X× their show's normal (and not tiny)."""
    week = (today - timedelta(days=6)).isoformat()
    return [s for s in scores if s["published"] >= week and s["ratio"] >= BREAKOUT_X and s["at"] >= BREAKOUT_MIN_VIEWS]


def gained_between(daily, dates, cid, end_days_ago, days, field="views"):
    """Change in a channel total over the `days` ending `end_days_ago` days before the latest snapshot."""
    last = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    end, start = (last - timedelta(days=end_days_ago)).isoformat(), (last - timedelta(days=end_days_ago + days)).isoformat()
    if end not in daily or start not in daily:
        return None
    a, b = num(daily[end].get(cid, {}).get(field)), num(daily[start].get(cid, {}).get(field))
    return a - b if a is not None and b is not None else None


# ── What's working: topics, title style, timing ────────────────────────────────────────────
STOP = set("""a an and are as at be but by for from has have he her his how i if in into is it its just me my no not of on or
our out says say so than that the their them they this to up us was we were what when where which who why will with you your
vs vs. new full ep episode podcast show live reacts react reaction breaks break talks talk explains explain reveals reveal
week season game games team teams nba nfl wnba draft trade best worst top next last first one two three big real why's he's
don't can't won't it's that's there's here's did does do got get gets go goes going says said tells told can could would should
just only all more most every after before over about back still now today tonight night year years day time way thing things""".split())
CAP_WORD = re.compile(r"[A-Z][A-Za-z'’.-]+|[A-Z]{2,}")


def title_terms(title):
    """Names/topics in a title: runs of capitalised words (1–3), stop-words trimmed. 'LeBron James', 'Luka', 'Chiefs'."""
    words = re.findall(r"[A-Za-z0-9'’.&-]+", title)
    terms, run = set(), []

    def flush():
        while run and run[0].lower().strip("'’.") in STOP:
            run.pop(0)
        while run and run[-1].lower().strip("'’.") in STOP:
            run.pop()
        if run:
            t = " ".join(w.strip(".").title() if w.isupper() and len(w.strip(".")) > 4 else w.strip(".") for w in run[:3])
            t = re.sub(r"['’]s$", "", t)
            if len(t) >= 3 and t.lower() not in STOP:
                terms.add(t)
        run.clear()

    for i, w in enumerate(words):
        if CAP_WORD.fullmatch(w) and not (i == 0 and w.lower() in STOP):
            run.append(w)
        else:
            flush()
    flush()
    return terms


def title_style(title):
    letters = [w for w in re.findall(r"[A-Za-z]{4,}", title)]
    return {
        "Question in title": "?" in title,
        "Number in title": bool(re.search(r"\d", title)),
        "ALL-CAPS word": any(w.isupper() for w in letters),
        "Emoji": bool(re.search(r"[\U0001F300-\U0001FAFF☀-➿]", title)),
        "Long title (60+ characters)": len(title) >= 60,
    }


def working_html(scores):
    """Content intelligence for one group from its scored uploads (last 28 days)."""
    if len(scores) < 20:
        return '<div class="sub">Needs a few more weeks of uploads to read patterns.</div>'
    med = lambda xs: statistics.median(xs) if xs else None
    overall = med([s["ratio"] for s in scores])
    lift = lambda xs: (med(xs) / overall) if xs and overall else None
    pct = lambda x: f"{(x - 1) * 100:+.0f}%" if x is not None else "—"
    cls = lambda x: "up" if (x or 1) >= 1.15 else "down" if (x or 1) <= 0.87 else ""

    # Topics: at least 4 uploads from at least 2 shows
    by_term = defaultdict(list)
    for s in scores:
        for t in title_terms(s["title"]):
            by_term[t].append(s)
    topics = []
    for t, ss in by_term.items():
        shows = {s["channel_id"] for s in ss}
        if len(ss) >= 4 and len(shows) >= 2:
            topics.append((t, lift([s["ratio"] for s in ss]), len(ss), len(shows)))
    hot = sorted(topics, key=lambda x: -x[1])[:8]
    busy = sorted(topics, key=lambda x: -x[2])[:6]
    topic_rows = "".join(f'<tr><td>{t}</td><td class="n {cls(l)}">{pct(l)}</td><td class="n sub">{n} uploads · {k} shows</td></tr>'
                         for t, l, n, k in hot) or '<tr><td class="sub" colspan="3">No recurring topics yet.</td></tr>'
    busy_txt = " · ".join(f"{t} ({n})" for t, l, n, k in busy)

    # Title style
    style_rows = ""
    for feat in title_style("").keys():
        yes = [s["ratio"] for s in scores if title_style(s["title"])[feat]]
        no = [s["ratio"] for s in scores if not title_style(s["title"])[feat]]
        if len(yes) >= 8 and len(no) >= 8:
            l = med(yes) / med(no)
            style_rows += (f'<tr><td>{feat}</td><td class="n {cls(l)}">{pct(l)}</td>'
                           f'<td class="n sub">{len(yes)} with · {len(no)} without</td></tr>')

    # Format
    fmt_rows = "".join(
        f'<tr><td>{l}</td><td class="n {cls(lift([s["ratio"] for s in scores if s["format"] == f]))}">'
        f'{pct(lift([s["ratio"] for s in scores if s["format"] == f]))}</td>'
        f'<td class="n sub">{sum(1 for s in scores if s["format"] == f)} uploads · '
        f'{sum(1 for s in scores if s["format"] == f and s["ratio"] >= BREAKOUT_X)} breakouts</td></tr>'
        for f, l, _ in FORMATS if sum(1 for s in scores if s["format"] == f) >= 5)

    # Timing (ET)
    timed = [s for s in scores if s.get("published_at")]
    days = defaultdict(list)
    slots = defaultdict(list)
    slot_of = lambda h: ("Overnight (12–6a)" if h < 6 else "Morning (6a–12p)" if h < 12 else "Afternoon (12–5p)" if h < 17
                         else "Evening (5–9p)" if h < 21 else "Late (9p–12a)")
    for s in timed:
        t = datetime.strptime(s["published_at"], "%Y-%m-%dT%H:%M")
        days[t.strftime("%a")].append(s["ratio"])
        slots[slot_of(t.hour)].append(s["ratio"])
    day_rows = "".join(f'<tr><td>{d}</td><td class="n {cls(lift(days[d]))}">{pct(lift(days[d]))}</td><td class="n sub">{len(days[d])}</td></tr>'
                       for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") if len(days[d]) >= 5)
    slot_rows = "".join(f'<tr><td>{k}</td><td class="n {cls(lift(v))}">{pct(lift(v))}</td><td class="n sub">{len(v)}</td></tr>'
                        for k, v in sorted(slots.items(), key=lambda kv: ["Overnight", "Morning", "Afternoon", "Evening", "Late"].index(kv[0].split()[0]))
                        if len(v) >= 5)
    tbl = lambda head, rows: (f'<table class="lb wk"><thead><tr><th>{head}</th><th class="n">vs normal</th><th class="n">sample</th></tr></thead>'
                              f'<tbody>{rows}</tbody></table>')
    return f"""
      <div class="sub" style="margin-bottom:10px">How uploads with each trait did at 48 hours compared with their own show's normal,
        across {len(scores)} uploads from the last 28 days. +50% = these did half again better than usual for whoever posted them.
        Most-covered topics: {busy_txt or '—'}.</div>
      <div class="grid3">
        <div><h4>Topics that over-perform</h4>{tbl("Topic in title", topic_rows)}</div>
        <div><h4>Title style</h4>{tbl("Title has…", style_rows or '<tr><td class="sub" colspan="3">Not enough uploads.</td></tr>')}
             <h4 style="margin-top:14px">Format</h4>{tbl("Format", fmt_rows)}</div>
        <div><h4>Day posted (ET)</h4>{tbl("Day", day_rows)}<h4 style="margin-top:14px">Time posted (ET)</h4>{tbl("Time", slot_rows)}</div>
      </div>"""


def digest_html(rows, daily, dates, groups):
    """Monday digest: the last full Mon–Sun week, from the Monday snapshots on either side of it."""
    last = datetime.strptime(dates[-1], "%Y-%m-%d").date()
    mon = last - timedelta(days=last.weekday())                 # most recent Monday snapshot
    prev = mon - timedelta(days=7)
    if mon.isoformat() not in daily or prev.isoformat() not in daily:
        return ""
    wk_start, wk_end = prev, mon - timedelta(days=1)
    g = lambda d0, d1, cid: (lambda a, b: a - b if a is not None and b is not None else None)(
        num(daily.get(d1.isoformat(), {}).get(cid, {}).get("views")), num(daily.get(d0.isoformat(), {}).get(cid, {}).get("views")))
    have_prior = (prev - timedelta(days=7)).isoformat() in daily
    lines = []
    for grp in groups:
        gr = [r for r in rows if r["group"] == grp and g(prev, mon, r["channel_id"]) is not None]   # shows with the full week
        wk = {r["channel_id"]: g(prev, mon, r["channel_id"]) for r in gr}
        pr = {r["channel_id"]: g(prev - timedelta(days=7), prev, r["channel_id"]) for r in gr} if have_prior else {}
        order = sorted(gr, key=lambda r: -(wk[r["channel_id"]] or 0))
        porder = sorted(gr, key=lambda r: -(pr.get(r["channel_id"]) or 0)) if have_prior else []
        for r in [x for x in order if x["ours"]]:
            rk = order.index(r) + 1
            mv = ""
            if have_prior:
                d = porder.index(r) + 1 - rk
                mv = f' <span class="{"up" if d > 0 else "down" if d < 0 else "sub"}">{"▲" + str(d) if d > 0 else "▼" + str(-d) if d < 0 else "—"}</span>'
            ch = ""
            if have_prior and pr.get(r["channel_id"]):
                c = wk[r["channel_id"]] / pr[r["channel_id"]] - 1
                ch = f' · <span class="{"up" if c >= 0 else "down"}">{c * 100:+.0f}% vs the week before</span>'
            lines.append(f'<li><b>★ {r["show"]}</b> · #{rk} of {len(order)} in {grp}{mv} · {fmt(wk[r["channel_id"]])} views gained{ch}</li>')
        if have_prior:
            movers = sorted((r for r in gr if pr.get(r["channel_id"]) and pr[r["channel_id"]] > 50_000),
                            key=lambda r: -(wk[r["channel_id"]] or 0) / pr[r["channel_id"]])[:1]
            for r in movers:
                lines.append(f'<li>Biggest riser in {grp}: {r["show"]} ({(wk[r["channel_id"]] / pr[r["channel_id"]] - 1) * 100:+.0f}% week over week)</li>')
    bo = sorted((dict(b, show=r["show"]) for r in rows for b in r["scores"]
                 if wk_start.isoformat() <= b["published"] <= wk_end.isoformat() and b["ratio"] >= BREAKOUT_X
                 and b["at"] >= BREAKOUT_MIN_VIEWS), key=lambda b: -b["ratio"])[:5]
    bo_html = "".join(f'<li><span class="x">{b["ratio"]:.1f}×</span> <a href="https://youtu.be/{b["video_id"]}" target="_blank" rel="noopener">'
                      f'{b["title"][:90]}</a> <span class="sub">· {b["show"]}</span></li>' for b in bo)
    return f"""
  <div class="card digest">
    <div class="card-h"><h3>This week · {md(wk_start.isoformat())} – {md(wk_end.isoformat())}</h3>
      <span class="r">ranked by views gained Mon–Sun{'' if have_prior else ' · week-over-week moves start next Monday'}</span></div>
    <div class="grid2">
      <div><h4>Where we stand</h4><ul class="dl">{''.join(lines)}</ul></div>
      <div><h4>Top breakouts of the week</h4><ul class="dl">{bo_html or '<li class="sub">None this week.</li>'}</ul></div>
    </div>
  </div>"""


def summarize(shows, daily, videos, vdaily):
    dates = sorted(daily)
    d1 = dates[-1]
    today = datetime.strptime(d1, "%Y-%m-%d").date()
    since = (today - timedelta(days=WINDOW - 1)).isoformat()
    week = (today - timedelta(days=6)).isoformat()
    views_now = vdaily.get(d1, {})
    by_channel = defaultdict(list)
    for vid, v in videos.items():
        if vid in views_now:     # every tracked upload (last ~35 days); 28-day stats filter below
            by_channel[v["channel_id"]].append({**v, "views": views_now[vid] or 0,
                                                "format": video_format(num(v["duration_sec"]) or 0)})
    rows = []
    for s in shows:
        cid = s["channel_id"]
        c = daily[d1].get(cid, {})
        tracked = by_channel.get(cid, [])
        vs = [v for v in tracked if v["published"] >= since]
        eps = [v["views"] for v in vs if v["format"] == "episode"]
        ep_age = {}
        for a in AGES:
            xs = [x for x in (views_at(vdaily, v, a) for v in tracked if v["format"] == "episode") if x is not None]
            ep_age[a] = (round(statistics.median(xs)) if xs else None, len(xs))
        last = c.get("last_upload") or ""
        rows.append({
            **s, "ours": s["ours"] == "1",
            "subs": num(c.get("subs")), "views_total": num(c.get("views")),
            "gain7": gained(daily, dates, cid, 7), "gain28": gained(daily, dates, cid, 28),
            "gain1": gained(daily, dates, cid, 1),
            "subs28": gained(daily, dates, cid, 28, "subs"),
            "uploads": {f: sum(1 for v in vs if v["format"] == f) for f, *_ in FORMATS},
            "upload_views": {f: sum(v["views"] for v in vs if v["format"] == f) for f, *_ in FORMATS},
            "median_ep": round(statistics.median(eps)) if eps else None,
            "eps_week": round(len(eps) / (WINDOW / 7), 1),
            "last_upload": last,
            "inactive": bool(last) and (today - datetime.strptime(last, "%Y-%m-%d").date()).days > INACTIVE_DAYS,
            "top": sorted((v for v in vs if v["published"] >= week), key=lambda v: -v["views"])[:3],
            "ep_age": ep_age,
            "scores": (sc := score_uploads(tracked, vdaily, today, views_now, since)),
            "breakouts": find_breakouts(sc, today),
            "gain7_prev": gained_between(daily, dates, cid, 7, 7),
        })
    for r in rows:
        r["upload_views_total"] = sum(r["upload_views"].values())
    # Views gained per day, per channel (for the trend chart once there's history)
    trend = {}
    for s in shows:
        cid, pts = s["channel_id"], []
        for a, b in zip(dates, dates[1:]):
            va, vb = num(daily[a].get(cid, {}).get("views")), num(daily[b].get(cid, {}).get("views"))
            pts.append(vb - va if va is not None and vb is not None else None)
        trend[cid] = pts
    return rows, dates, trend


def group_html(group, rows, dates, trend, gi):
    g = [r for r in rows if r["group"] == group]
    have28 = any(r["gain28"] is not None for r in g)
    have7 = any(r["gain7"] is not None for r in g)
    if have7:
        key, key_lbl = (lambda r: r["gain7"] or 0), "views gained · last 7 days"
    elif have28:
        key, key_lbl = (lambda r: r["gain28"] or 0), "views gained · last 28 days"
    else:
        key, key_lbl = (lambda r: r["upload_views_total"]), "views on last-28-day uploads"
    g.sort(key=lambda r: (-key(r), r["show"]))
    ours = [r for r in g if r["ours"]]
    have_prev = have7 and any(r["gain7_prev"] is not None for r in g)
    prev_rank = ({r["channel_id"]: k for k, r in enumerate(sorted(g, key=lambda r: -(r["gain7_prev"] or 0)), 1)}
                 if have_prev else {})
    group_week = sum(max(r["gain7"] or 0, 0) for r in g) if have7 else 0
    # Shows added recently have no 7-day figure yet: they sit at the bottom and don't count in "#N of M"
    n_ranked = sum(1 for r in g if r["gain7"] is not None) if have7 else len(g)
    newcomers = [r["show"] for r in g if have7 and r["gain7"] is None]

    # Headline tiles for our show(s) in this group
    tiles = ""
    for r in ours:
        rank = g.index(r) + 1
        lead = g[0] if g[0] is not r else (g[1] if len(g) > 1 else None)
        above = g[rank - 2] if rank > 1 else None
        mv = ""
        if have_prev:
            d = prev_rank[r["channel_id"]] - rank
            mv = (f'<span class="mv up">▲{d}</span>' if d > 0 else f'<span class="mv down">▼{-d}</span>' if d < 0
                  else '<span class="mv sub">no change</span>')
        wow = ""
        if have7 and r["gain7_prev"]:
            c = (r["gain7"] or 0) / r["gain7_prev"] - 1
            wow = f'<br><span class="{"up" if c >= 0 else "down"}">{c * 100:+.0f}%</span> vs the 7 days before'
        share = f" · {max(r['gain7'] or 0, 0) / group_week * 100:.1f}% of the group's views gained" if have7 and group_week else ""
        gap = (f"<br>{fmt(key(above) - key(r))} more to pass {above['show']} (#{rank - 1})" if above else "<br>Leading the group")
        tiles += f"""
      <div class="tile ours-tile">
        <div class="t-l">★ {r['show']}</div>
        <div class="t-v">#{rank} <small>of {n_ranked}</small> {mv}</div>
        <div class="t-s">{key_lbl} · <b>{fmt(key(r))}</b>{share}{wow}{gap}
          {f"<br>Leader: {lead['show']} · {fmt(key(lead))}" if lead and rank > 2 else ''}</div>
      </div>"""

    # Leaderboard
    def cell(v, cls=""):
        return f'<td class="n {cls}">{fmt(v)}</td>'
    body = ""
    for i, r in enumerate(g, 1):
        up = r["uploads"]
        status = (f'<span class="badge">inactive · last {md(r["last_upload"])}</span>' if r["inactive"]
                  else f'<span class="sub">last upload {md(r["last_upload"])}</span>' if r["last_upload"] else "")
        d = (prev_rank[r["channel_id"]] - i) if have_prev else 0
        mvc = (f'<div class="mv up">▲{d}</div>' if d > 0 else f'<div class="mv down">▼{-d}</div>' if d < 0 else "")
        body += (f'<tr class="{"ours" if r["ours"] else ""}"><td class="rk">{i}{mvc}</td>'
                 f'<td class="sh"><a href="https://www.youtube.com/channel/{r["channel_id"]}" target="_blank" rel="noopener">'
                 f'{"★ " if r["ours"] else ""}{r["show"]}</a><div class="sub">{r["subgroup"]} · {status}</div></td>'
                 + cell(r["subs"]) + cell(r["gain7"], "" if have7 else "pending")
                 + cell(r["gain28"], "" if have28 else "pending")
                 + f'<td class="n">{up["episode"]} · {up["clip"]} · {up["short"]}</td>'
                 + cell(r["upload_views_total"])
                 + (f'<td class="n">{fmt(r["ep_age"][7][0])}<div class="sub">{r["ep_age"][7][1]} ep</div></td>'
                    if r["ep_age"][7][1] else '<td class="n pending">—</td>')
                 + f'<td class="n">{r["eps_week"] if up["episode"] else "—"}</td></tr>')

    # Charts data
    chart_rows = [r for r in g if r["upload_views_total"] or not r["inactive"]]   # inactive shows: table only
    labels = [("★ " if r["ours"] else "") + r["show"] for r in chart_rows]
    bars = {f: [r["upload_views"][f] for r in chart_rows] for f, *_ in FORMATS}
    trend_rows = [r for r in g if any(v is not None for v in trend[r["channel_id"]])]
    pick = sorted(trend_rows, key=lambda r: -(r["gain7"] or r["gain1"] or 0))[:5]
    pick += [r for r in trend_rows if r["ours"] and r not in pick]          # our show is always on the chart
    trend_sets = [{"label": ("★ " if r["ours"] else "") + r["show"], "data": trend[r["channel_id"]],
                   "ours": r["ours"]} for r in pick]
    top = sorted((dict(v, show=r["show"], ours=r["ours"]) for r in g for v in r["top"]), key=lambda v: -v["views"])[:10]
    top_html = "".join(
        f'<tr class="{"ours" if v["ours"] else ""}"><td class="n">{fmt(v["views"])}</td>'
        f'<td><a href="https://youtu.be/{v["video_id"]}" target="_blank" rel="noopener">{v["title"]}</a>'
        f'<div class="sub">{v["show"]} · {md(v["published"])} · {dict((f, l) for f, l, _ in FORMATS)[v["format"]][:-1]}</div></td></tr>'
        for v in top) or '<tr><td colspan="2" class="sub">No uploads in the last 7 days.</td></tr>'

    # Episode views by age (day 1 / 3 / 7), shows with any measured episode
    aged = [r for r in g if any(r["ep_age"][a][1] for a in AGES)]
    aged.sort(key=lambda r: (r["ep_age"][7][0] is None, -(r["ep_age"][7][0] or 0), -(r["ep_age"][1][0] or 0)))
    top7 = max([r["ep_age"][7][0] or 0 for r in aged] + [1])
    age_rows = "".join(
        f'<tr class="{"ours" if r["ours"] else ""}"><td class="sh">{"★ " if r["ours"] else ""}{r["show"]}</td>'
        + "".join(f'<td class="n">{fmt(r["ep_age"][a][0])}<div class="sub">{r["ep_age"][a][1] or "no"} ep</div></td>' for a in AGES)
        + f'<td class="barcell"><div class="bar" style="width:{(r["ep_age"][7][0] or 0) / top7 * 100:.0f}%"></div></td></tr>'
        for r in aged) or (f'<tr><td class="sub" colspan="5">Fills in as episodes reach day 1, 3 and 7 '
                           f'(tracking since {md(dates[0])}).</td></tr>')

    # Breakouts across the group
    bo = sorted((dict(b, show=r["show"], ours=r["ours"]) for r in g for b in r["breakouts"]),
                key=lambda b: -b["ratio"])[:8]

    def when(b):
        if b.get("published_at"):
            t = datetime.strptime(b["published_at"], "%Y-%m-%dT%H:%M")
            return f'{t.strftime("%a")} {md(b["published"])} · {t.strftime("%I:%M %p").lstrip("0")} ET'
        return md(b["published"])

    fmt_name = {f: l[:-1] for f, l, _ in FORMATS}
    no_bo = f"No uploads from the last 7 days are running {BREAKOUT_X:.0f}× their show's normal."
    bo_rows = "".join(
        f'<tr class="{"ours" if b["ours"] else ""}"><td class="n"><span class="x">{b["ratio"]:.1f}×</span></td>'
        f'<td><a href="https://youtu.be/{b["video_id"]}" target="_blank" rel="noopener">{b["title"]}</a>'
        f'<div class="sub">{b["show"]} · {fmt_name[b["format"]]} · {hms(num(b["duration_sec"]) or 0)} · {when(b)}<br>'
        f'{fmt(b["at"])} views at {"48h" if b["age"] == 2 else str(b["age"] * 24) + "h"} vs normal {fmt(b["normal"])}'
        f'{" (rough: recent median)" if b["method"] != "same age" else ""}</div></td></tr>'
        for b in bo) or f'<tr><td class="sub" colspan="2">{no_bo}</td></tr>'

    trend_block = (f'<canvas id="trend{gi}"></canvas>' if len(dates) >= 3 else
                   f'<div class="pending-box">Daily views gained starts drawing after a few days of snapshots '
                   f'(tracking since {md(dates[0])}).</div>')
    chart_data = json.dumps({"labels": labels, "bars": bars, "trend": trend_sets,
                             "days": [md(d) for d in dates[1:]]})
    return f"""
  <section class="group" id="g{gi}" {'hidden' if gi else ''}>
    <div class="tiles">{tiles}</div>
    <div class="card">
      <div class="card-h"><h3>Views on uploads from the last 28 days</h3><span class="r">current views of everything published {md((datetime.strptime(dates[-1], '%Y-%m-%d') - timedelta(days=WINDOW-1)).strftime('%Y-%m-%d'))} – {md(dates[-1])}, by format</span></div>
      <div style="position:relative;height:{max(len(chart_rows) * 30 + 60, 220)}px"><canvas id="bars{gi}"></canvas></div>
    </div>
    <div class="card">
      <div class="card-h"><h3>Leaderboard</h3><span class="r">sorted by {key_lbl}{' · ▲▼ = places moved vs the 7 days before' if have_prev else ''}{f' · {len(newcomers)} newly added shows join the ranking once they have 7 days of history' if newcomers else ''}</span></div>
      <div class="scroll"><table class="lb">
        <thead><tr><th>#</th><th>Show</th><th class="n">Subscribers</th><th class="n">Views gained · 7d</th><th class="n">Views gained · 28d</th>
          <th class="n">Uploads 28d<br><span class="sub">ep · clip · short</span></th><th class="n">Views on 28d uploads</th>
          <th class="n">Episode views<br><span class="sub">day 7 · median</span></th><th class="n">Episodes / week</th></tr></thead>
        <tbody>{body}</tbody></table></div>
    </div>
    <div class="grid2">
      <div class="card">
        <div class="card-h"><h3>Episode views by age</h3><span class="r">median views of full episodes 1, 3 and 7 days after upload</span></div>
        <div class="scroll"><table class="lb age"><thead><tr><th>Show</th><th class="n">Day 1</th><th class="n">Day 3</th><th class="n">Day 7</th><th></th></tr></thead>
          <tbody>{age_rows}</tbody></table></div>
      </div>
      <div class="card">
        <div class="card-h"><h3>Breakouts · last 7 days</h3><span class="r">{BREAKOUT_X:.0f}×+ the show's normal at 48 hours</span></div>
        <table class="top">{bo_rows}</table>
      </div>
    </div>
    <div class="grid2">
      <div class="card">
        <div class="card-h"><h3>Views gained per day</h3><span class="r">top 5 by last-7-day gains + ours</span></div>
        <div style="position:relative;height:260px">{trend_block}</div>
      </div>
      <div class="card">
        <div class="card-h"><h3>Top uploads · last 7 days</h3><span class="r">current views</span></div>
        <table class="top">{top_html}</table>
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h3>What's working in {group}</h3><span class="r">last 28 days · every show's uploads vs its own normal at 48 hours</span></div>
      {working_html([sc for r in g for sc in r["scores"]])}
    </div>
    <script type="application/json" id="data{gi}">{chart_data}</script>
  </section>"""


def build():
    shows, daily, videos, vdaily = load()
    if not daily:
        raise SystemExit("No snapshots yet — run collect_competitors.py first.")
    rows, dates, trend = summarize(shows, daily, videos, vdaily)
    # Missed-day guard: every day from the first snapshot to today should have one
    today_et = datetime.now(ET).date()
    first = datetime.strptime(dates[0], "%Y-%m-%d").date()
    expected = [(first + timedelta(days=i)).isoformat() for i in range((today_et - first).days + 1)]
    have = set(dates) & set(vdaily)
    gaps = [d for d in expected if d not in have]
    stale = dates[-1] < today_et.isoformat()
    if gaps:
        print(f"::warning::Competitor snapshot missing for {', '.join(gaps)}")
    alert = ""
    if gaps:
        head = "Today's snapshot is missing." if stale else "History has gaps."
        alert = (f'<div class="alert"><b>{head}</b> No snapshot for {", ".join(md(d) for d in gaps)}. '
                 "Those days can't be recovered: check the \"Snapshot competitor channels\" step "
                 "in the daily workflow.</div>")
    groups = list(dict.fromkeys(s["group"] for s in shows))
    tabs = "".join(f'<button class="tab{" on" if i == 0 else ""}" data-g="{i}">{g}</button>' for i, g in enumerate(groups))
    sections = "".join(group_html(g, rows, dates, trend, i) for i, g in enumerate(groups))
    digest = digest_html(rows, daily, dates, groups)
    days = len(dates)
    legend = "".join(f'<span><i style="background:{c}"></i>{l}</span>' for _, l, c in FORMATS)
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Competitive Landscape — Rain Delay Media</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{ --bg:#F6F7F9; --surface:#FFFFFF; --surface2:#F1F3F6; --border:#E2E5EA; --ink:#0F172A; --text:#1E293B;
          --text2:#475569; --mut:#94A3B8; --brand:#1E3A5F; --gold:#C9A84C; --gold-soft:#FBF6E8; --radius:10px; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:'Inter',-apple-system,system-ui,sans-serif; color:var(--text); background:var(--bg); font-size:13px; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:28px 20px 60px; }}
  a {{ color:inherit; }}
  .back {{ font-size:12px; color:var(--text2); text-decoration:none; }}
  h1 {{ font-size:26px; margin:10px 0 4px; color:var(--ink); letter-spacing:-.01em; }}
  .lead {{ color:var(--text2); margin-bottom:16px; }}
  .note {{ background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--gold); border-radius:var(--radius);
          padding:10px 14px; color:var(--text2); margin-bottom:16px; font-size:12px; line-height:1.5; }}
  .alert {{ background:#FEF2F2; border:1px solid #FECACA; border-left:3px solid #DC2626; border-radius:var(--radius);
           padding:10px 14px; color:#7F1D1D; margin-bottom:16px; font-size:12px; line-height:1.5; }}
  .x {{ display:inline-block; font-weight:800; color:#065F46; background:#D1FAE5; padding:2px 6px; border-radius:4px; }}
  .age td.barcell {{ width:28%; }}
  .bar {{ height:8px; border-radius:4px; background:var(--brand); min-width:2px; }}
  tr.ours .bar {{ background:var(--gold); }}
  .tabs {{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:16px; }}
  .tab {{ border:1px solid var(--border); background:var(--surface); color:var(--text2); padding:7px 14px; border-radius:999px;
         font:600 12px Inter,sans-serif; cursor:pointer; }}
  .tab.on {{ background:var(--brand); border-color:var(--brand); color:#fff; }}
  .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; margin-bottom:12px; }}
  .tile {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; }}
  .ours-tile {{ border-color:var(--gold); background:var(--gold-soft); }}
  .t-l {{ font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color:var(--text2); }}
  .t-v {{ font-size:28px; font-weight:800; color:var(--ink); margin:4px 0; }} .t-v small {{ font-size:13px; color:var(--mut); font-weight:600; }}
  .t-s {{ font-size:12px; color:var(--text2); line-height:1.5; }}
  .card {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius); padding:16px 18px; margin-bottom:12px; }}
  .card-h {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:10px; }}
  .card-h h3 {{ margin:0; font-size:14px; color:var(--ink); }} .card-h .r {{ font-size:11px; color:var(--mut); }}
  .legend {{ display:flex; gap:14px; font-size:11px; color:var(--text2); margin:-2px 0 8px; }}
  .legend i {{ display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:5px; vertical-align:-1px; }}
  .grid2 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:12px; }}
  .scroll {{ overflow-x:auto; }}
  table {{ border-collapse:collapse; width:100%; }}
  .lb th {{ font-size:10.5px; text-transform:uppercase; letter-spacing:.05em; color:var(--mut); font-weight:700; text-align:left;
           padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; vertical-align:bottom; }}
  .lb td {{ padding:9px 10px; border-bottom:1px solid var(--surface2); vertical-align:top; }}
  .n {{ text-align:right !important; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .rk {{ color:var(--mut); width:28px; }}
  .sh a {{ font-weight:600; color:var(--ink); text-decoration:none; }} .sh a:hover {{ text-decoration:underline; }}
  .sub {{ font-size:11px; color:var(--mut); font-weight:400; text-transform:none; letter-spacing:0; }}
  tr.ours td {{ background:var(--gold-soft); }}
  .pending {{ color:var(--mut); }}
  .badge {{ font-size:10px; color:#92400E; background:#FEF3C7; padding:1px 6px; border-radius:4px; }}
  .top td {{ padding:7px 6px; border-bottom:1px solid var(--surface2); vertical-align:top; font-size:12px; }}
  .top a {{ color:var(--ink); text-decoration:none; }} .top a:hover {{ text-decoration:underline; }}
  .top td.n {{ width:64px; font-weight:700; color:var(--ink); }}
  .pending-box {{ height:100%; display:flex; align-items:center; justify-content:center; text-align:center; color:var(--mut); padding:0 30px; }}
  .grid3 {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; }}
  h4 {{ margin:0 0 6px; font-size:12px; color:var(--ink); }}
  .wk td {{ padding:6px 8px; }} .wk th {{ padding:6px 8px; }}
  .up {{ color:#047857; font-weight:700; }} .down {{ color:#B91C1C; font-weight:700; }}
  .mv {{ font-size:11px; font-weight:700; margin-left:6px; }} .rk .mv {{ margin-left:0; font-size:10px; }}
  .digest {{ border-left:3px solid var(--gold); }}
  .dl {{ margin:0; padding-left:18px; line-height:1.7; font-size:12.5px; }} .dl a {{ color:var(--ink); }}
  .foot {{ margin-top:22px; font-size:11px; color:var(--mut); line-height:1.6; }}
  @media (max-width:560px) {{ .wrap {{ padding:18px 16px 40px; }} h1 {{ font-size:21px; }} }}
</style></head><body><div class="wrap">
  <a class="back" href="../../index.html">← RDM Network</a>
  <h1>Competitive Landscape</h1>
  <div class="lead">Public YouTube stats for {len(shows)} shows · our shows marked ★ · snapshot {md(dates[-1])} · tracking since {md(dates[0])} ({days} day{'s' if days != 1 else ''})</div>
  {alert}
  {'' if days > 28 else f'<div class="note"><b>History is building.</b> Shows rank by views gained over the last 7 days (live from {md((datetime.strptime(dates[0], "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d"))}); week-over-week rank moves start {md((datetime.strptime(dates[0], "%Y-%m-%d") + timedelta(days=14)).strftime("%Y-%m-%d"))}; 28-day figures fill in from {md((datetime.strptime(dates[0], "%Y-%m-%d") + timedelta(days=28)).strftime("%Y-%m-%d"))}.</div>'}
  {digest}
  <div class="tabs">{tabs}</div>
  <div class="legend" id="legend">{legend}</div>
  {sections}
  <div class="foot">
    Internal use only. Views gained = change in the channel's public total view count. Formats by length: Short ≤ 3:00 · Clip 3:01–20:00 · Episode &gt; 20:00.
    Subscriber counts are rounded by YouTube (3 significant figures). Channel totals cover everything on the channel, so shows on shared
    network channels aren't tracked. Updated daily by the RDM workflow.
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const FORMATS = {json.dumps([[f, l, c] for f, l, c in FORMATS])};
const K = v => Math.abs(v) >= 1e6 ? (v/1e6).toFixed(1)+'M' : Math.abs(v) >= 1e3 ? (v/1e3).toFixed(0)+'K' : v;
const TREND_C = ['#1E3A5F','#3B82F6','#0EA5E9','#64748B','#94A3B8','#CBD5E1'];
Chart.defaults.font.family = "'Inter', system-ui, sans-serif"; Chart.defaults.color = '#475569';
const drawn = {{}};
function draw(i) {{
  if (drawn[i]) return; drawn[i] = true;
  const D = JSON.parse(document.getElementById('data'+i).textContent);
  new Chart(document.getElementById('bars'+i), {{
    type:'bar',
    data:{{ labels:D.labels, datasets:FORMATS.map(([f,l,c]) => ({{ label:l, data:D.bars[f], backgroundColor:c, borderRadius:3,
      borderColor:'#FFFFFF', borderWidth:{{ left:0, right:2, top:0, bottom:0 }}, borderSkipped:false, maxBarThickness:22 }})) }},
    options:{{ indexAxis:'y', responsive:true, maintainAspectRatio:false, interaction:{{ mode:'index', intersect:false, axis:'y' }},
      plugins:{{ legend:{{ display:false }}, tooltip:{{ callbacks:{{ label:c => ' '+c.dataset.label+': '+Math.round(c.parsed.x).toLocaleString(),
        footer:items => 'Total: '+items.reduce((a,c)=>a+c.parsed.x,0).toLocaleString() }} }} }},
      scales:{{ x:{{ stacked:true, grid:{{ color:'#EEF1F5' }}, ticks:{{ callback:K }} }},
               y:{{ stacked:true, grid:{{ display:false }}, ticks:{{ font:c => ({{ weight: String(D.labels[c.index]).startsWith('★') ? '700' : '400' }}),
                    color:c => String(D.labels[c.index]).startsWith('★') ? '#0F172A' : '#475569' }} }} }} }}
  }});
  const t = document.getElementById('trend'+i);
  if (t && D.trend.length) new Chart(t, {{
    type:'line',
    data:{{ labels:D.days, datasets:D.trend.map((s,j) => ({{ label:s.label, data:s.data, borderWidth:s.ours?3:2,
      borderColor:s.ours?'#C9A84C':TREND_C[j%TREND_C.length], backgroundColor:s.ours?'#C9A84C':TREND_C[j%TREND_C.length],
      pointRadius:3, pointHoverRadius:5, tension:.25, spanGaps:true }})) }},
    options:{{ responsive:true, maintainAspectRatio:false, interaction:{{ mode:'index', intersect:false }},
      plugins:{{ legend:{{ position:'bottom', labels:{{ boxWidth:10, boxHeight:10, font:{{ size:11 }} }} }},
        tooltip:{{ callbacks:{{ label:c => ' '+c.dataset.label+': '+(c.parsed.y==null?'—':Math.round(c.parsed.y).toLocaleString()) }} }} }},
      scales:{{ x:{{ grid:{{ display:false }} }}, y:{{ beginAtZero:true, grid:{{ color:'#EEF1F5' }}, ticks:{{ callback:K }} }} }} }}
  }});
}}
document.querySelectorAll('.tab').forEach(b => b.onclick = () => {{
  document.querySelectorAll('.tab').forEach(x => x.classList.toggle('on', x === b));
  document.querySelectorAll('.group').forEach((s,i) => s.hidden = String(i) !== b.dataset.g);
  draw(+b.dataset.g);
}});
draw(0);
</script>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ {os.path.relpath(OUT)} · {len(rows)} shows · {days} day(s) of history")


if __name__ == "__main__":
    build()
