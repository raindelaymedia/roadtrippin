"""
Road Trippin' × Fanatics — Season 2 delivery report renderer (renewal Year 1: Oct 16 2026 – Oct 18 2027).
render_html(d) -> print-ready HTML. Same look as the Season 1 report (its CSS is read from
fanatics_report_template.py so the two never drift); what's new for Season 2:
  • 130,000,000-impression annual delivery goal with pace
  • Road Trippin' and Girls Tripp broken out separately
  • Season 2 episode / integration targets and talent weekly minimums with a pace line per talent
"""

import os

GOLD = "#C9A84C"
GREEN = "#2E7D32"
RED = "#C62828"

_S1 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fanatics_report_template.py"), encoding="utf-8").read()
CSS = (_S1[_S1.index("<style>") + 7:_S1.index("</style>")]
       .replace("{{", "{").replace("}}", "}").replace("{GOLD}", GOLD))
CSS += """
  .blk td { padding-top:14px; border-top:2px solid var(--ink); }
  .blk .pl-title { font-size:15px; }
  .blk .pl-sub { font-style:normal; }
  .ok { color:#2E7D32; font-weight:700; }
  .behind { color:#C62828; font-weight:700; }
  .pend { color:var(--mut); font-style:italic; font-weight:500; }
  .split { display:flex; gap:18px; margin-top:6px; font-size:10px; color:#555; }
  .split b { font-family:'Barlow Condensed'; font-size:14px; color:var(--ink); }
"""


def _fmt(n):
    if n is None:
        return '<span class="pend">Pending</span>'
    try:
        return f"{int(round(float(n))):,}"
    except (ValueError, TypeError):
        return str(n)


def _md(dt):
    return f"{dt.strftime('%b')} {dt.day}"


def _mdy(dt):
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def _Mdy(dt):
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def _bar(pct, color=GOLD):
    return (f'<div class="bar"><div class="bar-fill" style="width:{min(max(pct, 0), 100):.1f}%;background:{color}"></div></div>')


def _content_card(item, show_dur=False):
    dur = f'<span class="cc-dur"> · {item["dur"]}</span>' if show_dur and item.get("dur") else ""
    return f'''
    <a class="cc" href="{item.get('url', '#')}">
      <div class="cc-thumb" style="background-image:url('{item.get('thumb', '')}')"></div>
      <div class="cc-body">
        <div class="cc-rank">#{item['rank']}<span class="cc-views">{_fmt(item['views'])} VIEWS</span></div>
        <div class="cc-meta">{item.get('date', '')}{dur}</div>
        <div class="cc-title">{item['title']}</div>
      </div>
    </a>'''


def _social_card(item):
    return f'''
    <div class="sc">
      <div class="cc-rank">#{item['rank']}<span class="cc-views">{_fmt(item['views'])} VIEWS</span></div>
      <div class="sc-plat">{item['platform'].upper()}<span class="sc-date">{item.get('date', '')}</span></div>
      <div class="cc-title">{item['title']}</div>
    </div>'''


def _row(label, sub, metric, tp, cum, indent=False, gold=False):
    style = f' style="color:{GOLD}"' if gold else ""
    return f'''
        <tr class="{'ind' if indent else ''}">
          <td class="pl-name"><div class="pl-title"{style}>{label}</div><div class="pl-sub">{sub}</div></td>
          <td class="pl-metric">{metric}</td>
          <td class="pl-num">{_fmt(tp)}</td>
          <td class="pl-num">{_fmt(cum)}</td>
        </tr>'''


def _block(label, sub, imp_tp, imp_cum):
    return f'''
        <tr class="blk"><td class="pl-name"><div class="pl-title">{label}</div><div class="pl-sub">{sub}</div></td>
          <td class="pl-metric">Impressions</td><td class="pl-num" style="color:{GOLD}">{_fmt(imp_tp)}</td>
          <td class="pl-num" style="color:{GOLD}">{_fmt(imp_cum)}</td></tr>'''


def render_html(d):
    rt, gt = d["rt"], d["gt"]
    period_lbl = f"{_md(d['start'])} – {_mdy(d['end'])}"
    yr = f"{_mdy(d['year_start'])} – {_mdy(d['year_end'])}"

    def yt_rows(p, name, ep_label, ep_sub):
        return (_row("YOUTUBE", f"{name} channel · {_fmt(p['yt_total']['ct_new'])} new videos this period", "Views",
                     p["yt_total"]["tp"], p["yt_total"]["cum"])
                + _row(ep_label, f"{ep_sub} · {_fmt(p['yt_full']['ct_new'])} new", "Views", p["yt_full"]["tp"], p["yt_full"]["cum"], True)
                + _row("CLIPS", f"Segment cutdowns · {_fmt(p['yt_clip']['ct_new'])} new", "Views", p["yt_clip"]["tp"], p["yt_clip"]["cum"], True)
                + _row("SHORTS", f"≤3:00 · {_fmt(p['yt_short']['ct_new'])} new", "Views", p["yt_short"]["tp"], p["yt_short"]["cum"], True))

    rt_rows = (_block("ROAD TRIPPIN'", "Presenting partnership · counts toward the delivery goal", rt["imp_tp"], rt["imp_cum"])
               + yt_rows(rt, "Road Trippin'", "FULL EPISODES", "Group episodes · Perk Unplugged · Channing's Mailbag")
               + _row("MEGAPHONE", "RSS &amp; Spotify · downloads + streams", "Total Delivery", rt["mega"]["tp"], rt["mega"]["cum"])
               + _row("INSTAGRAM", "@RoadTrippinShow · whole account (incl. Girls Tripp collabs)", "Views", rt["ig"]["tp"], rt["ig"]["cum"], gold=True)
               + _row("TIKTOK", f"@roadtrippinshow · {_fmt(rt['tiktok']['vids_tp'])} videos this period", "Views", rt["tiktok"]["tp"], rt["tiktok"]["cum"], gold=True)
               + _row("FACEBOOK", "@RoadTrippin page · Reels &amp; video", "Views", rt["fb"]["tp"], rt["fb"]["cum"], gold=True)
               + _row("X (TWITTER)", "Show account · @roadtrippin", "Impressions", rt["x"]["tp"], rt["x"]["cum"]))
    gt_rows = (_block("GIRLS TRIPP", "Presenting partnership · added value", gt["imp_tp"], gt["imp_cum"])
               + yt_rows(gt, "Girls Tripp", "FULL EPISODES", "Girls Tripp Full Episodes playlist")
               + _row("MEGAPHONE", "Girls Tripp feed · downloads + streams", "Total Delivery", gt["mega"]["tp"], gt["mega"]["cum"])
               + _row("INSTAGRAM", f"@girlstripppod · {_fmt(gt['ig']['posts_tp'])} non-collab posts this period (collabs counted under Road Trippin')",
                      "Views", gt["ig"]["tp"], gt["ig"]["cum"], gold=True))

    eps, integ = d["eps"], d["integrations"]
    T = d["targets"]
    talent_html = ""
    for t in d["talent"]:
        status = (f'<span class="ok">ON PACE</span>' if t["cum"] is not None and t["cum"] >= t["need"]
                  else f'<span class="behind">BEHIND · {t["need"] - (t["cum"] or 0):.0f} to catch up</span>' if t["cum"] is not None
                  else '<span class="pend">Pending</span>')
        talent_html += f'''
        <div class="talent-card">
          <div class="tc-name">{t['name']}<span class="tc-handle">{t['handle']}</span>
            <span class="tc-req">Min. {t['min_wk']}/wk · {status}</span></div>
          <div class="tc-stats">
            <div class="tc-stat"><div class="tc-lbl">THIS PERIOD</div><div class="tc-num">{_fmt(t['tp'])}</div><div class="tc-sub">POSTS</div></div>
            <div class="tc-stat"><div class="tc-lbl">SEASON TO DATE</div><div class="tc-num">{_fmt(t['cum'])}</div><div class="tc-sub">POSTS</div></div>
            <div class="tc-stat gold-box"><div class="tc-num gold">{t['need']:.0f}</div><div class="tc-sub">MINIMUM<br>TO DATE</div></div>
          </div>
        </div>'''
    tal_ok = d["talent_cum_total"] is not None and d["talent_cum_total"] >= d["talent_need_total"]
    pace_color = GREEN if d["pct_goal"] >= d["pct_elapsed"] else GOLD

    top_full = "".join(_content_card(i, show_dur=True) for i in d["top_full"])
    top_clip = "".join(_content_card(i) for i in d["top_clip"])
    top_short = "".join(_content_card(i) for i in d["top_short"])
    top_gt = "".join(_content_card(i) for i in d["top_gt"])
    top_social = "".join(_social_card(i) for i in d["top_social"])
    m = d["method"]

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Road Trippin' × Fanatics — {period_lbl}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700;800&family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>

<!-- ══════════════ PAGE 1 ══════════════ -->
<section class="page">
  <div class="hdr">
    <div>
      <div class="title">ROAD TRIPPIN' <span class="x">×</span> FANATICS<br>SPORTS &amp; CASINO</div>
      <div class="subt">Presenting Partnership · {d['season']} · Delivery Report</div>
    </div>
    <div class="hdr-r">
      <div class="eyebrow">Reporting Period</div>
      <div class="big">{period_lbl}</div>
      <div class="sm">Year 1: {yr} · ~85 episodes (min. 78)</div>
    </div>
  </div>

  <div class="cards">
    <div class="card"><div class="lbl">Season Views &amp; Downloads</div><div class="val">{_fmt(d['cum_vd'])}</div><div class="note">Road Trippin' + Girls Tripp · since {_md(d['year_start'])}</div></div>
    <div class="card"><div class="lbl">This Period Views &amp; Downloads</div><div class="val">{_fmt(d['tp_vd'])}</div><div class="note">{_md(d['start'])} – {_md(d['end'])} only</div></div>
    <div class="card"><div class="lbl">% of Year Elapsed</div><div class="val">{d['pct_elapsed']:.1f}%</div><div class="note">Of {d['year_days']}-day year</div></div>
    <div class="card"><div class="lbl">Days Into Season</div><div class="val">{d['days_into']}</div><div class="note">of {d['year_days']} days ({_md(d['year_start'])} → {_md(d['year_end'])})</div></div>
  </div>

  <div class="imp">
    <div>
      <div class="lbl">Impressions* · Season to date</div>
      <div class="num">{_fmt(d['total_imp'])}</div>
      <div class="vs">vs. 130,000,000 annual delivery goal</div>
    </div>
    <div class="pace">
      <b style="color:{pace_color}">{d['pct_goal']:.1f}%</b> of goal delivered with {d['pct_elapsed']:.1f}% of the year elapsed<br>
      At the current rate: on pace for <b>~{_fmt(d['pace'])}</b> impressions this year
      <div class="split"><span>Road Trippin' <b>{_fmt(rt['imp_cum'])}</b></span><span>Girls Tripp <b>{_fmt(gt['imp_cum'])}</b></span>
        <span>This period <b>{_fmt(d['tp_imp'])}</b></span></div>
    </div>
  </div>

  <div class="sec-h"><h2>Views &amp; Downloads</h2><div class="r">Season to date from {_md(d['year_start'])}</div></div>
  <div class="eyebrow" style="margin:4px 0 2px">Platform Delivery Breakdown · Raw Counts · Impressions shown per show</div>
  <table>
    <thead><tr><td>Platform</td><td>Metric Type</td><td style="text-align:right">This Period</td><td style="text-align:right">Season to Date</td></tr></thead>
    <tbody>{rt_rows}{gt_rows}</tbody>
  </table>
</section>

<!-- ══════════════ PAGE 2 ══════════════ -->
<section class="page">
  <div class="kpis" style="margin-top:0">
    <div class="kpi">
      <div class="kpi-h">Episode Delivery · Road Trippin'</div>
      <div class="big-row"><span class="big-num">{eps['cum']}</span><span class="big-pct">{eps['cum'] / T['eps'] * 100:.1f}%</span><span class="big-tgt">~{T['eps']}</span></div>
      <div class="micro">Episodes aired · % of target · min. {T['eps_min']}</div>
      {_bar(eps['cum'] / T['eps'] * 100)}
      <div class="line"><span>Group Episodes (Full Crew)</span><span class="v">{eps['group']}</span></div>
      <div class="line"><span>Perk Unplugged</span><span class="v">{eps['solo_perk']} <small>on hiatus</small></span></div>
      <div class="line"><span>Channing's Mailbag</span><span class="v">{eps['solo_chan']} <small>on hiatus</small></span></div>
      <div class="line"><span><b>Total Aired</b></span><span class="v">{eps['cum']} <small>/ ~{T['eps']}</small></span></div>
      <div class="line"><span>Girls Tripp episodes (added value)</span><span class="v">{_fmt(eps['gt'])}</span></div>
    </div>
    <div class="kpi">
      <div class="kpi-h">Integrations Delivered</div>
      <div class="big-row"><span class="big-num">{integ['cum']}</span><span class="big-pct">{integ['cum'] / T['integrations'] * 100:.1f}%</span><span class="big-tgt">~{T['integrations']}</span></div>
      <div class="micro">Total delivered · % of target · season</div>
      {_bar(integ['cum'] / T['integrations'] * 100)}
      <div class="line"><span>Top-of-Show Shoutouts</span><span class="v">{integ['shoutouts']} <small>/ ~{T['eps']}</small></span></div>
      <div class="line"><span>Sponsored Segments (On-Cam)</span><span class="v">{integ['segments']} <small>/ ~{T['eps']}</small></span></div>
      <div class="line"><span>Host-Read Ad Reads (60s)</span><span class="v">{integ['ad_reads']} <small>/ ~{T['eps']}</small></span></div>
    </div>
    <div class="kpi">
      <div class="kpi-h">Talent Social Amplification</div>
      <div class="big-row"><span class="big-num">{_fmt(d['talent_tp_total'])}</span><span class="big-pct">{_fmt(d['talent_cum_total'])}</span><span class="big-tgt">min. {d['talent_need_total']:.0f}</span></div>
      <div class="micro">This period · season to date · minimum to date (575/yr)</div>
      {_bar((d['talent_cum_total'] or 0) / max(d['talent_need_total'], 1) * 100, GREEN if tal_ok else GOLD)}
      <div class="micro" style="color:{GREEN if tal_ok else 'var(--mut)'}">{'✓ On pace' if tal_ok else 'Behind the weekly minimums'} · contractual minimum 575 posts per year</div>
      {talent_html}
    </div>
  </div>

  <div class="sec-h" style="margin-top:18px"><h2>Top Content — {_md(d['start'])} – {_md(d['end'])}</h2><div class="r">Ranked by Views</div></div>
  <div class="eyebrow" style="margin:4px 0">Best-performing content published {_md(d['start'])} – {_md(d['end'])} · views to date · click any title to view</div>
  <div class="eyebrow" style="color:{GOLD};font-size:11px;margin-top:8px">★ Top 3 Full Episodes · Road Trippin' · YouTube</div>
  <div class="cc-grid">{top_full}</div>
  <div class="eyebrow" style="color:{GOLD};font-size:11px">★ Top 3 Clips · Road Trippin' · YouTube</div>
  <div class="cc-grid">{top_clip}</div>
</section>

<!-- ══════════════ PAGE 3 ══════════════ -->
<section class="page">
  <div class="eyebrow" style="color:{GOLD};font-size:11px">★ Top 3 Shorts · Road Trippin' · YouTube</div>
  <div class="cc-grid">{top_short}</div>
  <div class="eyebrow" style="color:{GOLD};font-size:11px">★ Top 3 · Girls Tripp · YouTube</div>
  <div class="cc-grid">{top_gt}</div>
  <div class="eyebrow" style="color:{GOLD};font-size:11px">★ Top 3 Social Posts · Instagram / TikTok / X</div>
  <div class="cc-grid">{top_social or '<div class="sc"><div class="cc-title pend">Pending</div></div>'}</div>

  <div class="goal">
    <div class="goal-top">
      <div>
        <h2>*How Impressions Are Calculated</h2>
        <div class="desc">Each episode view counts as multiple impressions — one per sponsored asset delivered within it.
          YouTube counts every view during the period on content published since Oct 1, 2025. Annual delivery goal: 130,000,000.</div>
      </div>
      <div class="tot"><div class="l">Impressions · Season to date</div><div class="n">{_fmt(d['total_imp'])}</div>
        <div class="micro">{d['pct_goal']:.1f}% of 130M goal</div></div>
    </div>
    <div class="mults">
      <div class="mult">
        <h3>Full Episodes <span class="x">6× · Solo 5×</span></h3>
        <ul><li>✓ Top-of-Show Brand Shoutout</li><li>✓ Sponsored Segment (group)</li><li>✓ Video Ad Read</li>
            <li>✓ Audio Ad Read</li><li>✓ Logo Watermark</li><li>✓ On-Set Branding</li></ul>
        <div class="calc">Road Trippin' {_fmt(m['rt_full_views'])} views → <b>{_fmt(m['rt_full_imp'])} imp.</b><br>
          Girls Tripp {_fmt(m['gt_full_views'])} views → <b>{_fmt(m['gt_full_imp'])} imp.</b></div>
      </div>
      <div class="mult">
        <h3>Clips &amp; Shorts <span class="x">2× Multiplier</span></h3>
        <ul><li>✓ View</li><li>✓ Logo Watermark</li></ul>
        <div class="calc">{_fmt(m['cs_views'])} views → <b>{_fmt(m['cs_imp'])} imp.</b></div>
      </div>
      <div class="mult">
        <h3>Audio &amp; Social <span class="x">1× Multiplier</span></h3>
        <ul><li>✓ Megaphone downloads + streams</li><li>✓ Instagram, TikTok, Facebook views</li><li>✓ X impressions</li></ul>
        <div class="calc">{_fmt(m['other'])} → <b>{_fmt(m['other'])} imp.</b></div>
      </div>
    </div>
  </div>

  <div class="foot">
    <span>Road Trippin' Show × Fanatics Sports &amp; Casino · Presenting Partnership</span>
    <span>Prepared by Rain Delay Media · Confidential</span>
    <span>Generated {_Mdy(d['generated'])}</span>
  </div>
</section>
</body></html>'''
