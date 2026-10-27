"""
RDM — Content tab for the show dashboards (RT, GT, FR, SR internal; the shared SR dashboard uses a copy in common/).
content_page(path, fmt, show) → HTML: every graded YouTube upload from the last ~5 months in one table you can
filter by any date range (presets or custom), format and grade status, sorted by any column, plus a plain-English
"How the grades work". Reads content.json from master/content_grades.py (or SR's content_sr.json).

Grade status by age: Provisional (< 7 days) · Working (7–28 days) · Final (28+ days, locked at its day-28 reading).
"""

import json
import os
from datetime import datetime

NAMES = {"retention": "% viewed", "ctr": "CTR", "views": "views", "engagement": "engagement", "subs": "subs"}


def _why(gr, fmt_):
    r = {k: x for k, x in (gr.get("ranks") or {}).items() if x is not None}
    if not r:
        return ""
    nm = lambda k: "engaged %" if (k == "ctr" and fmt_ == "short") else NAMES[k]
    best, worst = max(r, key=r.get), min(r, key=r.get)
    return (f'{nm(best)} top {max(1, 100 - round(r[best] * 100))}%'
            + (f' · {nm(worst)} bottom {max(1, round(r[worst] * 100))}%' if r[worst] < .4 else ""))


def status(age, final_age=28):
    return "final" if age >= final_age else "working" if age >= 7 else "provisional"


def rows_for(content):
    """Compact rows for the page script."""
    final_age = content.get("final_age", 28)
    out = []
    for vid, v in (content.get("videos") or {}).items():
        gr = v.get("grade") or {}
        vals = gr.get("values") or {}
        paid = v.get("paid_views")
        if paid is None and v.get("by_age"):
            paid = v["by_age"][-1].get("paid_views")
        age = gr.get("age_days") or 0
        out.append({"id": vid, "t": v.get("title", ""), "p": v.get("published", ""), "f": v.get("format", ""),
                    "a": age, "s": status(age, final_age), "g": gr.get("letter"), "sc": gr.get("score"),
                    "v": vals.get("views"), "pd": paid or 0, "r": vals.get("retention"), "c": vals.get("ctr"),
                    "w": _why(gr, v.get("format")) if gr.get("letter") else "not enough comparable uploads yet"})
    out.sort(key=lambda x: x["p"], reverse=True)
    return out


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
      <p style="margin:0 0 6px"><b>Grade status.</b> <b>Provisional</b> (under 7 days old) — an early read, likely to move.
        <b>Working</b> (7–28 days) — mostly settled. <b>Final</b> (28+ days) — locked at its day-28 reading, so uploads from any
        period compare on the same yardstick.</p>
      <p style="margin:0 0 6px"><b>Five measures</b>, each ranked within the comparison group and combined: % viewed {p(w['retention'])}
        (how much people watch) · click-through rate {p(w['ctr'])} (how often a thumbnail gets clicked; for Shorts, the share of views
        where people kept watching instead of swiping) · views {p(w['views'])} · engagement {p(w['engagement'])} (likes, comments,
        shares per view) · subscribers per 1,000 views {p(w['subs'])}.</p>
      <p style="margin:0 0 6px"><b>Grade bands:</b> A 80+ · B 60–80 · C 40–60 · D 20–40 · F under 20 (combined score out of 100).
        A measure with no data yet (e.g. too few impressions for CTR) is left out and the rest re-weighted.</p>
      <p style="margin:0"><b>Organic only:</b> views from YouTube ads are left out of every measure (shown in the table for reference).
        YouTube's data runs about two days behind.</p>
    </div>
  </div>"""


_UI = r"""
<style>
  .ct-bar{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin-bottom:12px;font-size:12px}
  .ct-bar select,.ct-bar input[type=date]{font:inherit;padding:5px 8px;border-radius:6px;border:1px solid rgba(127,127,127,.35);
    background:transparent;color:inherit}
  .ct-bar select option{color:#111}
  .ct-bar label{display:inline-flex;gap:5px;align-items:center;cursor:pointer}
  .ct-sum{font-size:12.5px;margin:0 0 10px;opacity:.9}
  .ct-g{display:inline-block;min-width:22px;text-align:center;border-radius:4px;font-weight:700;color:#111}
  .ct-st{display:inline-block;font-size:10px;padding:1px 6px;border-radius:999px;margin-left:6px;vertical-align:1px;
    border:1px solid currentColor;opacity:.8}
  .ct-tbl th{cursor:pointer;user-select:none} .ct-tbl th.on::after{content:' ▾'} .ct-tbl th.on.asc::after{content:' ▴'}
  .ct-tbl td.t{text-align:left;white-space:normal;min-width:260px;max-width:440px}
</style>
<div class="card">
  <div class="ct-bar">
    <b>Uploads published</b>
    <select id="ct-preset">
      <option value="lw">Last week</option><option value="tw">This week</option><option value="l4">Last 4 weeks</option>
      <option value="tm">This month</option><option value="lm">Last month</option><option value="l90">Last 90 days</option>
      <option value="all">Everything (~5 months)</option><option value="custom">Custom…</option>
    </select>
    <span id="ct-custom" hidden><input type="date" id="ct-from"> to <input type="date" id="ct-to"></span>
    <span>· <label><input type="checkbox" class="ct-f" value="episode" checked>Episodes</label>
      <label><input type="checkbox" class="ct-f" value="clip" checked>Clips</label>
      <label><input type="checkbox" class="ct-f" value="short" checked>Shorts</label></span>
    <span>· <label><input type="checkbox" class="ct-s" value="final" checked>Final</label>
      <label><input type="checkbox" class="ct-s" value="working" checked>Working</label>
      <label><input type="checkbox" class="ct-s" value="provisional" checked>Provisional</label></span>
  </div>
  <div class="ct-sum" id="ct-sum"></div>
  <div class="table-scroll"><table class="data-table ct-tbl"><thead><tr>
    <th data-k="sc" class="on">Grade</th><th data-k="t" style="text-align:left">Upload</th><th data-k="f">Format</th>
    <th data-k="p">Published</th><th data-k="a">Age</th><th data-k="v">Organic views</th><th data-k="pd">Paid views</th>
    <th data-k="r">% viewed</th><th data-k="c">CTR / engaged %</th><th data-k="w" style="text-align:left">Why</th>
  </tr></thead><tbody id="ct-body"></tbody></table></div>
  <div class="metric-delta" style="color:var(--text2);margin-top:8px">__NOTE__</div>
</div>
<script>
(function(){
  const R = __ROWS__, TODAY = '__TODAY__';
  const COL = {A:'#3BB273',B:'#8BC34A',C:'#E8C840',D:'#E08C2A',F:'#E05252'};
  const FMT = {episode:'Episode',clip:'Clip',short:'Short'};
  const ST = {final:'Final',working:'Working',provisional:'Provisional'};
  let sortK = 'sc', asc = false;
  const $ = id => document.getElementById(id);
  const iso = d => d.toISOString().slice(0,10);
  const D = s => new Date(s + 'T12:00:00Z');
  const add = (d,n) => { const x = new Date(d); x.setUTCDate(x.getUTCDate()+n); return x; };
  const K = v => v==null ? '—' : v>=1e6 ? (v/1e6).toFixed(1)+'M' : v>=1e4 ? Math.round(v/1e3)+'K' : v>=1e3 ? (v/1e3).toFixed(1)+'K' : Math.round(v).toLocaleString();
  const P = v => v==null ? '—' : (v*100).toFixed(1)+'%';
  function range(){
    const t = D(TODAY), dow = (t.getUTCDay()+6)%7, mon = add(t,-dow), p = $('ct-preset').value;
    if (p==='tw') return [iso(mon), TODAY];
    if (p==='lw') return [iso(add(mon,-7)), iso(add(mon,-1))];
    if (p==='l4') return [iso(add(mon,-28)), iso(add(mon,-1))];
    if (p==='tm') return [TODAY.slice(0,8)+'01', TODAY];
    if (p==='lm') { const f = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth()-1, 1)), l = new Date(Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), 0)); return [iso(f), iso(l)]; }
    if (p==='l90') return [iso(add(t,-90)), TODAY];
    if (p==='all') return ['0000', '9999'];
    return [$('ct-from').value || '0000', $('ct-to').value || '9999'];
  }
  function draw(){
    $('ct-custom').hidden = $('ct-preset').value !== 'custom';
    const [a,b] = range();
    const fs = [...document.querySelectorAll('.ct-f:checked')].map(x=>x.value);
    const ss = [...document.querySelectorAll('.ct-s:checked')].map(x=>x.value);
    const rows = R.filter(r => r.p>=a && r.p<=b && fs.includes(r.f) && ss.includes(r.s));
    rows.sort((x,y) => { let u=x[sortK], v=y[sortK]; if (u==null) return 1; if (v==null) return -1;
      const c = typeof u==='string' ? u.localeCompare(v) : u-v; return asc ? c : -c; });
    const n = {}; rows.forEach(r => { if (r.g) n[r.g]=(n[r.g]||0)+1; });
    const top = rows.filter(r=>r.sc!=null).sort((x,y)=>y.sc-x.sc)[0];
    $('ct-sum').innerHTML = rows.length ? `<b>${rows.length}</b> uploads · ` + ['A','B','C','D','F'].map(g =>
      `<span class="ct-g" style="background:${COL[g]}">${g}</span> ${n[g]||0}`).join(' &nbsp;') +
      (top ? ` &nbsp;· best: <a href="https://www.youtube.com/watch?v=${top.id}" target="_blank" style="color:var(--brand)">${top.t.slice(0,60)}</a> (${top.g})` : '')
      : 'No uploads in this range.';
    $('ct-body').innerHTML = rows.map(r => `<tr>
      <td>${r.g ? `<span class="ct-g" style="background:${COL[r.g]}">${r.g}</span>` : '<span style="opacity:.6">—</span>'}<span class="ct-st">${ST[r.s]}</span></td>
      <td class="t"><a href="https://www.youtube.com/watch?v=${r.id}" target="_blank" style="color:var(--brand)">${r.t.slice(0,90)}</a></td>
      <td>${FMT[r.f]||r.f}</td><td>${r.p}</td><td>day ${r.a}</td><td>${K(r.v)}</td><td style="opacity:.7">${r.pd ? K(r.pd) : '—'}</td>
      <td>${P(r.r)}</td><td>${P(r.c)}</td><td style="text-align:left;opacity:.75">${r.w}</td></tr>`).join('');
  }
  document.querySelectorAll('.ct-tbl th').forEach(th => th.onclick = () => {
    const k = th.dataset.k; asc = (sortK===k) ? !asc : (k==='t'||k==='f'); sortK = k;
    document.querySelectorAll('.ct-tbl th').forEach(x => x.classList.toggle('on', x===th));
    th.classList.toggle('asc', asc); draw(); });
  ['ct-preset','ct-from','ct-to'].forEach(id => $(id).onchange = draw);
  document.querySelectorAll('.ct-f,.ct-s').forEach(x => x.onchange = draw);
  draw();
})();
</script>"""


def content_page(path, fmt, show, methodology=True):
    if not os.path.exists(path):
        return ('<div class="card"><div class="metric-delta" style="color:var(--text2)">Content grades appear after the next '
                'daily run.</div></div>')
    content = json.load(open(path, encoding="utf-8"))
    rows = rows_for(content)
    note = (f"{len(rows)} graded uploads · data through {content.get('through', '')} · organic only (paid views shown, not graded) · "
            "click a column to sort · see How the grades work below")
    ui = (_UI.replace("__ROWS__", json.dumps(rows, separators=(",", ":")).replace("</", "<\\/"))
          .replace("__TODAY__", datetime.now().strftime("%Y-%m-%d")).replace("__NOTE__", note))
    return ui + (_methodology(content, show) if methodology else "")
