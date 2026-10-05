"""
The Schultz Report × Fanatics delivery report — HTML renderer.
render_html(data) -> print-ready HTML (US Letter, SR blue #11116b + yellow #E8C840,
Barlow Condensed). Same layout language as the Road Trippin' report.
"""

BLUE = "#11116b"
YELLOW = "#E8C840"
GREEN = "#2E7D32"


def _fmt(n):
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


def _pct(a, b):
    return (a / b * 100) if b else 0


def _bar(pct, exceeded=False):
    w = min(pct, 100)
    return (f'<div class="bar"><div class="bar-fill" '
            f'style="width:{w:.1f}%;background:{GREEN if exceeded else YELLOW}"></div></div>')


def _line(label, cum, target, tp=None):
    small = f" <small>/ ~{target}</small>" if target else ""
    tp_txt = f'<small style="margin-right:6px">+{tp} this period</small>' if tp else ""
    return f'<div class="line"><span>{label}</span><span class="v">{tp_txt}{_fmt(cum)}{small}</span></div>'


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


def _empty(msg):
    return f'<div class="micro" style="padding:14px 0">{msg}</div>'


def render_html(d):
    r, c, k = d["row"], d["cum"], d["kpi"]
    period_lbl = f"{_md(d['start'])} – {_mdy(d['end'])}"
    term_lbl = f"{_mdy(d['term_start'])} – {_mdy(d['term_end'])}"

    def row(label, sub, metric, tp, cum, indent=False):
        return f'''
        <tr class="{'ind' if indent else ''}">
          <td class="pl-name"><div class="pl-title">{label}</div><div class="pl-sub">{sub}</div></td>
          <td class="pl-metric">{metric}</td>
          <td class="pl-num">{_fmt(tp)}</td><td class="pl-num">{_fmt(cum)}</td>
        </tr>'''

    grp = lambda t: f'<tr class="grp"><td colspan="4">{t}</td></tr>'
    platform_rows = (
        grp("YouTube")
        + row("YOUTUBE", f"{_fmt(c['yt_total_count_new'])} videos this term ({_fmt(r['yt_total_count_new'])} new this period)", "Views", r["yt_total_views"], c["yt_total_views"])
        + row("FULL EPISODES", f"&gt;30 min · {_fmt(r['yt_full_count_new'])} new this period", "Views", r["yt_full_views"], c["yt_full_views"], True)
        + row("SEGMENT CLIPS", f"3:01–30 min · {_fmt(r['yt_clip_count_new'])} new this period", "Views", r["yt_clip_views"], c["yt_clip_views"], True)
        + row("SHORTS", f"≤3:00 · {_fmt(r['yt_short_count_new'])} new this period", "Views", r["yt_short_views"], c["yt_short_views"], True)
        + grp("Audio")
        + row("PODCAST", "RSS · Spotify · Apple Podcasts", "Downloads", r["audio_downloads"], c["audio_downloads"])
        + grp("Social · Schultz Report show accounts")
        + row("INSTAGRAM", "SR's own posts only · collabs with @JordanSchultz counted under Jordan", "Views", r["ig_views"], c["ig_views"])
        + row("TIKTOK", f"Show account · {_fmt(r['tiktok_posts'])} videos this period · own posts, separate from Jordan's", "Views", r["tiktok_views"], c["tiktok_views"])
        + row("X (TWITTER)", "Show account · own posts, separate from Jordan's", "Impressions", r["x_imp"], c["x_imp"])
        + grp("Social · Reporter &amp; talent accounts — Fanatics-integrated posts only")
        + row("@JORDANSCHULTZ · X", f"{_fmt(r['js_x_posts'])} Fanatics posts this period", "Impressions", r["js_x_views"], c["js_x_views"])
        + row("@JORDANSCHULTZ · INSTAGRAM", f"{_fmt(r['js_ig_posts'])} Fanatics posts this period", "Views", r["js_ig_views"], c["js_ig_views"])
        + row("@JORDANSCHULTZ · TIKTOK", f"{_fmt(r['js_tt_posts'])} Fanatics posts this period", "Views", r["js_tt_views"], c["js_tt_views"])
        + row("@KEYSHAWNJOHNSON", f"Instagram + X · {_fmt(r['kj_posts'])} Fanatics posts this period", "Views", r["kj_views"], c["kj_views"])
    )

    def k3(title, key, unit):
        v = k[key]
        return f'''
        <div class="k3"><div class="h">{title}</div>
          <div class="rowv"><span>{unit} · period</span><b>{_fmt(v['tp_views'])}</b></div>
          <div class="rowv"><span>{unit} · cumulative</span><b>{_fmt(v['cum_views'])}</b></div>
          <div class="rowv"><span>Impressions · cum.</span><b style="color:{BLUE}">{_fmt(v['cum_imp'])}</b></div>
        </div>'''

    # ── episodes ──
    e = d["eps"]
    ep_lines = "".join(_line(f"{t['label']}{' · 5×' if not t['seg'] else ''}", t["cum"], t["plan"], t["tp"]) for t in e["types"])
    floor_pos, tgt_pos = 90 / 115 * 100, 100 / 115 * 100

    # ── sponsorship / content ──
    sponsor_total = sum(s["cum"] for s in d["sponsor"])
    sponsor_target = sum(s["target"] for s in d["sponsor"])
    sponsor_lines = "".join(_line(s["label"], s["cum"], s["target"], s["tp"]) for s in d["sponsor"])
    content_lines = "".join(_line(s["label"], s["cum"], s["target"], s["tp"]) for s in d["content"])

    # ── reporter channels ──
    rep_html = ""
    for rp in d["reporter"]:
        ok = rp["wk_avg"] >= rp["min_wk"]
        tag = f'<span class="tag {"ok" if ok else "low"}">{"ON PACE" if ok else "BELOW MIN"}</span>' if rp["cum_posts"] else '<span class="tag na">NO DATA</span>'
        rep_html += f'''
        <div class="talent-card">
          <div class="tc-name">{rp['name']}{tag}<span class="tc-req">Min. {rp['min_wk']}/wk · ~{rp['target']} posts over term</span></div>
          <div class="tc-stats">
            <div class="tc-stat"><div class="tc-lbl">THIS PERIOD</div><div class="tc-num">{_fmt(rp['tp_posts'])}</div><div class="tc-sub">POSTS</div></div>
            <div class="tc-stat"><div class="tc-lbl">CUMULATIVE</div><div class="tc-num">{_fmt(rp['cum_posts'])}</div><div class="tc-sub">{_fmt(rp['cum_views'])} {rp['unit'].upper()}</div></div>
            <div class="tc-stat gold-box"><div class="tc-num gold">{rp['wk_avg']:.1f}</div><div class="tc-sub">/ WK AVG<br>VS {rp['min_wk']}/WK</div></div>
          </div>
        </div>'''
    kj = d["keyshawn"]
    rep_html += f'''
        <div class="talent-card">
          <div class="tc-name">KEYSHAWN JOHNSON<span class="tc-handle">@KeyshawnJohnson · IG + X</span><span class="tc-req">Min. {kj['min_wk']}/wk in season · ~{kj['target']} posts</span></div>
          {_line("Fanatics posts", kj["cum_posts"], kj["target"], kj["tp_posts"])}
          {_line("Fanatics-post views", kj["cum_views"], None, None)}
        </div>'''

    ev_lines = "".join(_line(ev["label"], ev["cum"], ev["target"], ev["tp"]) for ev in d["events"])

    top_full = "".join(_content_card(i, True) for i in d["top_full"]) or _empty("No full episodes published this period")
    top_clip = "".join(_content_card(i) for i in d["top_clip"]) or _empty("No clips published this period")
    top_short = "".join(_content_card(i) for i in d["top_short"]) or _empty("No Shorts published this period")
    top_social = "".join(_social_card(i) for i in d["top_social"]) or _empty("Top social posts not entered")

    foot = f'''
  <div class="foot">
    <span>The Schultz Report × Fanatics Sportsbook · Presenting Partnership</span>
    <span>Prepared by Rain Delay Media · Confidential</span>
    <span>Generated {_Mdy(d['generated'])}</span>
  </div>'''

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>The Schultz Report × Fanatics — {period_lbl}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600;700;800&family=Barlow:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --gold:{BLUE}; --yel:{YELLOW}; --ink:#1a1a1a; --mut:#8a8a8a; --line:#e6e6e6; }}
  * {{ box-sizing:border-box; }}
  body {{ font-family:'Barlow',sans-serif; color:var(--ink); margin:0; background:#f3f3f3; font-size:12px; }}
  .page {{ width:8.5in; min-height:11in; padding:0.5in 0.55in; margin:14px auto; background:#fff;
          box-shadow:0 2px 12px rgba(0,0,0,.12); }}
  h1,h2,h3,.cond {{ font-family:'Barlow Condensed',sans-serif; }}
  .eyebrow {{ font-family:'Barlow Condensed'; letter-spacing:.28em; font-weight:600; color:var(--mut); font-size:9px; text-transform:uppercase; }}

  /* header */
  .hdr {{ display:flex; justify-content:space-between; align-items:flex-start; background:var(--gold); color:#fff;
          margin:-0.5in -0.55in 0; padding:0.42in 0.55in 16px; border-bottom:5px solid var(--yel); }}
  .title {{ font-family:'Barlow Condensed'; font-weight:800; font-size:36px; line-height:.95; letter-spacing:-.01em; text-transform:uppercase; }}
  .title .x {{ color:var(--yel); }}
  .subt {{ letter-spacing:.22em; font-weight:600; color:#c9c9ef; font-size:9px; text-transform:uppercase; margin-top:6px; }}
  .hdr-r {{ text-align:right; }}
  .hdr-r .big {{ font-family:'Barlow Condensed'; font-weight:700; font-size:20px; }}
  .hdr-r .sm {{ color:#c9c9ef; font-size:10px; }}
  .hdr .eyebrow {{ color:var(--yel); }}

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
  .gold-box {{ border:1px solid var(--yel); background:#fffbe6; border-radius:3px; padding:3px 0; }}

  /* top content cards */
  .cc-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:10px 0 18px; }}
  .cc {{ border:1px solid var(--line); border-radius:3px; overflow:hidden; text-decoration:none; color:inherit; display:block; }}
  .cc-thumb {{ aspect-ratio:16/9; background:#222 center/cover no-repeat; }}
  .cc-body {{ padding:8px 10px 11px; }}
  .cc-rank {{ font-family:'Barlow Condensed'; font-weight:800; font-size:22px; display:flex; align-items:baseline; gap:8px; }}
  .cc-views {{ font-size:13px; color:var(--gold); }}
  .cc-meta {{ font-size:8px; letter-spacing:.12em; color:var(--mut); text-transform:uppercase; margin:2px 0 4px; }}
  .cc-title {{ font-weight:600; font-size:11px; line-height:1.25; }}
  .sc {{ border:1px solid var(--line); border-left:3px solid var(--yel); border-radius:3px; padding:9px 11px; }}
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

  /* SR additions */
  .kpi3 {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:0 0 16px; }}
  .k3 {{ border:1px solid var(--line); border-top:4px solid var(--yel); border-radius:3px; padding:10px 12px; }}
  .k3 .h {{ font-family:'Barlow Condensed'; font-weight:800; font-size:13px; line-height:1.15; min-height:30px; color:var(--gold); text-transform:uppercase; letter-spacing:.04em; }}
  .k3 .rowv {{ display:flex; justify-content:space-between; font-size:10px; padding:3px 0; border-top:1px dotted var(--line); }}
  .k3 .rowv:first-of-type {{ border-top:none; }}
  .k3 .rowv b {{ font-family:'Barlow Condensed'; font-size:14px; }}
  tr.grp td {{ font-size:8px; letter-spacing:.2em; color:var(--gold); font-weight:700; text-transform:uppercase; padding:10px 6px 4px; background:#f5f5fb; }}
  .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-top:12px; }}
  .tag {{ display:inline-block; font-size:7.5px; letter-spacing:.12em; font-weight:700; padding:1px 5px; border-radius:2px; margin-left:6px; vertical-align:middle; }}
  .tag.ok {{ background:#E8F5E9; color:#2E7D32; }}
  .tag.low {{ background:#FFF3E0; color:#B45309; }}
  .tag.na {{ background:#eee; color:#777; }}
  .marks {{ position:relative; height:12px; font-size:7px; color:var(--mut); margin-top:-4px; }}
  .marks span {{ position:absolute; transform:translateX(-50%); white-space:nowrap; }}
</style></head><body>

<!-- ══════════════ PAGE 1 · HEADLINE + PLATFORM DELIVERY ══════════════ -->
<section class="page">
  <div class="hdr">
    <div>
      <div class="title">THE SCHULTZ REPORT <span class="x">×</span><br>FANATICS SPORTSBOOK</div>
      <div class="subt">Presenting Partnership · Monthly Delivery Report</div>
    </div>
    <div class="hdr-r">
      <div class="eyebrow">Reporting Period</div>
      <div class="big">{period_lbl}</div>
      <div class="sm">Term: {term_lbl} · ~90–115 Episodes</div>
    </div>
  </div>

  <div class="cards">
    <div class="card"><div class="lbl">Cumulative Views &amp; Downloads</div><div class="val">{_fmt(d['cum_vd'])}</div><div class="note">All platforms · term to date</div></div>
    <div class="card"><div class="lbl">This Period Views &amp; Downloads</div><div class="val">{_fmt(d['tp_vd'])}</div><div class="note">{_md(d['start'])} – {_md(d['end'])} only</div></div>
    <div class="card"><div class="lbl">% of Term Elapsed</div><div class="val">{d['pct_elapsed']:.1f}%</div><div class="note">Of {d['term_days']}-day term</div></div>
    <div class="card"><div class="lbl">Days Into Partnership</div><div class="val">{d['days_into']}</div><div class="note">of {d['term_days']} days</div></div>
  </div>

  <div class="imp">
    <div>
      <div class="lbl">Impressions*</div>
      <div class="num">{_fmt(d['total_imp'])}</div>
      <div class="vs">vs. {_fmt(d['goal'])} minimum target</div>
    </div>
    <div class="pace">
      <b>{d['pct_plan']:.2f}%</b> of target delivered with {d['pct_elapsed']:.1f}% of the term elapsed<br>
      At the current rate: on pace for <b>~{_fmt(d['pace'])}</b> impressions over the term
    </div>
  </div>

  <div class="kpi3">
    {k3("YouTube", "youtube", "Views")}
    {k3("Social · Jordan &amp; Keyshawn", "social_talent", "Views")}
    {k3("Social · SR Show Accounts", "social_show", "Views")}
    {k3("Audio", "audio", "Downloads")}
  </div>

  <div class="sec-h"><h2>Platform Delivery</h2><div class="r">VIEWS &amp; DOWNLOADS · RAW COUNTS</div></div>
  <table>
    <thead><tr><td>Platform</td><td>Metric</td><td style="text-align:right">This Period</td><td style="text-align:right">Cumulative</td></tr></thead>
    <tbody>{platform_rows}</tbody>
  </table>
  {foot}
</section>

<!-- ══════════════ PAGE 2 · DELIVERY TRACKERS ══════════════ -->
<section class="page">
  <div class="sec-h"><h2>Delivery Tracker</h2><div class="r">TERM TO DATE VS. CONTRACT</div></div>

  <div class="grid2">
    <div class="kpi">
      <div class="kpi-h">Episode Delivery</div>
      <div class="big-row"><span class="big-num">{e['cum']}</span><span class="big-pct">{_pct(e['cum'], 90):.1f}%</span><span class="big-tgt">of 90 floor</span></div>
      <div class="micro">Regular episodes aired · floor 90 · cycle target ~100 · ceiling 115 incl. specials</div>
      {_bar(_pct(e['cum'] + e['special_cum'], 115), exceeded=e['cum'] >= 90)}
      <div class="marks"><span style="left:{floor_pos:.1f}%">90</span><span style="left:{tgt_pos:.1f}%">100</span><span style="left:99%">115</span></div>
      {ep_lines}
      {_line("Special / Tentpole (upside)", e['special_cum'], 25, e['special_tp'])}
      <div class="line"><span><b>Total aired</b></span><span class="v">{e['cum'] + e['special_cum']} <small>/ ~100</small></span></div>
    </div>

    <div class="kpi">
      <div class="kpi-h">Sponsorship Delivered</div>
      <div class="big-row"><span class="big-num">{_fmt(sponsor_total)}</span><span class="big-pct">{_pct(sponsor_total, sponsor_target):.1f}%</span><span class="big-tgt">~{sponsor_target}</span></div>
      <div class="micro">Per-episode sponsorship units · % of term target</div>
      {_bar(_pct(sponsor_total, sponsor_target))}
      {sponsor_lines}
      <div class="kpi-h" style="margin-top:14px">Branded Content &amp; Added Value</div>
      {content_lines}
    </div>
  </div>

  <div class="grid2">
    <div class="kpi">
      <div class="kpi-h">Reporter &amp; Talent Channels · Fanatics-Integrated Posts</div>
      {rep_html}
    </div>
    <div class="kpi">
      <div class="kpi-h">Marquee Moments &amp; Branded Content</div>
      {ev_lines}
      <div class="micro" style="margin-top:8px">Event content is counted once, in the platform it ran on.</div>
    </div>
  </div>
  {foot}
</section>

<!-- ══════════════ PAGE 3 · TOP CONTENT ══════════════ -->
<section class="page">
  <div class="sec-h"><h2>Top Content — {_md(d['start'])} – {_md(d['end'])}</h2><div class="r">RANKED BY VIEWS</div></div>
  <div class="eyebrow" style="margin:4px 0">Best-performing content published {_md(d['start'])} – {_md(d['end'])} · click any title to view</div>
  <div class="eyebrow" style="color:{BLUE};font-size:11px;margin-top:8px">★ Top 3 Full Episodes · YouTube</div>
  <div class="cc-grid">{top_full}</div>
  <div class="eyebrow" style="color:{BLUE};font-size:11px">★ Top 3 Segment Clips · YouTube</div>
  <div class="cc-grid">{top_clip}</div>
  <div class="eyebrow" style="color:{BLUE};font-size:11px">★ Top 3 Shorts · YouTube</div>
  <div class="cc-grid">{top_short}</div>
  {foot}
</section>

<!-- ══════════════ PAGE 4 · SOCIAL + METHODOLOGY ══════════════ -->
<section class="page">
  <div class="eyebrow" style="color:{BLUE};font-size:11px">★ Top 3 Social Posts</div>
  <div class="cc-grid">{top_social}</div>

  <div class="goal">
    <div class="goal-top">
      <div>
        <h2>*How Impressions Are Calculated</h2>
        <div class="desc">Each episode view counts once per sponsored element delivered inside it. Social and audio count one impression per view or download.</div>
      </div>
      <div class="tot"><div class="l">Impressions Total</div><div class="n">{_fmt(d['total_imp'])}</div>
        <div class="micro">{d['pct_plan']:.2f}% of {_fmt(d['goal'])}</div></div>
    </div>
    <div class="mults">
      <div class="mult">
        <h3>Jordan-Led &amp; Keyshawn Episodes <span class="x">6×</span></h3>
        <ul><li>✓ Top-of-Show Shoutout</li><li>✓ Sponsored Segment</li><li>✓ Video Host-Read Ad</li>
            <li>✓ Audio Ad Read</li><li>✓ Logo Watermark</li><li>✓ On-Set Branding</li></ul>
      </div>
      <div class="mult">
        <h3>Guest Episodes &amp; Specials <span class="x">5×</span></h3>
        <ul><li>✓ Top-of-Show Shoutout</li><li>✓ Video Host-Read Ad</li><li>✓ Audio Ad Read</li>
            <li>✓ Logo Watermark</li><li>✓ On-Set Branding</li></ul>
        <div class="calc">This period: <b>{d['blend']:.2f}×</b> blended across the episode mix</div>
      </div>
      <div class="mult">
        <h3>Clips &amp; Shorts <span class="x">2×</span></h3>
        <ul><li>✓ View</li><li>✓ Logo Watermark</li></ul>
        <div class="calc">Social posts &amp; podcast downloads: <b>1×</b></div>
      </div>
    </div>
    <div class="mults" style="grid-template-columns:repeat(4,1fr)">
      <div class="mult"><h3>YouTube</h3><div class="calc"><b>{_fmt(k['youtube']['cum_imp'])}</b> impressions</div></div>
      <div class="mult"><h3>Social · Jordan &amp; Keyshawn</h3><div class="calc"><b>{_fmt(k['social_talent']['cum_imp'])}</b> impressions</div></div>
      <div class="mult"><h3>Social · SR Show</h3><div class="calc"><b>{_fmt(k['social_show']['cum_imp'])}</b> impressions</div></div>
      <div class="mult"><h3>Audio</h3><div class="calc"><b>{_fmt(k['audio']['cum_imp'])}</b> impressions</div></div>
    </div>
    <div class="desc" style="max-width:none;margin-top:14px;font-size:9.5px;color:#555">
      <b style="color:{BLUE}">Social attribution:</b> every view is counted once. Instagram collab posts between @JordanSchultz and the
      Schultz Report account share a single view count, so each collab is counted once, under @JordanSchultz.
      TikTok and X posts on the two accounts are separate posts with separate views, so each account's views are counted.
      Reporter and talent figures include Fanatics-integrated posts only.
    </div>
  </div>
  {foot}
</section>
</body></html>'''