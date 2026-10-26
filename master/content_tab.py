"""
RDM — Content tab for the show dashboards (RT, GT, FR, SR internal).
content_page(path, fmt, show) → HTML: last week's graded YouTube uploads, this week so far, and a plain-English
"How the grades work". Reads the content.json that master/content_grades.py writes (or SR's content_sr.json).
Uses the dashboards' shared classes (card, card-title, data-table, table-scroll, metric-delta).
"""

import json
import os
from datetime import date, datetime, timedelta

FORMAT = {"episode": "Episode", "clip": "Clip", "short": "Short"}
COLOR = {"A": "#3BB273", "B": "#8BC34A", "C": "#E8C840", "D": "#E08C2A", "F": "#E05252"}
NAMES = {"retention": "% viewed", "ctr": "CTR", "views": "views", "engagement": "engagement", "subs": "subs"}


def _md(iso):
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{d.strftime('%b')} {d.day}"


def _pct(v, d=1):
    return "—" if v is None else f"{v * 100:.{d}f}%"


def _why(gr, fmt_):
    r = {k: x for k, x in (gr.get("ranks") or {}).items() if x is not None}
    if not r:
        return ""
    nm = lambda k: "engaged %" if (k == "ctr" and fmt_ == "short") else NAMES[k]
    best, worst = max(r, key=r.get), min(r, key=r.get)
    return (f'{nm(best)} top {max(1, 100 - round(r[best] * 100))}%'
            + (f' · {nm(worst)} bottom {max(1, round(r[worst] * 100))}%' if r[worst] < .4 else ""))


def _table(items, fmt):
    rows = ""
    for f in ("episode", "clip", "short"):
        its = sorted((v for v in items if v["format"] == f), key=lambda v: -((v["grade"] or {}).get("score") or -1))
        if not its:
            continue
        rows += f'<tr><td colspan="8" style="text-align:left;font-weight:700;opacity:.85">{FORMAT[f]}s · {len(its)}</td></tr>'
        for v in its:
            gr = v.get("grade") or {}
            vals = gr.get("values") or {}
            paid = v.get("paid_views") or ((v.get("by_age") or [{}])[-1].get("paid_views") if v.get("by_age") else 0) or 0
            letter = gr.get("letter")
            badge = (f'<span style="display:inline-block;min-width:22px;text-align:center;border-radius:4px;font-weight:700;'
                     f'color:#111;background:{COLOR[letter]}">{letter}</span>' if letter
                     else '<span title="Not enough comparable uploads yet" style="opacity:.6">—</span>')
            rows += (f'<tr><td style="width:44px">{badge}</td>'
                     f'<td style="text-align:left;white-space:normal;min-width:280px;max-width:440px">'
                     f'<a href="https://www.youtube.com/watch?v={v["id"]}" target="_blank" style="color:var(--brand)">{v["title"][:90]}</a></td>'
                     f'<td>{_md(v["published"])} · day {gr.get("age_days", "—")}</td><td>{fmt(vals.get("views"))}</td>'
                     f'<td style="opacity:.7">{fmt(paid) if paid else "—"}</td><td>{_pct(vals.get("retention"))}</td>'
                     f'<td>{_pct(vals.get("ctr"))}</td>'
                     f'<td style="text-align:left;opacity:.75">{_why(gr, f) if letter else "not enough comparable uploads yet"}</td></tr>')
    return (f'<div class="table-scroll"><table class="data-table"><thead><tr><th>Grade</th><th style="text-align:left">Upload</th>'
            f'<th>Published · age</th><th>Organic views</th><th>Paid views</th><th>% viewed</th><th>CTR / engaged %</th>'
            f'<th style="text-align:left">Why</th></tr></thead><tbody>{rows}</tbody></table></div>')


def _methodology(content, show):
    w = content.get("weights") or {"retention": .35, "ctr": .35, "views": .15, "engagement": .10, "subs": .05}
    p = lambda x: f"{x * 100:.0f}%"
    return f"""
  <div class="card" style="border-left:3px solid var(--brand)">
    <div class="card-title">How the grades work</div>
    <div style="font-size:13px;line-height:1.6">
      <p style="margin:0 0 10px"><b>The short version:</b> every YouTube upload is compared with {show}'s own recent uploads of the
        same kind, at the same age. <b>A</b> = doing better than about 80% of them, <b>C</b> = about average, <b>F</b> = behind about
        80% of them. It's a comparison with ourselves, not with other channels.</p>
      <p style="margin:0 0 6px"><b>Like for like.</b> Episodes vs episodes, clips vs clips, Shorts vs Shorts. A 3-day-old clip is
        compared with how other clips were doing on <i>their</i> day 3, so new uploads aren't punished for being new. The comparison
        group is the same kind of upload from the {content.get("peer_days", 90)} days before (at least 5 needed — until then the grade
        shows "—").</p>
      <p style="margin:0 0 6px"><b>Five measures</b>, each ranked within that group and combined: % viewed {p(w['retention'])} (how much
        people watch) · click-through rate {p(w['ctr'])} (how often a thumbnail gets clicked; for Shorts, the share of views where people
        kept watching instead of swiping) · views {p(w['views'])} · engagement {p(w['engagement'])} (likes, comments, shares per view) ·
        subscribers per 1,000 views {p(w['subs'])}.</p>
      <p style="margin:0 0 6px"><b>Grade bands:</b> A 80+ · B 60–80 · C 40–60 · D 20–40 · F under 20 (combined score out of 100).
        A measure with no data yet (e.g. too few impressions for CTR) is left out and the rest re-weighted.</p>
      <p style="margin:0"><b>Organic only:</b> views from YouTube ads are left out of every measure (shown in the table for reference).
        Grades move during the week as uploads age and YouTube's data settles (about two days behind).</p>
    </div>
  </div>"""


def content_page(path, fmt, show):
    if not os.path.exists(path):
        return ('<div class="card"><div class="metric-delta" style="color:var(--text2)">Content grades appear after the next '
                'daily run.</div></div>')
    content = json.load(open(path, encoding="utf-8"))
    vids = [dict(v, id=k) for k, v in (content.get("videos") or {}).items()]
    today = date.today()
    this_w = (today - timedelta(days=today.weekday())).isoformat()
    last_w = (today - timedelta(days=today.weekday() + 7)).isoformat()
    lbl = lambda s: f"{_md(s)}–{_md((date.fromisoformat(s) + timedelta(days=6)).isoformat())}"
    last = [v for v in vids if v.get("week") == last_w]
    cur = [v for v in vids if v.get("week") == this_w]
    sec = lambda title, items: (f'<div class="card"><div class="card-title">{title}</div>'
                                + (_table(items, fmt) if items else '<div class="metric-delta" style="color:var(--text2)">No uploads.</div>')
                                + '</div>')
    return (sec(f"Last week · {lbl(last_w)} · {len(last)} uploads", last)
            + (sec(f"This week so far · since {_md(this_w)}", cur) if cur else "")
            + f'<div class="metric-delta" style="color:var(--text2);margin:-4px 0 14px">Data through {content.get("through", "")}. '
              'See <b>How the grades work</b> below.</div>'
            + _methodology(content, show))
