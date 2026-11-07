"""
RDM — Weekly top content (per show, Mon–Sun)
============================================
One page per show (RT, GT, FR, SR): the top full episode (long-form), clip (mid-form) and Short (short-form) published
that week, the top social post, and the top audio episode vs last week's. Two versions of the same PDF:

  • views  — ranked by DAY-3 VIEWS (upload day + 3 days), so every upload in the week is compared at the same age.
  • grades — ranked by the content grade (master/content_grades.py): % viewed, CTR (Shorts: engaged %), views,
             engagement and subs per 1K, each vs the show's own uploads of that format at the same age.

Every card shows day-1 views (upload day + next day: the launch read), day-3 views and views to date. YouTube
reports views by calendar day, not by hour, so "day 1" covers 24–48 hours depending on upload time. Data runs about
two days behind: on a Friday, day 3 is complete for every upload of the previous Mon–Sun week. A card whose day 3
isn't in yet is marked with the last day available.

Social posts are ranked by views in both versions (no social grades yet). Sources: <show data>/content.json +
content/video_daily.csv (YouTube; run after the daily grading), TikTok daily snapshots + titles from the TikTok API,
Instagram via the API (IG_TOKEN_<SHOW>, checked against the show's handle), plus posts entered by hand in
master/weekly_social.csv (optional `note` column prints under the card). Audio: master/weekly_audio.csv, by hand
(week,show,title,downloads,prev_title,prev_downloads).

Usage (from repo root):
    python master/weekly_top.py                       # last full Mon–Sun week → both PDFs
    python master/weekly_top.py --week 2026-10-19
    python master/weekly_top.py --show rt gt
Output: master/weekly_reports/<week>/Top_Content_<week>_{views,grades}.pdf (+ .html)
"""

import argparse
import csv
import glob
import html
import importlib.util
import json
import os
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

MASTER = os.path.dirname(os.path.abspath(__file__))
RT = os.path.join(MASTER, "shows", "road_trippin")
OUT = os.path.join(MASTER, "weekly_reports")
AUDIO_CSV = os.path.join(MASTER, "weekly_audio.csv")
SOCIAL_CSV = os.path.join(MASTER, "weekly_social.csv")
SHOWS = {
    "rt": {"name": "Road Trippin'", "data": os.path.join(RT, "data"), "ig": "IG_TOKEN_RT", "handle": "roadtrippin",
           "tiktok": "rt", "accent": "#C9A84C"},
    "gt": {"name": "Girls Tripp", "data": os.path.join(RT, "data", "girls_tripp"), "ig": "IG_TOKEN_GT",
           "handle": "girlstripp", "tiktok": None, "accent": "#FF4370"},
    "fr": {"name": "Football Related", "data": os.path.join(RT, "data", "football_related", "data_fr"),
           "ig": "IG_TOKEN_FR", "handle": "footballrelated", "tiktok": None, "accent": "#1E7A46"},
    "sr": {"name": "The Schultz Report", "data": os.path.join(MASTER, "shows", "schultz_report", "data_sr"),
           "content": "content_sr.json", "ig": "IG_TOKEN_SR", "handle": "theschultzreport", "tiktok": "sr",
           "accent": "#11116b", "audio": "Simplecast"},
}
FORMATS = [("episode", "Top long-form", "full episode"), ("clip", "Top mid-form", "clip"), ("short", "Top short-form", "Short")]
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]


def _sync():
    spec = importlib.util.spec_from_file_location("sync_socials", os.path.join(MASTER, "sync_socials.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ── Data ─────────────────────────────────────────────────────────────────────
def youtube_uploads(data_dir, start, end, content="content.json"):
    """Uploads published in the week with grade values and day-1 / day-3 / to-date ORGANIC views (video_daily `views`
    includes paid; organic = views − paid_views, as in the grades), plus paid views to day 3 shown separately."""
    p = os.path.join(data_dir, content)
    if not os.path.exists(p):
        return [], None
    c = json.load(open(p, encoding="utf-8"))
    vids = {k: dict(v, id=k) for k, v in c["videos"].items() if start <= v["published"] <= end}
    daily, paid = defaultdict(dict), defaultdict(dict)
    dp = os.path.join(data_dir, "content", "video_daily.csv")
    if os.path.exists(dp):
        for r in csv.DictReader(open(dp, encoding="utf-8-sig")):
            if r["video_id"] in vids:
                pv = float(r.get("paid_views") or 0)
                daily[r["video_id"]][r["date"]] = float(r["views"] or 0) - pv
                paid[r["video_id"]][r["date"]] = pv
    through = max((d for v in daily.values() for d in v), default=None)
    for k, v in vids.items():
        pub = date.fromisoformat(v["published"])
        dd = daily.get(k, {})
        last_day = (date.fromisoformat(through) - pub).days if through else -1
        cum = lambda n, src=dd: sum(src.get((pub + timedelta(days=i)).isoformat(), 0) for i in range(n + 1))
        v["d1"] = cum(1) if last_day >= 1 else None
        v["d3"] = cum(min(3, last_day)) if last_day >= 0 else None
        v["d3_age"] = min(3, last_day)
        v["to_date"] = sum(dd.values()) if dd else None
        v["paid"] = cum(min(3, last_day), paid.get(k, {})) if last_day >= 0 else 0
        g = v.get("grade") or {}
        v["score"] = g.get("score")
        v["letter"] = g.get("letter")
        v["vals"] = g.get("values") or {}
    return list(vids.values()), through


def tiktok_posts(data_dir, account, start, end):
    files = sorted(glob.glob(os.path.join(data_dir, "tiktok", "daily", "*.csv")))
    if not files:
        return None
    posts = [{"platform": "TikTok", "id": r["video_id"], "url": r["url"].split("?")[0], "date": r["created"],
              "text": "", "views": int(float(r["views"] or 0)),
              "eng": sum(int(float(r[k] or 0)) for k in ("likes", "comments", "shares"))}
             for r in csv.DictReader(open(files[-1], encoding="utf-8-sig")) if start <= r["created"] <= end]
    top = sorted(posts, key=lambda p: -p["views"])[:3]
    try:                                           # captions for the cards
        sys.path.insert(0, MASTER)
        from tiktok_auth import video_stats
        st = video_stats(account, [p["id"] for p in top])
        for p in top:
            p["text"] = (st.get(p["id"]) or {}).get("title") or ""
    except Exception as e:
        print(f"  ⚠ TikTok titles: {str(e)[:80]}")
    return posts


def instagram_posts(env, handle, start, end):
    sync = _sync()
    tok = sync.load_token({"env": env})
    if not tok:
        return None
    ig = sync.IG(tok)
    me = ig.get("me", fields="user_id,username")
    if handle not in me["username"].lower():
        raise LookupError(f"token is for @{me['username']}")
    posts, after = [], None
    while True:
        page = ig.get(f"{me['user_id']}/media", fields="id,permalink,timestamp,caption,like_count,comments_count",
                      limit=50, **({"after": after} if after else {}))
        data = page.get("data", [])
        for m in data:
            d = m["timestamp"][:10]
            if start <= d <= end:
                posts.append({"platform": "Instagram", "url": m.get("permalink", ""), "date": d,
                              "text": (m.get("caption") or "").strip(), "views": ig.post_views(m["id"]) or 0,
                              "eng": (m.get("like_count") or 0) + (m.get("comments_count") or 0)})
        after = page.get("paging", {}).get("cursors", {}).get("after")
        if any(m["timestamp"][:10] < start for m in data) or not page.get("paging", {}).get("next"):
            break
    return posts


def audio_rows(week, key):
    if not os.path.exists(AUDIO_CSV):
        return None
    for r in csv.DictReader(open(AUDIO_CSV, encoding="utf-8-sig")):
        if r.get("week") == week and r.get("show") == key and (r.get("title") or "").strip():
            return r
    return None


def manual_posts(week, key):
    """Posts entered by hand (master/weekly_social.csv) for accounts the APIs can't read yet."""
    if not os.path.exists(SOCIAL_CSV):
        return []
    return [{"platform": r["platform"], "url": r["url"], "date": r["date"], "text": r.get("text") or "",
             "views": float(r["views"] or 0), "eng": float(r.get("engagements") or 0), "manual": True,
             "note": (r.get("note") or "").strip()}
            for r in csv.DictReader(open(SOCIAL_CSV, encoding="utf-8-sig"))
            if r.get("week") == week and r.get("show") == key and r.get("url")]


def collect(key, ws):
    s = SHOWS[key]
    start, end = ws.isoformat(), (ws + timedelta(days=6)).isoformat()
    vids, through = youtube_uploads(s["data"], start, end, s.get("content", "content.json"))
    posts, notes = [], []
    if s["tiktok"]:
        tt = tiktok_posts(s["data"], s["tiktok"], start, end)
        if tt is not None:
            posts += tt
    try:
        ig = instagram_posts(s["ig"], s["handle"], start, end)
        if ig is None:
            notes.append("Instagram not connected")
        else:
            posts += ig
    except Exception as e:
        notes.append(f"Instagram skipped: {str(e)[:50]}")
    hand = manual_posts(start, key)
    if hand:
        posts += hand
        got = {p["platform"].lower() for p in hand}
        notes = [n for n in notes if n.split()[0].lower() not in got] + [f'{" / ".join(sorted({p["platform"] for p in hand}))} entered by hand']
        notes += [p["note"] for p in hand if p["note"]]
    return {"key": key, "show": s, "start": start, "end": end, "vids": vids, "through": through,
            "posts": sorted(posts, key=lambda p: -p["views"]), "notes": notes, "audio": audio_rows(start, key)}


def ranked(vids, fmt, by):
    vs = [v for v in vids if v["format"] == fmt]
    if by == "views":
        return sorted(vs, key=lambda v: -(v["d3"] or 0))
    return sorted(vs, key=lambda v: (v["score"] is None, -(v["score"] or 0), -(v["d3"] or 0)))


# ── Page ─────────────────────────────────────────────────────────────────────
def _n(v):
    return "—" if v is None else f"{v:,.0f}"


def _k(v):
    if v is None:
        return "—"
    return f"{v / 1e6:.2f}M" if v >= 1e6 else f"{v / 1e3:.1f}K" if v >= 1e4 else f"{v:,.0f}"


def _p(v):
    return "—" if v is None else f"{v * 100:.1f}%"


def _dur(s):
    s = int(s or 0)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _md(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.strftime('%b').upper()} {d.day:02d}"


def _esc(t, n=None):
    t = " ".join((t or "").split())
    if n and len(t) > n:
        t = t[:n - 1].rstrip() + "…"
    return html.escape(t)


def video_card(v, by):
    x = v["vals"]
    if by == "views":
        head = f'<span class="big">{_n(v["d3"])} VIEWS</span><span class="tag">day {v["d3_age"]}{" · organic" if v.get("paid") else ""}</span>'
    else:
        head = (f'<span class="big">GRADE {v["letter"]}</span><span class="tag">{v["score"] * 100:.0f} / 100</span>'
                if v["score"] is not None else '<span class="big">NOT GRADED</span>')
    if v["d3_age"] == 3:
        views = f'Day 1 <b>{_k(v["d1"])}</b> · Day 3 <b>{_k(v["d3"])}</b>'
    elif v["d3_age"] == 2:
        views = f'Day 1 <b>{_k(v["d1"])}</b> · Day 2* <b>{_k(v["d3"])}</b>'
    else:
        views = f'Day {max(v["d3_age"], 0)}* <b>{_k(v["d3"])}</b>'
    views += f' · To date <b>{_k(v["to_date"])}</b>'
    if v.get("paid"):
        views += f'<br><span class="paid">+ {_k(v["paid"])} paid (ads) by day {v["d3_age"]}, not counted</span>'
    if v["format"] == "short":
        q = f'Engaged <b>{_p(x.get("ctr"))}</b> · Viewed <b>{_p(x.get("retention"))}</b> · Avg <b>{_dur(x.get("avd"))}</b>'
    else:
        q = (f'CTR <b>{_p(x.get("ctr"))}</b> · Viewed <b>{_p(x.get("retention"))}</b> · Avg <b>{_dur(x.get("avd"))}</b>'
             + (f' · 0:30 <b>{x["r30"] * 100:.0f}%</b>' if x.get("r30") is not None else ""))
    grade = (f' · Grade <b>{v["letter"]}</b>' if by == "views" and v["letter"] else "")
    return f'''
    <a class="cc" href="https://youtu.be/{v["id"]}">
      <div class="thumb" style="background-image:url('https://i.ytimg.com/vi/{v["id"]}/hqdefault.jpg')"></div>
      <div class="body">
        <div class="rank">{head}</div>
        <div class="meta">{_md(v["published"])} · {_dur(v["duration_sec"])}{grade}</div>
        <div class="title">{_esc(v["title"], 95)}</div>
        <div class="stats">{views}<br>{q}</div>
      </div>
    </a>'''


def social_card(p):
    rate = f' · {p["eng"] / p["views"] * 100:.1f}% eng.' if p["views"] else ""
    return f'''
    <a class="sc" href="{html.escape(p["url"])}">
      <div class="rank"><span class="big">{f'{p["views"] / 1e6:.1f}M' if p.get("manual") and p["views"] >= 1e6 else _n(p["views"])} VIEWS</span></div>
      <div class="plat">{p["platform"].upper()} <span>· {_md(p["date"])}{" · from Insights" if p.get("manual") else ""}</span></div>
      <div class="ctext">{_esc(p["text"], 170) or "(no caption)"}</div>
      {f'<div class="stats">{_n(p["eng"])} engagements{rate}</div>' if p["eng"] or not p.get("manual") else ""}
    </a>'''


def block(title, inner, sub="", note=""):
    return (f'<div class="blk"><div class="sec-h">★ {title}</div><div class="sec-s">{sub or "&nbsp;"}</div>{inner}'
            + (f'<div class="note">{note}</div>' if note else "") + '</div>')


def page(d, by):
    s = d["show"]
    cols = ""
    for f, label, noun in FORMATS:
        vs = ranked(d["vids"], f, by)
        inner = video_card(vs[0], by) if vs else f'<div class="empty">No {noun}s published this week.</div>'
        paid, org = sum(v.get("paid") or 0 for v in vs), sum(v["d3"] or 0 for v in vs)
        mix = f" · {paid / (paid + org) * 100:.0f}% of day-3 views paid" if paid else ""
        cols += block(label, inner, f"{noun[0].upper() + noun[1:]} · {len(vs)} published this week{mix}")
    plats = " / ".join(sorted({p["platform"] for p in d["posts"]}))
    notes = "; ".join(d["notes"])
    social = block("Top social post",
                   social_card(d["posts"][0]) if d["posts"] else
                   f'<div class="empty">No social data for this show yet{" — " + notes if notes else ""}.</div>',
                   f'{plats} · {len(d["posts"])} posts · by views' if d["posts"] else "", notes if d["posts"] else "")
    a = d["audio"]
    src = s.get("audio", "Megaphone")
    if a:
        cur, prev = float(a.get("downloads") or 0), float(a.get("prev_downloads") or 0)
        chg = f' <span class="{"up" if cur >= prev else "down"}">{(cur / prev - 1) * 100:+.0f}% vs last week\'s top</span>' if prev else ""
        def tot(label, k, ck=None):
            v = a.get(k)
            if not v:
                return ""
            c = a.get(ck) if ck else None
            cs = f' <span class="{"up" if float(c) >= 0 else "down"}">{float(c):+.1f}%</span>' if c not in (None, "") else ""
            return f'{label} <b>{_n(float(v))}</b>{cs}'
        week_tot = "<br>".join(x for x in (tot("Downloads", "total_downloads", "downloads_chg"),
                                          tot("Spotify streams", "streams", "streams_chg"),
                                          tot("Listening hrs", "hours", "hours_chg")) if x)
        audio = (f'<div class="audio"><div><div class="rank"><span class="big">{_n(cur)} DOWNLOADS</span>{chg}</div>'
                 f'<div class="title">{_esc(a["title"])}</div>'
                 + (f'<div class="prev">Last week\'s top · <b>{_n(prev)}</b> · {_esc(a.get("prev_title"), 90)}</div>' if prev else "")
                 + (f'<div class="stats" style="margin-top:6px"><b>Show week</b> (vs prior week)<br>{week_tot}</div>' if week_tot else "")
                 + '</div></div>')
    else:
        audio = f'<div class="empty">Added by hand from {src} (master/weekly_audio.csv).</div>'
    secs = (f'<div class="row3">{cols}</div>'
            f'<div class="row2">{social}{block("Top audio episode", audio, src + " · vs last week" + chr(39) + "s top")}</div>')
    rank_lbl = "Ranked by Day-3 Views" if by == "views" else "Ranked by Content Grade"
    return f'''
  <section class="page" style="--accent:{s["accent"]}">
    <div class="hdr"><div><div class="show">{html.escape(s["name"]).upper()}</div>
      <h1>Top Content — {_md(d["start"])} – {_md(d["end"])}</h1></div><div class="by">{rank_lbl}</div></div>
    <div class="sub">Best-performing content published {_md(d["start"])} – {_md(d["end"])} · click any title to view</div>
    {secs}
    <div class="foot">Day 1 = upload day + next day · Day 3 = upload day + 3 days (YouTube reports by calendar day) · * day 3 not in yet:
      last day available · YouTube data through {_md(d["through"]) if d["through"] else "—"} · Grades compare each upload with the
      show's own uploads of the same format at the same age · Rain Delay Media · Internal · Generated {date.today().strftime("%B %-d, %Y") if os.name != "nt" else date.today().strftime("%B %#d, %Y")}</div>
  </section>'''


CSS = """
  :root { --ink:#111418; --mut:#7A808A; --line:#E3E5E8; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:Inter,sans-serif; color:var(--ink); background:#fff; }
  .page { width:8.5in; height:11in; overflow:hidden; padding:.3in .5in .15in; page-break-after:always; }
  .hdr { display:flex; justify-content:space-between; align-items:flex-end; }
  .show { font:700 10px Inter; letter-spacing:.22em; color:var(--accent); }
  h1 { font:800 27px Inter; letter-spacing:-.01em; text-transform:uppercase; margin:2px 0 0; }
  .by { font:600 11px Inter; color:var(--mut); padding-bottom:6px; }
  .sub { font:500 9.5px Inter; letter-spacing:.16em; color:var(--mut); text-transform:uppercase; margin:4px 0 9px; }
  .row3 { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; margin:8px 0 22px; }
  .row2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
  .blk { display:flex; flex-direction:column; min-width:0; }
  .blk > .sc, .blk > .audio, .blk > .empty { flex:1; }
  .note { font:400 8px Inter; color:var(--mut); margin-top:5px; }
  .sec-h { font:700 10.5px Inter; letter-spacing:.16em; color:var(--accent); text-transform:uppercase; margin-bottom:6px;
           display:flex; justify-content:space-between; }
  .sec-s { font:500 8.5px Inter; letter-spacing:.06em; color:var(--mut); margin:-3px 0 7px; }
  .grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
  a { color:inherit; text-decoration:none; }
  .cc { display:block; }
  .thumb { aspect-ratio:16/9; border-radius:8px; background:#1b1b1b center/cover no-repeat; width:100%; }
  .body { padding-top:7px; }
  .rank { font:800 22px 'Barlow Condensed',Inter; display:flex; align-items:baseline; gap:7px; flex-wrap:wrap; }
  .big { color:var(--accent); }
  .paid { color:#94A3B8; }
  .tag { font:600 9px Inter; color:var(--mut); }
  .meta { font:500 8.5px Inter; letter-spacing:.08em; color:var(--mut); text-transform:uppercase; margin:1px 0 2px; }
  .title { font:600 11.5px/1.3 Inter; }
  .stats { font:400 9px/1.6 Inter; color:#4A505A; margin-top:5px; }
  .stats b { color:var(--ink); font-weight:600; }
  .sc { display:block; border:1px solid var(--line); border-left:3px solid var(--accent); border-radius:10px; padding:12px 14px; }
  .plat { font:600 8.5px Inter; letter-spacing:.12em; color:var(--mut); margin:1px 0 3px; }
  .ctext { font:400 10.5px/1.4 Inter; margin:5px 0; }
  .empty { font:400 10px Inter; color:var(--mut); border:1px dashed var(--line); border-radius:10px; padding:10px 12px; }
  .audio { border:1px solid var(--line); border-left:3px solid var(--accent); border-radius:10px; padding:12px 14px; }
  .prev { font:400 9px/1.45 Inter; color:var(--mut); margin-top:6px; padding-top:6px; border-top:1px solid var(--line); }
  .up { color:#15803D; font:600 10px Inter; } .down { color:#B91C1C; font:600 10px Inter; }
  .foot { border-top:1px solid var(--line); margin-top:24px; padding-top:6px; font:400 7.6px/1.5 Inter; color:var(--mut); text-align:center; }
  @page { size:letter; margin:0; }
"""


def render(data, by):
    pages = "".join(page(d, by) for d in data)
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Top Content · {data[0]["start"]}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Barlow+Condensed:wght@700;800&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>{pages}</body></html>'''


def to_pdf(html_path, pdf_path):
    edge = next((e for e in EDGE if os.path.exists(e)), None)
    if not edge:
        return False
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=15000",
                    f"--user-data-dir={os.path.join(os.environ.get('TEMP', '.'), 'rdm_weekly_edge')}",
                    f"--print-to-pdf={pdf_path}", "file:///" + html_path.replace(os.sep, "/")],
                   capture_output=True, timeout=120)
    import time
    for _ in range(60):                            # Edge returns before the file is written
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            time.sleep(1)
            return True
        time.sleep(1)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", help="Monday of the week (YYYY-MM-DD); default = last full week")
    ap.add_argument("--show", choices=list(SHOWS), nargs="*")
    a = ap.parse_args()
    if a.week:
        ws = datetime.strptime(a.week, "%Y-%m-%d").date()
        ws -= timedelta(days=ws.weekday())
    else:
        t = date.today()
        ws = t - timedelta(days=t.weekday() + 7)
    data = []
    for k in a.show or list(SHOWS):
        print(f"• {SHOWS[k]['name']}")
        data.append(collect(k, ws))
    folder = os.path.join(OUT, ws.isoformat())
    os.makedirs(folder, exist_ok=True)
    for by in ("views", "grades"):
        hp = os.path.join(folder, f"Top_Content_{ws.isoformat()}_{by}.html")
        open(hp, "w", encoding="utf-8").write(render(data, by))
        pp = hp[:-5] + ".pdf"
        if os.path.exists(pp):
            os.remove(pp)
        print(f"✓ {os.path.relpath(pp if to_pdf(hp, pp) else hp)}")


if __name__ == "__main__":
    main()
