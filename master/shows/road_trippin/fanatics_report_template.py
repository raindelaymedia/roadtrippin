"""
Fanatics delivery report — HTML renderer.
render_html(data) -> a print-ready HTML string (US Letter, gold #C9A84C,
Barlow Condensed) reproducing the 4-page monthly report layout.
"""

GOLD = "#C9A84C"


def _fmt(n):
    try:
        return f"{int(round(float(n))):,}"
    except (ValueError, TypeError):
        return str(n)


def _md(dt):
    """'May 1' — portable replacement for strftime('%b %-d') which is Unix-only."""
    return f"{dt.strftime('%b')} {dt.day}"


def _mdy(dt):
    """'May 1, 2026' — portable replacement for strftime('%b %-d, %Y')."""
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def _Mdy(dt):
    """'May 1, 2026' with full month — portable replacement for strftime('%B %-d, %Y')."""
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def _bar(pct, exceeded=False):
    w = min(pct, 100)
    color = GOLD if not exceeded else "#2E7D32"
    return (f'<div class="bar"><div class="bar-fill" '
            f'style="width:{w:.1f}%;background:{color}"></div></div>')


def _content_card(item, show_dur=False):
    dur = (f'<span class="cc-dur"> · {item["dur"]}</span>'
           if show_dur and item.get("dur") else "")
    thumb = item.get("thumb", "")
    return f'''
    <a class="cc" href="{item.get('url','#')}">
      <div class="cc-thumb" style="background-image:url('{thumb}')"></div>
      <div class="cc-body">
        <div class="cc-rank">#{item['rank']}<span class="cc-views">{_fmt(item['views'])} VIEWS</span></div>
        <div class="cc-meta">{item.get('date','')}{dur}</div>
        <div class="cc-title">{item['title']}</div>
      </div>
    </a>'''


def _social_card(item):
    return f'''
    <div class="sc">
      <div class="cc-rank">#{item['rank']}<span class="cc-views">{_fmt(item['views'])} VIEWS</span></div>
      <div class="sc-plat">{item['platform'].upper()}<span class="sc-date">{item.get('date','')}</span></div>
      <div class="cc-title">{item['title']}</div>
    </div>'''


def render_html(d):
    p = d["platforms"]
    period_lbl = f"{_md(d['start'])} – {_mdy(d['end'])}"
    talent_html = ""
    for t in d["talent"]:
        talent_html += f'''
        <div class="talent-card">
          <div class="tc-name">{t['name']}<span class="tc-handle">{t['handle']}</span>
            <span class="tc-req">Min. {t['min_wk']}/wk required</span></div>
          <div class="tc-stats">
            <div class="tc-stat"><div class="tc-lbl">THIS PERIOD</div><div class="tc-num">{_fmt(t['tp'])}</div><div class="tc-sub">POSTS</div></div>
            <div class="tc-stat"><div class="tc-lbl">CUMULATIVE</div><div class="tc-num">{_fmt(t['cum'])}</div><div class="tc-sub">POSTS</div></div>
            <div class="tc-stat gold-box"><div class="tc-num gold">{t['wk_avg']}+</div><div class="tc-sub">/ WK AVG<br>VS {t['min_wk']}/WK</div></div>
          </div>
        </div>'''

    talent_exceeded = d["talent_cum_total"] >= 182
    talent_pct = d["talent_cum_total"] / 182 * 100

    def row(label, sub, tp, cum, indent=False):
        cls = "ind" if indent else ""
        return f'''
        <tr class="{cls}">
          <td class="pl-name"><div class="pl-title">{label}</div><div class="pl-sub">{sub}</div></td>
          <td class="pl-metric">Views</td>
          <td class="pl-num">{_fmt(tp)}</td>
          <td class="pl-num">{_fmt(cum)}</td>
        </tr>'''

    yt = p["yt_total"]; ytf = p["yt_full"]; ytc = p["yt_clip"]; yts = p["yt_short"]
    views_rows = (
        row("YOUTUBE", f"Content 2/16+ · {_fmt(yt['ct_total'])} videos ({_fmt(yt['ct_new'])} new this period)", yt["tp"], yt["cum"])
        + row("FULL EPISODES", f"&gt;30 min · {_fmt(ytf['ct_total'])} videos ({_fmt(ytf['ct_new'])} new this period)", ytf["tp"], ytf["cum"], True)
        + row("SEGMENT CLIPS", f"3:01–30 min · {_fmt(ytc['ct_total'])} videos ({_fmt(ytc['ct_new'])} new this period)", ytc["tp"], ytc["cum"], True)
        + row("SHORTS", f"≤3:00 · {_fmt(yts['ct_total'])} videos ({_fmt(yts['ct_new'])} new this period)", yts["tp"], yts["cum"], True)
    )
    other_rows = f'''
        <tr><td class="pl-name"><div class="pl-title">MEGAPHONE</div><div class="pl-sub">RSS &amp; Spotify</div></td>
            <td class="pl-metric">Total Delivery · content 2/16+ only</td>
            <td class="pl-num">{_fmt(p['mega']['tp'])}</td><td class="pl-num">{_fmt(p['mega']['cum'])}</td></tr>
        <tr><td class="pl-name"><div class="pl-title" style="color:{GOLD}">INSTAGRAM</div><div class="pl-sub">@RoadTrippinShow account only</div></td>
            <td class="pl-metric">Views / Reach</td>
            <td class="pl-num">{_fmt(p['ig']['tp'])}</td><td class="pl-num">{_fmt(p['ig']['cum'])}</td></tr>
        <tr><td class="pl-name"><div class="pl-title" style="color:{GOLD}">TIKTOK</div><div class="pl-sub">Per-video · {_fmt(p['tiktok']['vids_tp'])} videos this period · {_fmt(p['tiktok']['vids_total'])} total</div></td>
            <td class="pl-metric">Views</td>
            <td class="pl-num">{_fmt(p['tiktok']['tp'])}</td><td class="pl-num">{_fmt(p['tiktok']['cum'])}</td></tr>
        <tr><td class="pl-name"><div class="pl-title">X (TWITTER)</div><div class="pl-sub">Show account · @roadtrippin</div></td>
            <td class="pl-metric">Impressions</td>
            <td class="pl-num">{_fmt(p['x']['tp'])}</td><td class="pl-num">{_fmt(p['x']['cum'])}</td></tr>'''

    eps, integ = d["eps"], d["integrations"]
    top_full = "".join(_content_card(i, show_dur=True) for i in d["top_full"])
    top_clip = "".join(_content_card(i) for i in d["top_clip"])
    top_short = "".join(_content_card(i) for i in d["top_short"])
    top_social = "".join(_social_card(i) for i in d["top_social"])

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Road Trippin' × Fanatics — {period_lbl}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700;800&family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --gold:{GOLD}; --ink:#1a1a1a; --mut:#8a8a8a; --line:#e6e6e6; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Barlow',sans-serif; color:var(--ink); margin:0; background:#f3f3f3; font-size:12px; }}
  .page {{ width:8.5in; min-height:11in; padding:0.5in 0.55in; margin:14px auto; background:#fff;
          box-shadow:0 2px 12px rgba(0,0,0,.12); }}
  h1,h2,h3,.cond {{ font-family:'Barlow Condensed',sans-serif; }}
  .eyebrow {{ font-family:'Barlow Condensed'; letter-spacing:.28em; font-weight:600; color:var(--mut); font-size:9px; text-transform:uppercase; }}

  /* header */
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid var(--gold); padding-bottom:12px; }}
  .title {{ font-family:'Barlow Condensed'; font-weight:800; font-size:42px; line-height:.95; letter-spacing:-.01em; text-transform:uppercase; }}
  .title .x {{ color:var(--gold); }}
  .subt {{ letter-spacing:.22em; font-weight:600; color:var(--mut); font-size:9px; text-transform:uppercase; margin-top:6px; }}
  .hdr-r {{ text-align:right; }}
  .hdr-r .big {{ font-family:'Barlow Condensed'; font-weight:700; font-size:20px; }}
  .hdr-r .sm {{ color:var(--mut); font-size:10px; }}

  /* metric cards */
  .cards {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:16px 0; }}
  .card {{ border:1px solid var(--line); border-radius:3px; padding:12px 14px; }}
  .card .lbl {{ font-size:8px; letter-spacing:.16em; color:var(--mut); font-weight:600; text-transform:uppercase; }}
  .card .val {{ font-family:'Barlow Condensed'; font-weight:700; font-size:30px; line-height:1.05; margin-top:6px; }}
  .card .note {{ color:var(--mut); font-size:9.5px; margin-top:2px; }}

  /* impressions banner */
  .imp {{ border:1px solid var(--line); border-radius:3px; padding:16px 18px; display:flex; gap:26px; align-items:center; margin-bottom:18px; }}
  .imp .lbl {{ font-size:8px; letter-spacing:.2em; color:var(--gold); font-weight:700; text-transform:uppercase; }}
  .imp .num {{ font-family:'Barlow Condensed'; font-weight:800; font-size:34px; color:var(--gold); line-height:1; }}
  .imp .vs {{ color:var(--mut); font-size:12px; }}
  .imp .pace {{ font-size:10px; color:#555; line-height:1.5; }}
  .imp .pace b {{ color:var(--gold); }}

  /* section heading */
  .sec-h {{ display:flex; justify-content:space-between; align-items:baseline; border-bottom:1px solid var(--ink); padding-bottom:4px; margin-bottom:2px; }}
  .sec-h h2 {{ font-weight:700; font-size:17px; letter-spacing:.02em; margin:0; text-transform:uppercase; }}
  .sec-h .r {{ font-size:8px; letter-spacing:.18em; color:var(--mut); font-weight:600; }}

  /* views table */
  table {{ width:100%; border-collapse:collapse; }}
  thead td {{ font-size:8px; letter-spacing:.14em; color:var(--mut); font-weight:600; padding:8px 6px; text-transform:uppercase; }}
  tbody tr {{ border-top:1px solid var(--line); }}
  td {{ padding:9px 6px; vertical-align:middle; }}
  tr.ind .pl-name {{ padding-left:22px; }}
  tr.ind .pl-title {{ font-size:10px; }}
  .pl-title {{ font-family:'Barlow Condensed'; font-weight:700; font-size:13px; text-transform:uppercase; }}
  .pl-sub {{ color:var(--mut); font-size:9px; font-style:italic; }}
  .pl-metric {{ color:#666; font-size:10px; font-style:italic; width:150px; }}
  .pl-num {{ font-family:'Barlow Condensed'; font-weight:700; font-size:15px; text-align:right; white-space:nowrap; }}

  /* three KPI columns */
  .kpis {{ display:grid; grid-template-columns:1fr 1fr 1.35fr; gap:12px; margin-top:16px; }}
  .kpi {{ border:1px solid var(--line); border-radius:3px; padding:12px; }}
  .kpi-h {{ font-size:8px; letter-spacing:.16em; color:var(--mut); font-weight:600; text-transform:uppercase; line-height:1.3; }}
  .big-row {{ display:flex; align-items:baseline; gap:8px; margin:6px 0 2px; }}
  .big-num {{ font-family:'Barlow Condensed'; font-weight:800; font-size:30px; line-height:1; }}
  .big-pct {{ font-family:'Barlow Condensed'; font-weight:800; font-size:22px; color:var(--gold); }}
  .big-tgt {{ font-family:'Barlow Condensed'; font-weight:700; font-size:20px; color:var(--mut); }}
  .micro {{ font-size:7.5px; letter-spacing:.1em; color:var(--mut); text-transform:uppercase; }}
  .bar {{ height:5px; background:#eee; border-radius:3px; overflow:hidden; margin:8px 0; }}
  .bar-fill {{ height:100%; }}
  .line {{ display:flex; justify-content:space-between; font-size:10.5px; padding:3px 0; border-top:1px dotted var(--line); }}
  .line .v {{ font-family:'Barlow Condensed'; font-weight:700; }}
  .line .v small {{ color:var(--mut); font-weight:500; }}

  /* talent */
  .talent-card {{ border-top:1px solid var(--line); padding:8px 0; }}
  .talent-card:first-child {{ border-top:none; }}
  .tc-name {{ font-family:'Barlow Condensed'; font-weight:700; font-size:13px; }}
  .tc-handle {{ color:var(--mut); font-weight:500; font-size:9px; margin-left:6px; }}
  .tc-req {{ color:var(--mut); font-size:8px; display:block; }}
  .tc-stats {{ display:grid; grid-template-columns:repeat(3,1fr); gap:6px; margin-top:5px; text-align:center; }}
  .tc-lbl {{ font-size:7px; letter-spacing:.1em; color:var(--mut); }}
  .tc-num {{ font-family:'Barlow Condensed'; font-weight:800; font-size:20px; line-height:1; }}
  .tc-num.gold {{ color:var(--gold); }}
  .tc-sub {{ font-size:7px; color:var(--mut); }}
  .gold-box {{ border:1px solid var(--gold); border-radius:3px; padding:3px 0; }}

  /* top content cards */
  .cc-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:10px 0 18px; }}
  .cc {{ border:1px solid var(--line); border-radius:3px; overflow:hidden; text-decoration:none; color:inherit; display:block; }}
  .cc-thumb {{ aspect-ratio:16/9; background:#222 center/cover no-repeat; }}
  .cc-body {{ padding:8px 10px 11px; }}
  .cc-rank {{ font-family:'Barlow Condensed'; font-weight:800; font-size:22px; display:flex; align-items:baseline; gap:8px; }}
  .cc-views {{ font-size:13px; color:var(--gold); }}
  .cc-meta {{ font-size:8px; letter-spacing:.12em; color:var(--mut); text-transform:uppercase; margin:2px 0 4px; }}
  .cc-title {{ font-weight:600; font-size:11px; line-height:1.25; }}
  .sc {{ border:1px solid var(--line); border-left:3px solid var(--gold); border-radius:3px; padding:9px 11px; }}
  .sc-plat {{ font-family:'Barlow Condensed'; font-weight:700; font-size:11px; color:var(--gold); margin:2px 0 4px; }}
  .sc-date {{ color:var(--mut); font-weight:500; margin-left:8px; letter-spacing:.1em; }}

  /* goal box */
  .goal {{ border:1px solid var(--line); border-radius:3px; padding:16px 18px; margin-top:6px; }}
  .goal-top {{ display:flex; justify-content:space-between; align-items:flex-start; }}
  .goal h2 {{ font-weight:700; font-size:18px; margin:0; text-transform:uppercase; }}
  .goal .desc {{ color:#666; font-size:10px; max-width:62%; margin-top:4px; }}
  .goal .tot {{ text-align:right; }}
  .goal .tot .l {{ font-size:8px; letter-spacing:.16em; color:var(--mut); }}
  .goal .tot .n {{ font-family:'Barlow Condensed'; font-weight:800; font-size:26px; color:var(--gold); }}
  .mults {{ display:grid; grid-template-columns:repeat(3,1fr); gap:18px; margin-top:14px; }}
  .mult h3 {{ font-weight:700; font-size:12px; margin:0; text-transform:uppercase; }}
  .mult .x {{ color:var(--gold); font-family:'Barlow Condensed'; font-weight:800; font-size:15px; }}
  .mult ul {{ list-style:none; padding:0; margin:8px 0 0; }}
  .mult li {{ font-size:9.5px; color:#444; padding:1.5px 0; }}
  .mult .calc {{ font-style:italic; font-size:9.5px; color:#666; border-top:1px solid var(--line); margin-top:8px; padding-top:6px; }}
  .mult .calc b {{ color:var(--gold); font-style:normal; }}

  .foot {{ display:flex; justify-content:space-between; color:var(--mut); font-size:7.5px; letter-spacing:.12em;
           text-transform:uppercase; border-top:1px solid var(--line); margin-top:18px; padding-top:8px; }}

  @media print {{
    body {{ background:#fff; }}
    .page {{ box-shadow:none; margin:0; width:auto; min-height:auto; padding:0.4in 0.45in; }}
    .page + .page {{ page-break-before:always; }}
    .cc, .sc, .talent-card, .kpi, .mult {{ break-inside:avoid; }}
  }}
  @page {{ size:letter; margin:0; }}
</style></head><body>

<!-- ══════════════ PAGE 1 ══════════════ -->
<section class="page">
  <div class="hdr">
    <div>
      <div class="title">ROAD TRIPPIN' <span class="x">×</span> FANATICS<br>SPORTSBOOK</div>
      <div class="subt">Presenting Partnership · Monthly Delivery Report</div>
    </div>
    <div class="hdr-r">
      <div class="eyebrow">Reporting Period</div>
      <div class="big">{period_lbl}</div>
      <div class="sm">Term: Feb 13, 2026 – Sep 13, 2026 · ~94 Episodes</div>
    </div>
  </div>

  <div class="cards">
    <div class="card"><div class="lbl">Cumulative Views &amp; Downloads</div><div class="val">{_fmt(d['cum_vd'])}</div><div class="note">All platforms · since 2/17</div></div>
    <div class="card"><div class="lbl">This Period Views &amp; Downloads</div><div class="val">{_fmt(d['tp_vd'])}</div><div class="note">{_md(d['start'])} – {_md(d['end'])} only</div></div>
    <div class="card"><div class="lbl">% of Term Elapsed</div><div class="val">{d['pct_elapsed']:.2f}%</div><div class="note">Of 212-day term</div></div>
    <div class="card"><div class="lbl">Days Into Partnership</div><div class="val">{d['days_into']}</div><div class="note">of 212 days (Feb 13 → Sep 13)</div></div>
  </div>

  <div class="imp">
    <div>
      <div class="lbl">Impressions*</div>
      <div class="num">{_fmt(d['total_imp'])}</div>
      <div class="vs">vs. 47M plan</div>
    </div>
    <div class="pace">
      <b>{d['pct_plan']:.2f}%</b> &nbsp;At current rate: on pace for <b>~{_fmt(d['pace'])}</b> total impressions<br>
      Goal: 47,000,000 – 50,000,000 · 212-day term
    </div>
  </div>

  <div class="sec-h"><h2>Views &amp; Downloads</h2><div class="r">Cumulative from Feb 17</div></div>
  <div class="eyebrow" style="margin:4px 0 2px">Platform Delivery Breakdown · Raw Counts · Not Impression Equivalents</div>
  <table>
    <thead><tr><td>Platform</td><td>Metric Type</td><td style="text-align:right">This Period (raw)</td><td style="text-align:right">Cumulative (raw)</td></tr></thead>
    <tbody>{views_rows}{other_rows}</tbody>
  </table>

  <div class="kpis">
    <div class="kpi">
      <div class="kpi-h">Episode Delivery Tracker</div>
      <div class="big-row"><span class="big-num">{eps['cum']}</span><span class="big-pct">{eps['cum']/94*100:.1f}%</span><span class="big-tgt">~94</span></div>
      <div class="micro">Episodes aired · % of target · total target</div>
      {_bar(eps['cum']/94*100)}
      <div class="line"><span>Group Episodes (Full Crew)</span><span class="v">{eps['group']} <small>/ ~56</small></span></div>
      <div class="line"><span>Solo – Kendrick Perkins</span><span class="v">{eps['solo_perk']} <small>/ ~24</small></span></div>
      <div class="line"><span>Solo – Channing Frye</span><span class="v">{eps['solo_chan']} <small>/ ~14</small></span></div>
      <div class="line"><span><b>Total Aired</b></span><span class="v">{eps['cum']} <small>/ ~94</small></span></div>
    </div>
    <div class="kpi">
      <div class="kpi-h">Integrations Delivered</div>
      <div class="big-row"><span class="big-num">{integ['cum']}</span><span class="big-pct">{integ['cum']/240*100:.1f}%</span><span class="big-tgt">~240</span></div>
      <div class="micro">Total delivered · % of target · {('94+52+94')}</div>
      {_bar(integ['cum']/240*100)}
      <div class="line"><span>Top-of-Show Shoutouts</span><span class="v">{integ['shoutouts']} <small>/ ~94</small></span></div>
      <div class="line"><span>Sponsored Segments (On-Cam)</span><span class="v">{integ['segments']} <small>/ ~52</small></span></div>
      <div class="line"><span>Host-Read Ad Reads (60s)</span><span class="v">{integ['ad_reads']} <small>/ ~94</small></span></div>
    </div>
    <div class="kpi">
      <div class="kpi-h">Talent Social Amplification</div>
      <div class="big-row"><span class="big-num">{d['talent_tp_total']}</span><span class="big-pct">{d['talent_cum_total']}</span><span class="big-tgt">~182</span></div>
      <div class="micro">This period · cumulative total · contractual target</div>
      {_bar(talent_pct, exceeded=talent_exceeded)}
      <div class="micro" style="color:{'#2E7D32' if talent_exceeded else 'var(--mut)'}">{talent_pct:.1f}% {'✓ Exceeded' if talent_exceeded else ''} ~182 total posts over term</div>
      {talent_html}
    </div>
  </div>
</section>

<!-- ══════════════ PAGE 2 ══════════════ -->
<section class="page">
  <div class="sec-h"><h2>Top Content — {_md(d['start'])} – {_md(d['end'])}</h2><div class="r">Ranked by Views</div></div>
  <div class="eyebrow" style="margin:4px 0">Best-Performing Content Published {_md(d['start'])} – {_md(d['end'])} · Click Any Title To View</div>

  <div class="eyebrow" style="color:{GOLD};font-size:11px;margin-top:8px">★ Top 3 Full Episodes · YouTube</div>
  <div class="cc-grid">{top_full}</div>

  <div class="eyebrow" style="color:{GOLD};font-size:11px">★ Top 3 Segment Clips · YouTube</div>
  <div class="cc-grid">{top_clip}</div>

  <div class="eyebrow" style="color:{GOLD};font-size:11px">★ Top 3 Shorts · YouTube</div>
  <div class="cc-grid">{top_short}</div>
</section>

<!-- ══════════════ PAGE 3 ══════════════ -->
<section class="page">
  <div class="eyebrow" style="color:{GOLD};font-size:11px">★ Top 3 Social Posts · Instagram / TikTok / X</div>
  <div class="cc-grid">{top_social}</div>

  <div class="goal">
    <div class="goal-top">
      <div>
        <h2>*How the 47–50M Goal Is Calculated</h2>
        <div class="desc">Each episode view counts as multiple impressions — one per sponsored asset delivered within that episode.</div>
      </div>
      <div class="tot"><div class="l">Impressions Total</div><div class="n">{_fmt(d['total_imp'])}</div>
        <div class="micro">{d['pct_plan']:.2f}% of 47M goal</div></div>
    </div>
    <div class="mults">
      <div class="mult">
        <h3>Group Episodes <span class="x">6× Multiplier</span></h3>
        <ul><li>✓ Top-of-Show Brand Shoutout</li><li>✓ Sponsored Segment</li><li>✓ Video Ad Read</li>
            <li>✓ Audio Ad Read</li><li>✓ Logo Watermark</li><li>✓ On-Set Branding</li></ul>
        <div class="calc">{_fmt(d['cum_full_views'])} views → <b>{_fmt(d['imp_full'])} imp.</b></div>
      </div>
      <div class="mult">
        <h3>Solo Episodes (Perk / Channing) <span class="x">5× Multiplier</span></h3>
        <ul><li>✓ Top-of-Show Brand Shoutout</li><li>✓ Video Ad Read</li><li>✓ Audio Ad Read</li>
            <li>✓ Logo Watermark</li><li>✓ On-Set Branding</li></ul>
        <div class="calc">Included in full ep total above</div>
      </div>
      <div class="mult">
        <h3>Clips &amp; Shorts <span class="x">2× Multiplier</span></h3>
        <ul><li>✓ View</li><li>✓ Logo Watermark</li></ul>
        <div class="calc">{_fmt(d['cum_clips_short_views'])} views → <b>{_fmt(d['imp_clips_short'])} imp.</b></div>
      </div>
    </div>
  </div>

  <div class="foot">
    <span>Road Trippin' Show × Fanatics Sportsbook · Presenting Partnership</span>
    <span>Prepared by Rain Delay Media · Confidential &amp; Internal</span>
    <span>Generated {_Mdy(d['generated'])}</span>
  </div>
</section>
</body></html>'''