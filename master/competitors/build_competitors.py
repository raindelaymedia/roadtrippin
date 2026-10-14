"""
RDM — Competitive Landscape page (internal)
===========================================
Builds master/competitors/competitors.html from the daily snapshots that
collect_competitors.py writes. Linked from the RDM landing page only.

What it shows, per group (Basketball / Football / Women's), our shows highlighted:
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
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "competitors.html")
WINDOW = 28
INACTIVE_DAYS = 30
EPISODE_MIN_SEC = 20 * 60
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


def summarize(shows, daily, videos, vdaily):
    dates = sorted(daily)
    d1 = dates[-1]
    today = datetime.strptime(d1, "%Y-%m-%d").date()
    since = (today - timedelta(days=WINDOW - 1)).isoformat()
    week = (today - timedelta(days=6)).isoformat()
    views_now = vdaily.get(d1, {})
    by_channel = defaultdict(list)
    for vid, v in videos.items():
        if v["published"] >= since and vid in views_now:
            by_channel[v["channel_id"]].append({**v, "views": views_now[vid] or 0,
                                                "format": video_format(num(v["duration_sec"]) or 0)})
    rows = []
    for s in shows:
        cid = s["channel_id"]
        c = daily[d1].get(cid, {})
        vs = by_channel.get(cid, [])
        eps = [v["views"] for v in vs if v["format"] == "episode"]
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
    key = (lambda r: r["gain28"] or 0) if have28 else (lambda r: r["upload_views_total"])
    g.sort(key=lambda r: (-key(r), r["show"]))
    ours = [r for r in g if r["ours"]]

    # Headline tiles for our show(s) in this group
    tiles = ""
    for r in ours:
        rank = g.index(r) + 1
        lead = g[0] if g[0] is not r else (g[1] if len(g) > 1 else None)
        tiles += f"""
      <div class="tile ours-tile">
        <div class="t-l">★ {r['show']}</div>
        <div class="t-v">#{rank} <small>of {len(g)}</small></div>
        <div class="t-s">{'28-day views gained' if have28 else 'views on last-28-day uploads'} · {fmt(key(r))}
          {f"<br>Leader: {lead['show']} · {fmt(key(lead))}" if lead else ''}</div>
      </div>"""

    # Leaderboard
    def cell(v, cls=""):
        return f'<td class="n {cls}">{fmt(v)}</td>'
    body = ""
    for i, r in enumerate(g, 1):
        up = r["uploads"]
        status = (f'<span class="badge">inactive · last {md(r["last_upload"])}</span>' if r["inactive"]
                  else f'<span class="sub">last upload {md(r["last_upload"])}</span>' if r["last_upload"] else "")
        body += (f'<tr class="{"ours" if r["ours"] else ""}"><td class="rk">{i}</td>'
                 f'<td class="sh"><a href="https://www.youtube.com/channel/{r["channel_id"]}" target="_blank" rel="noopener">'
                 f'{"★ " if r["ours"] else ""}{r["show"]}</a><div class="sub">{r["subgroup"]} · {status}</div></td>'
                 + cell(r["subs"]) + cell(r["gain7"], "" if have7 else "pending")
                 + cell(r["gain28"], "" if have28 else "pending")
                 + f'<td class="n">{up["episode"]} · {up["clip"]} · {up["short"]}</td>'
                 + cell(r["upload_views_total"]) + cell(r["median_ep"])
                 + f'<td class="n">{r["eps_week"] if up["episode"] else "—"}</td></tr>')

    # Charts data
    chart_rows = [r for r in g if r["upload_views_total"] or not r["inactive"]]   # inactive shows: table only
    labels = [("★ " if r["ours"] else "") + r["show"] for r in chart_rows]
    bars = {f: [r["upload_views"][f] for r in chart_rows] for f, *_ in FORMATS}
    trend_rows = [r for r in g if any(v is not None for v in trend[r["channel_id"]])]
    trend_sets = [{"label": ("★ " if r["ours"] else "") + r["show"], "data": trend[r["channel_id"]],
                   "ours": r["ours"]} for r in sorted(trend_rows, key=lambda r: -(r["gain7"] or r["gain1"] or 0))[:6]]
    top = sorted((dict(v, show=r["show"], ours=r["ours"]) for r in g for v in r["top"]), key=lambda v: -v["views"])[:10]
    top_html = "".join(
        f'<tr class="{"ours" if v["ours"] else ""}"><td class="n">{fmt(v["views"])}</td>'
        f'<td><a href="https://youtu.be/{v["video_id"]}" target="_blank" rel="noopener">{v["title"]}</a>'
        f'<div class="sub">{v["show"]} · {md(v["published"])} · {dict((f, l) for f, l, _ in FORMATS)[v["format"]][:-1]}</div></td></tr>'
        for v in top) or '<tr><td colspan="2" class="sub">No uploads in the last 7 days.</td></tr>'

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
      <div class="card-h"><h3>Leaderboard</h3><span class="r">sorted by {'28-day views gained' if have28 else 'views on last-28-day uploads (views gained ranks from ' + md((datetime.strptime(dates[0], '%Y-%m-%d') + timedelta(days=28)).strftime('%Y-%m-%d')) + ')'}</span></div>
      <div class="scroll"><table class="lb">
        <thead><tr><th>#</th><th>Show</th><th class="n">Subscribers</th><th class="n">Views gained · 7d</th><th class="n">Views gained · 28d</th>
          <th class="n">Uploads 28d<br><span class="sub">ep · clip · short</span></th><th class="n">Views on 28d uploads</th>
          <th class="n">Median views / episode</th><th class="n">Episodes / week</th></tr></thead>
        <tbody>{body}</tbody></table></div>
    </div>
    <div class="grid2">
      <div class="card">
        <div class="card-h"><h3>Views gained per day</h3><span class="r">top 6 by last-7-day gains</span></div>
        <div style="position:relative;height:260px">{trend_block}</div>
      </div>
      <div class="card">
        <div class="card-h"><h3>Top uploads · last 7 days</h3><span class="r">current views</span></div>
        <table class="top">{top_html}</table>
      </div>
    </div>
    <script type="application/json" id="data{gi}">{chart_data}</script>
  </section>"""


def build():
    shows, daily, videos, vdaily = load()
    if not daily:
        raise SystemExit("No snapshots yet — run collect_competitors.py first.")
    rows, dates, trend = summarize(shows, daily, videos, vdaily)
    groups = list(dict.fromkeys(s["group"] for s in shows))
    tabs = "".join(f'<button class="tab{" on" if i == 0 else ""}" data-g="{i}">{g}</button>' for i, g in enumerate(groups))
    sections = "".join(group_html(g, rows, dates, trend, i) for i, g in enumerate(groups))
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
  .foot {{ margin-top:22px; font-size:11px; color:var(--mut); line-height:1.6; }}
  @media (max-width:560px) {{ .wrap {{ padding:18px 16px 40px; }} h1 {{ font-size:21px; }} }}
</style></head><body><div class="wrap">
  <a class="back" href="../../index.html">← RDM Network</a>
  <h1>Competitive Landscape</h1>
  <div class="lead">Public YouTube stats for {len(shows)} shows · our shows marked ★ · snapshot {md(dates[-1])} · tracking since {md(dates[0])} ({days} day{'s' if days != 1 else ''})</div>
  {'' if days > 28 else f'<div class="note"><b>History is building.</b> "Views gained" needs earlier snapshots: 7-day figures fill in from {md((datetime.strptime(dates[0], "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d"))}, 28-day from {md((datetime.strptime(dates[0], "%Y-%m-%d") + timedelta(days=28)).strftime("%Y-%m-%d"))}. Until then, shows rank by the views their last-28-day uploads have now.</div>'}
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
