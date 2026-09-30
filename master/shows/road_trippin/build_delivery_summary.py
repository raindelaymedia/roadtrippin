"""
Road Trippin' × Fanatics — Delivery Summary 1-Pager
Time series charts for all contractual deliverables across reporting periods.
Reads from fanatics_history.csv.

Usage:
    cd master/shows/road_trippin
    python build_delivery_summary.py --data-dir data
"""

import csv, os, argparse, json
from datetime import datetime


def load_history(path):
    if not os.path.exists(path): return []
    with open(path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    # Sort by period start
    rows.sort(key=lambda r: r.get("period_start",""))
    return rows


def ti(r, k):
    """Safe int from CSV field that might be float string or empty."""
    v = r.get(k, 0) or 0
    try: return int(float(v))
    except: return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--output", default="delivery_summary.html")
    args = parser.parse_args()

    path = os.path.join(args.data_dir, "fanatics_history.csv")
    rows = load_history(path)
    if not rows:
        print(f"No data found at {path}")
        return

    print(f"Loaded {len(rows)} reporting periods")

    # Extract per-period data
    period_labels = []
    impressions = []
    yt_total = []
    ig_views = []
    tt_views = []
    fb_views = []
    x_imp = []
    mega_views = []
    group_eps = []
    solo_perk = []
    solo_chan = []
    total_eps = []
    shoutouts = []
    segments = []
    ad_reads = []
    total_integrations = []
    perk_posts = []
    chan_posts = []
    rj_posts = []
    allie_posts = []
    total_posts = []

    cum_imp = 0
    cum_eps = 0
    cum_int = 0
    cum_posts = 0
    cum_impressions = []
    cum_episodes = []
    cum_integrations = []
    cum_talent_posts = []

    for r in rows:
        start = r.get("period_start","")
        end = r.get("period_end","")
        try:
            s = datetime.strptime(start, "%Y-%m-%d").strftime("%b %d")
            e = datetime.strptime(end, "%Y-%m-%d").strftime("%b %d")
            label = f"{s}–{e}"
        except:
            label = f"{start}–{end}"
        period_labels.append(label)

        imp = ti(r, "impressions")
        impressions.append(imp)
        yt_total.append(ti(r, "yt_total_views"))
        ig_views.append(ti(r, "ig_views"))
        tt_views.append(ti(r, "tiktok_views"))
        fb_views.append(ti(r, "fb_views"))
        x_imp.append(ti(r, "x_imp"))
        mega_views.append(ti(r, "mega_views"))

        ge = ti(r, "group_eps"); sp = ti(r, "solo_perk"); sc = ti(r, "solo_chan")
        group_eps.append(ge); solo_perk.append(sp); solo_chan.append(sc)
        te = ge + sp + sc
        total_eps.append(te)

        sh = ti(r, "shoutouts"); sg = ti(r, "segments"); ar = ti(r, "ad_reads")
        shoutouts.append(sh); segments.append(sg); ad_reads.append(ar)
        ti_val = sh + sg + ar
        total_integrations.append(ti_val)

        pp = ti(r, "perk_posts"); cp = ti(r, "channing_posts")
        rp = ti(r, "rj_posts"); ap = ti(r, "allie_posts")
        perk_posts.append(pp); chan_posts.append(cp)
        rj_posts.append(rp); allie_posts.append(ap)
        tp = pp + cp + rp + ap
        total_posts.append(tp)

        cum_imp += imp; cum_eps += te; cum_int += ti_val; cum_posts += tp
        cum_impressions.append(cum_imp)
        cum_episodes.append(cum_eps)
        cum_integrations.append(cum_int)
        cum_talent_posts.append(cum_posts)

    # Totals
    final_imp = cum_imp
    final_eps = cum_eps
    final_int = cum_int
    final_posts = cum_posts
    imp_goal = 47_000_000
    imp_pct = final_imp / imp_goal * 100

    # ── Delivery by content type ─────────────────────────────────
    # Off-YouTube platforms and podcast count 1x, so their impressions are exact.
    # The YouTube share of each period's reported impressions is the remainder,
    # split across full episodes / clips / shorts by multiplier-weighted views
    # (full eps 6x group / 5x solo, clips & shorts 2x). This keeps every bucket
    # tied to the impressions already reported for that period.
    ct = {k: [] for k in ("full", "clip", "short", "pod", "ig", "tt", "fb", "x")}
    yt_full_v, yt_clip_v, yt_short_v = [], [], []
    for i, r in enumerate(rows):
        fv, cv, sv = ti(r, "yt_full_views"), ti(r, "yt_clip_views"), ti(r, "yt_short_views")
        yt_full_v.append(fv); yt_clip_v.append(cv); yt_short_v.append(sv)
        off = ig_views[i] + tt_views[i] + fb_views[i] + x_imp[i]
        yt_imp = impressions[i] - off - mega_views[i]
        solo = solo_perk[i] + solo_chan[i]
        n = group_eps[i] + solo
        blend = (group_eps[i] * 6 + solo * 5) / n if n else 6
        wf, wc, ws = fv * blend, cv * 2, sv * 2
        wt = wf + wc + ws
        f_imp = round(yt_imp * wf / wt) if wt else 0
        c_imp = round(yt_imp * wc / wt) if wt else 0
        ct["full"].append(f_imp); ct["clip"].append(c_imp)
        ct["short"].append(yt_imp - f_imp - c_imp)
        ct["pod"].append(mega_views[i]); ct["ig"].append(ig_views[i])
        ct["tt"].append(tt_views[i]); ct["fb"].append(fb_views[i]); ct["x"].append(x_imp[i])

    T = {k: sum(v) for k, v in ct.items()}
    show_imp = T["full"] + T["clip"] + T["short"] + T["pod"]
    social_imp = T["ig"] + T["tt"] + T["fb"] + T["x"]
    yt_imp_total = T["full"] + T["clip"] + T["short"]
    pct = lambda v: v / final_imp * 100
    gpct = lambda v: v / imp_goal * 100
    fm = lambda v: f"{v/1e6:.1f}M"

    split_segments = [
        ("Full episodes", T["full"], "#123E8C"),
        ("YouTube clips", T["clip"], "#2F6DDE"),
        ("YouTube Shorts", T["short"], "#8DB0EF"),
        ("Podcast", T["pod"], "#7C5BD8"),
        ("Instagram", T["ig"], "#C9A84C"),
        ("TikTok", T["tt"], "#DDBF73"),
        ("Facebook", T["fb"], "#E08C2A"),
        ("X", T["x"], "#EFB77A"),
    ]
    split_bar = "".join(
        f'<div class="seg" style="flex:{v};background:{c}" title="{name}: {v:,} ({pct(v):.1f}%)"></div>'
        for name, v, c in split_segments if v > 0)

    def legend_rows(items):
        out = ""
        for name, v, c in items:
            out += (f'<div class="lg-row"><span class="sw" style="background:{c}"></span>'
                    f'<span class="lg-name">{name}</span>'
                    f'<span class="lg-val">{fm(v)}</span>'
                    f'<span class="lg-pct">{pct(v):.1f}%</span></div>')
        return out
    show_legend = legend_rows(split_segments[:4])
    social_legend = legend_rows(split_segments[4:])

    # Build delivery table rows
    delivery_table_rows = ""
    cum_vd = 0
    for i in range(len(rows)):
        period_vd = yt_total[i] + ig_views[i] + tt_views[i] + fb_views[i] + x_imp[i] + mega_views[i]
        cum_vd += period_vd
        delivery_table_rows += f'''<tr>
          <td class="sticky">{period_labels[i]}</td>
          <td class="grp-start">{yt_full_v[i]:,}</td>
          <td>{yt_clip_v[i]:,}</td>
          <td>{yt_short_v[i]:,}</td>
          <td>{mega_views[i]:,}</td>
          <td class="grp-start">{ig_views[i]:,}</td>
          <td>{tt_views[i]:,}</td>
          <td>{fb_views[i]:,}</td>
          <td>{x_imp[i]:,}</td>
          <td class="grp-start"><b>{period_vd:,}</b></td>
          <td>{impressions[i]:,}</td>
          <td class="gold">{cum_impressions[i]:,}</td>
        </tr>'''

    jsa = lambda lst: json.dumps(lst)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Road Trippin' × Fanatics — Delivery Summary</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
@page{{size:letter landscape;margin:.4in}}
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{--bg:#fff;--s1:#f8f9fb;--bdr:#e5e7eb;--t:#0f1729;--t2:#4a5468;--t3:#8a93a6;--gold:#C9A84C;--blue:#2F6DDE;--teal:#1B9B96;--orange:#E08C2A;--pink:#E84B8A;--green:#1B7A3A;--purple:#7C5BD8}}
body{{font-family:'DM Sans',sans-serif;color:var(--t);background:var(--bg);padding:20px 28px;max-width:1100px;margin:0 auto}}

.header{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:2px solid var(--gold);padding-bottom:10px;margin-bottom:16px}}
.header h1{{font-size:16px;font-weight:800;letter-spacing:-.3px}}
.header .sub{{font-size:11px;color:var(--t2)}}

.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:18px}}
.kpi{{background:var(--s1);border:1px solid var(--bdr);border-radius:8px;padding:10px 12px;text-align:center}}
.kpi-val{{font-size:20px;font-weight:800;letter-spacing:-.3px}}
.kpi-lbl{{font-size:9px;color:var(--t3);text-transform:uppercase;letter-spacing:.06em;margin-top:2px}}
.kpi-sub{{font-size:10px;color:var(--gold);font-weight:600;margin-top:1px}}

.charts{{display:grid;grid-template-columns:1fr 1fr;gap:14px}}
.chart-box{{background:var(--s1);border:1px solid var(--bdr);border-radius:8px;padding:14px}}
.chart-label{{font-size:11px;font-weight:600;color:var(--t2);margin-bottom:8px;text-transform:uppercase;letter-spacing:.04em}}

.foot{{text-align:center;font-size:9px;color:var(--t3);margin-top:14px;padding-top:8px;border-top:1px solid var(--bdr)}}
.table-scroll{{overflow-x:auto;scrollbar-width:thin}}
.dtable{{border-collapse:collapse;font-size:10.5px;font-family:'DM Mono',monospace;white-space:nowrap;width:100%}}
.dtable th{{background:var(--s1);padding:6px 7px;text-align:right;font-size:9px;font-weight:600;color:var(--t2);text-transform:uppercase;letter-spacing:.04em;border-bottom:1.5px solid var(--bdr);font-family:'DM Sans',sans-serif}}
.dtable td{{padding:5px 7px;text-align:right;border-bottom:.5px solid var(--bdr)}}
.dtable th.sticky,.dtable td.sticky{{text-align:left;position:sticky;left:0;background:var(--bg);z-index:1;font-family:'DM Sans',sans-serif;font-weight:500;min-width:100px}}
.dtable tr:nth-child(even) td{{background:#fafbfc}}
.dtable tr:nth-child(even) td.sticky{{background:#fafbfc}}
.dtable .total-row td{{background:var(--s1)!important;border-top:1.5px solid var(--bdr);font-weight:600}}
.dtable .total-row td.sticky{{background:var(--s1)!important}}
.gold{{color:var(--gold);font-weight:700}}

.ct{{background:var(--s1);border:1px solid var(--bdr);border-radius:8px;padding:16px 18px;margin-bottom:14px}}
.ct-head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px}}
.ct-title{{font-size:13px;font-weight:700}}
.ct-note{{font-size:10px;color:var(--t3)}}
.split{{display:flex;height:26px;border-radius:5px;overflow:hidden;gap:1px;background:#fff}}
.seg{{min-width:2px}}
.split-marks{{display:flex;font-size:10px;font-weight:600;margin-top:5px}}
.split-marks .m-show{{color:#123E8C}}
.split-marks .m-social{{color:#A8791E;text-align:right}}
.ct-cols{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}}
.ct-col{{background:#fff;border:1px solid var(--bdr);border-radius:6px;padding:12px 14px}}
.ct-col.show{{border-top:3px solid #123E8C}}
.ct-col.social{{border-top:3px solid var(--gold)}}
.ct-big{{display:flex;align-items:baseline;gap:10px;margin-bottom:2px}}
.ct-big .v{{font-size:24px;font-weight:800;letter-spacing:-.5px}}
.ct-big .p{{font-size:12px;font-weight:600;color:var(--t2)}}
.ct-sub{{font-size:11px;color:var(--t2);margin-bottom:10px}}
.ct-sub b{{color:var(--green)}}
.lg-row{{display:grid;grid-template-columns:12px 1fr auto 48px;gap:8px;align-items:center;font-size:11px;padding:3px 0;border-top:.5px solid var(--bdr)}}
.lg-row:first-child{{border-top:none}}
.sw{{width:10px;height:10px;border-radius:2px}}
.lg-val{{font-family:'DM Mono',monospace;font-weight:500}}
.lg-pct{{font-family:'DM Mono',monospace;color:var(--t3);text-align:right}}
.dtable .grp-row th{{text-align:center;font-size:9px;border-bottom:none;padding-bottom:2px}}
.dtable th.grp-show{{color:#123E8C;border-bottom:2px solid #123E8C}}
.dtable th.grp-social{{color:#A8791E;border-bottom:2px solid var(--gold)}}
.dtable .grp-start{{border-left:1px solid var(--bdr)}}
</style>
</head>
<body>

<div class="header">
  <h1>Road Trippin' × Fanatics Sportsbook — Delivery Summary</h1>
  <div class="sub">Feb 17, 2026 – Sep 13, 2026 · {len(rows)} Reporting Periods</div>
</div>

<div class="kpis">
  <div class="kpi">
    <div class="kpi-val">{final_imp/1e6:.1f}M</div>
    <div class="kpi-lbl">Total Impressions</div>
    <div class="kpi-sub">{imp_pct:.0f}% of 47M goal</div>
  </div>
  <div class="kpi">
    <div class="kpi-val">{final_eps}</div>
    <div class="kpi-lbl">Episodes Aired</div>
    <div class="kpi-sub">of ~94 target</div>
  </div>
  <div class="kpi">
    <div class="kpi-val">{final_int}</div>
    <div class="kpi-lbl">Integrations</div>
    <div class="kpi-sub">shoutouts + segments + ad reads</div>
  </div>
  <div class="kpi">
    <div class="kpi-val">{final_posts}</div>
    <div class="kpi-lbl">Talent Social Posts</div>
    <div class="kpi-sub">of ~182 target</div>
  </div>
  <div class="kpi">
    <div class="kpi-val">{len(rows)}</div>
    <div class="kpi-lbl">Reports Delivered</div>
    <div class="kpi-sub">monthly cadence</div>
  </div>
</div>

<div class="ct">
  <div class="ct-head">
    <div class="ct-title">Where the {final_imp/1e6:.1f}M impressions came from</div>
    <div class="ct-note">Share of total contracted impressions</div>
  </div>
  <div class="split">{split_bar}</div>
  <div class="split-marks">
    <div class="m-show" style="flex:{show_imp}">The show · {pct(show_imp):.0f}%</div>
    <div class="m-social" style="flex:{social_imp}">Off-YouTube social · {pct(social_imp):.0f}%</div>
  </div>
  <div class="ct-cols">
    <div class="ct-col show">
      <div class="ct-big"><span class="v">{fm(show_imp)}</span><span class="p">{gpct(show_imp):.0f}% of the 47M goal</span></div>
      <div class="ct-sub">The show: full episodes, clips and Shorts on YouTube, plus the podcast. <b>Clears the goal on its own.</b></div>
      {show_legend}
    </div>
    <div class="ct-col social">
      <div class="ct-big"><span class="v">{fm(social_imp)}</span><span class="p">{gpct(social_imp):.0f}% of the 47M goal</span></div>
      <div class="ct-sub">Promo clips posted to Instagram, TikTok, Facebook and X.</div>
      {social_legend}
    </div>
  </div>
</div>

<div class="charts" style="margin-bottom:14px">
  <div class="chart-box" style="grid-column:span 2">
    <div class="chart-label">Impressions per Period by Content Type</div>
    <div style="height:210px"><canvas id="c-ct"></canvas></div>
  </div>
</div>

<div class="charts">
  <div class="chart-box" style="grid-column:span 2">
    <div class="chart-label">Period-by-Period Views & Downloads by Content Type</div>
    <div class="table-scroll"><table class="dtable">
      <thead><tr class="grp-row">
        <th class="sticky"></th>
        <th colspan="4" class="grp grp-show">The show: YouTube + podcast</th>
        <th colspan="4" class="grp grp-social">Off-YouTube social</th>
        <th colspan="3" class="grp">Totals</th>
      </tr><tr>
        <th class="sticky">Period</th>
        <th class="grp-start">Full eps</th>
        <th>Clips</th>
        <th>Shorts</th>
        <th>Podcast</th>
        <th class="grp-start">Instagram</th>
        <th>TikTok</th>
        <th>Facebook</th>
        <th>X</th>
        <th class="grp-start">Period V&D</th>
        <th>Impressions</th>
        <th>Cum. Impressions</th>
      </tr></thead>
      <tbody>
      {delivery_table_rows}
      </tbody>
      <tfoot><tr class="total-row">
        <td class="sticky"><b>TOTAL</b></td>
        <td class="grp-start">{sum(yt_full_v):,}</td>
        <td>{sum(yt_clip_v):,}</td>
        <td>{sum(yt_short_v):,}</td>
        <td>{sum(mega_views):,}</td>
        <td class="grp-start">{sum(ig_views):,}</td>
        <td>{sum(tt_views):,}</td>
        <td>{sum(fb_views):,}</td>
        <td>{sum(x_imp):,}</td>
        <td class="grp-start"><b>{sum(yt_total)+sum(ig_views)+sum(tt_views)+sum(fb_views)+sum(x_imp)+sum(mega_views):,}</b></td>
        <td><b>{final_imp:,}</b></td>
        <td class="gold"><b>{imp_pct:.0f}% of 47M</b></td>
      </tr></tfoot>
    </table></div>
  </div>
</div>

<div class="charts" style="margin-top:14px">
  <div class="chart-box">
    <div class="chart-label">Impressions per Period (cumulative line)</div>
    <div style="height:180px"><canvas id="c-imp"></canvas></div>
  </div>
  <div class="chart-box">
    <div class="chart-label">Episodes per Period (group / solo)</div>
    <div style="height:180px"><canvas id="c-eps"></canvas></div>
  </div>
  <div class="chart-box">
    <div class="chart-label">Integrations per Period</div>
    <div style="height:180px"><canvas id="c-int"></canvas></div>
  </div>
  <div class="chart-box">
    <div class="chart-label">Talent Posts per Period</div>
    <div style="height:180px"><canvas id="c-posts"></canvas></div>
  </div>
</div>

<div class="foot" style="text-align:left;border-top:none;margin-top:10px;padding-top:0">
  Impressions: podcast and off-YouTube platforms count 1x. YouTube impressions per period are split across full episodes (6x group, 5x solo; live streams are included in the full-episode playlist), clips and Shorts (2x) by weighted views, and tie to each period's reported total.
</div>
<div class="foot">
  Road Trippin' × Fanatics Sportsbook · Presenting Partnership · Rain Delay Media · Confidential · Generated {datetime.now().strftime("%B %d, %Y")}
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const L={jsa(period_labels)};
const tc='#8a93a6',gc='#f0f1f3';
const fK=v=>v>=1e6?(v/1e6).toFixed(0)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v;

// Impressions by content type: YouTube + podcast (blues/purple) vs off-YouTube social (golds)
new Chart(document.getElementById('c-ct'),{{
  type:'bar',
  data:{{labels:L,datasets:[
    {{label:'Full episodes',data:{jsa(ct["full"])},backgroundColor:'#123E8C',stack:'s'}},
    {{label:'YouTube clips',data:{jsa(ct["clip"])},backgroundColor:'#2F6DDE',stack:'s'}},
    {{label:'YouTube Shorts',data:{jsa(ct["short"])},backgroundColor:'#8DB0EF',stack:'s'}},
    {{label:'Podcast',data:{jsa(ct["pod"])},backgroundColor:'#7C5BD8',stack:'s'}},
    {{label:'Instagram',data:{jsa(ct["ig"])},backgroundColor:'#C9A84C',stack:'s'}},
    {{label:'TikTok',data:{jsa(ct["tt"])},backgroundColor:'#DDBF73',stack:'s'}},
    {{label:'Facebook',data:{jsa(ct["fb"])},backgroundColor:'#E08C2A',stack:'s'}},
    {{label:'X',data:{jsa(ct["x"])},backgroundColor:'#EFB77A',stack:'s'}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'right',labels:{{boxWidth:10,font:{{size:10}}}}}},
      tooltip:{{callbacks:{{label:c=>c.dataset.label+': '+c.parsed.y.toLocaleString()}}}}}},
    scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{color:tc,font:{{size:8}},maxRotation:45}}}},
      y:{{stacked:true,grid:{{color:gc}},ticks:{{color:tc,callback:fK}}}}}}
  }}
}});

// Impressions: bar per period + cumulative line
new Chart(document.getElementById('c-imp'),{{
  type:'bar',
  data:{{labels:L,datasets:[
    {{label:'Period',data:{jsa(impressions)},backgroundColor:'#2F6DDE',borderRadius:3,order:2}},
    {{label:'Cumulative',data:{jsa(cum_impressions)},type:'line',borderColor:'#C9A84C',backgroundColor:'transparent',tension:.3,pointRadius:3,borderWidth:2,order:1}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}}}}}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{color:tc,font:{{size:8}},maxRotation:45}}}},
      y:{{grid:{{color:gc}},ticks:{{color:tc,callback:fK}}}}}}
  }}
}});

// Episodes: stacked bar (group, solo perk, solo chan)
new Chart(document.getElementById('c-eps'),{{
  type:'bar',
  data:{{labels:L,datasets:[
    {{label:'Group',data:{jsa(group_eps)},backgroundColor:'#2F6DDE',borderRadius:2,stack:'s'}},
    {{label:'Solo Perk',data:{jsa(solo_perk)},backgroundColor:'#E08C2A',borderRadius:2,stack:'s'}},
    {{label:'Solo Chan',data:{jsa(solo_chan)},backgroundColor:'#1B9B96',borderRadius:2,stack:'s'}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}}}}}}}},
    scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{color:tc,font:{{size:8}},maxRotation:45}}}},
      y:{{stacked:true,grid:{{color:gc}},ticks:{{color:tc}}}}}}
  }}
}});

// Integrations: stacked bar (shoutouts, segments, ad reads)
new Chart(document.getElementById('c-int'),{{
  type:'bar',
  data:{{labels:L,datasets:[
    {{label:'Shoutouts',data:{jsa(shoutouts)},backgroundColor:'#7C5BD8',borderRadius:2,stack:'s'}},
    {{label:'Segments',data:{jsa(segments)},backgroundColor:'#E84B8A',borderRadius:2,stack:'s'}},
    {{label:'Ad Reads',data:{jsa(ad_reads)},backgroundColor:'#C9A84C',borderRadius:2,stack:'s'}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}}}}}}}},
    scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{color:tc,font:{{size:8}},maxRotation:45}}}},
      y:{{stacked:true,grid:{{color:gc}},ticks:{{color:tc}}}}}}
  }}
}});

// Talent posts: stacked bar by talent
new Chart(document.getElementById('c-posts'),{{
  type:'bar',
  data:{{labels:L,datasets:[
    {{label:'Perk',data:{jsa(perk_posts)},backgroundColor:'#2F6DDE',borderRadius:2,stack:'s'}},
    {{label:'Channing',data:{jsa(chan_posts)},backgroundColor:'#1B9B96',borderRadius:2,stack:'s'}},
    {{label:'RJ',data:{jsa(rj_posts)},backgroundColor:'#E08C2A',borderRadius:2,stack:'s'}},
    {{label:'Allie',data:{jsa(allie_posts)},backgroundColor:'#E84B8A',borderRadius:2,stack:'s'}}
  ]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:'bottom',labels:{{boxWidth:10,font:{{size:10}}}}}}}},
    scales:{{x:{{stacked:true,grid:{{display:false}},ticks:{{color:tc,font:{{size:8}},maxRotation:45}}}},
      y:{{stacked:true,grid:{{color:gc}},ticks:{{color:tc}}}}}}
  }}
}});
</script>
</body>
</html>'''

    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ Saved: {args.output} ({os.path.getsize(args.output)/1024:.0f} KB)")


if __name__ == "__main__":
    main()