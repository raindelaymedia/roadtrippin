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

    # Build delivery table rows
    delivery_table_rows = ""
    cum_vd = 0
    for i in range(len(rows)):
        period_vd = yt_total[i] + ig_views[i] + tt_views[i] + fb_views[i] + x_imp[i] + mega_views[i]
        cum_vd += period_vd
        delivery_table_rows += f'''<tr>
          <td class="sticky">{period_labels[i]}</td>
          <td>{yt_total[i]:,}</td>
          <td>{ig_views[i]:,}</td>
          <td>{tt_views[i]:,}</td>
          <td>{fb_views[i]:,}</td>
          <td>{x_imp[i]:,}</td>
          <td>{mega_views[i]:,}</td>
          <td><b>{period_vd:,}</b></td>
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
.dtable{{border-collapse:collapse;font-size:11px;font-family:'DM Mono',monospace;white-space:nowrap;width:100%}}
.dtable th{{background:var(--s1);padding:6px 10px;text-align:right;font-size:9px;font-weight:600;color:var(--t2);text-transform:uppercase;letter-spacing:.04em;border-bottom:1.5px solid var(--bdr);font-family:'DM Sans',sans-serif}}
.dtable td{{padding:5px 10px;text-align:right;border-bottom:.5px solid var(--bdr)}}
.dtable th.sticky,.dtable td.sticky{{text-align:left;position:sticky;left:0;background:var(--bg);z-index:1;font-family:'DM Sans',sans-serif;font-weight:500;min-width:110px}}
.dtable tr:nth-child(even) td{{background:#fafbfc}}
.dtable tr:nth-child(even) td.sticky{{background:#fafbfc}}
.dtable .total-row td{{background:var(--s1)!important;border-top:1.5px solid var(--bdr);font-weight:600}}
.dtable .total-row td.sticky{{background:var(--s1)!important}}
.gold{{color:var(--gold);font-weight:700}}
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

<div class="charts">
  <div class="chart-box" style="grid-column:span 2">
    <div class="chart-label">Period-by-Period Delivery Breakdown</div>
    <div class="table-scroll"><table class="dtable">
      <thead><tr>
        <th class="sticky">Period</th>
        <th>YouTube</th>
        <th>Instagram</th>
        <th>TikTok</th>
        <th>Facebook</th>
        <th>X</th>
        <th>Podcast</th>
        <th>Period V&D</th>
        <th>Impressions</th>
        <th>Cum. Impressions</th>
      </tr></thead>
      <tbody>
      {delivery_table_rows}
      </tbody>
      <tfoot><tr class="total-row">
        <td class="sticky"><b>TOTAL</b></td>
        <td>{sum(yt_total):,}</td>
        <td>{sum(ig_views):,}</td>
        <td>{sum(tt_views):,}</td>
        <td>{sum(fb_views):,}</td>
        <td>{sum(x_imp):,}</td>
        <td>{sum(mega_views):,}</td>
        <td><b>{sum(yt_total)+sum(ig_views)+sum(tt_views)+sum(fb_views)+sum(x_imp)+sum(mega_views):,}</b></td>
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

<div class="foot">
  Road Trippin' × Fanatics Sportsbook · Presenting Partnership · Rain Delay Media · Confidential · Generated {datetime.now().strftime("%B %d, %Y")}
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const L={jsa(period_labels)};
const tc='#8a93a6',gc='#f0f1f3';
const fK=v=>v>=1e6?(v/1e6).toFixed(0)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v;

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