"""
Point of Attack — Dashboard Generator
Reads tracker_data_poa.json, revenue_poa.csv, and socials_poa.csv and generates
a standalone HTML dashboard. Mirrors Road Trippin's architecture with graceful
degradation when data sources are missing or empty.

Usage:
    python build_poa_dashboard.py
    python build_poa_dashboard.py --output point_of_attack.html
"""

import argparse
import json
import os
from datetime import datetime


# ─── Data loaders (same contract as RT) ──────────────────────────

def extract(path):
    """Load tracker_data_poa.json → dict matching the dashboard schema.
    Returns an empty-but-valid structure if the file has no month data."""
    with open(path, encoding='utf-8') as f:
        j = json.load(f)

    months = j.get('months', [])
    if not months:
        return _empty_extract()

    def series(keys, default=None):
        src = j
        for k in keys:
            src = src.get(k, {})
        if isinstance(src, dict):
            return [src.get(m, default) for m in months]
        return [default] * len(months)

    current_subs = j.get('current_subs', 0)
    subs_gained = series(['yt', 'subs_gained'], 0)
    subs_lost   = series(['yt', 'subs_lost'],   0)
    yt_subs = [None] * len(months)
    running = current_subs
    for i in range(len(months)):
        yt_subs[i] = running
        running -= ((subs_gained[i] or 0) - (subs_lost[i] or 0))

    downloads  = series(['audio', 'downloads'])
    eps_counts = series(['audio', 'episodes'])
    l_perep = []
    for dl, ep in zip(downloads, eps_counts):
        if dl and ep and ep > 0:
            l_perep.append(round(dl / ep))
        else:
            l_perep.append(None)

    vids_s   = series(['yt', 'vids'],   0)
    shorts_s = series(['yt', 'shorts'], 0)
    lives_s  = series(['yt', 'lives'],  0)
    pct_sht  = []
    for v, s, l in zip(vids_s, shorts_s, lives_s):
        total = (v or 0) + (s or 0) + (l or 0)
        pct_sht.append(round(s / total, 4) if total > 0 and s else None)

    best_of_raw = j.get('best_of', {})
    best_of = {
        'long':  [{**v, 'rank': str(i+1)} for i, v in enumerate(best_of_raw.get('long',  []))],
        'mid':   [{**v, 'rank': str(i+1)} for i, v in enumerate(best_of_raw.get('mid',   []))],
        'short': [{**v, 'rank': str(i+1)} for i, v in enumerate(best_of_raw.get('short', []))],
    }

    return {
        'months':       months,
        'eps':          eps_counts,
        'vids':         vids_s,
        'shorts':       shorts_s,
        'lives':        lives_s,
        'spotify':      series(['audio', 'streams']),
        'l_eps':        eps_counts,
        'l_perep':      l_perep,
        'l_total':      downloads,
        'yt_subs':      yt_subs,
        'ctr_vid':      series(['kpis', 'ctr']),
        'n_sht':        series(['kpis', 'shorts_count']),
        'pct_sht':      pct_sht,
        'srch_pct':     series(['kpis', 'search_pct']),
        'best_of':      best_of,
        'best_of_label': best_of_raw.get('label', ''),
        'top_content_monthly': j.get('top_content_monthly', {}),
        'all_videos':   j.get('all_videos', []),
        'subs_gained':  subs_gained,
        'subs_lost':    subs_lost,
        'current_subs': current_subs,
        'daily_yt':     j.get('daily_yt', {}),
        'audience_eps':  series(['audience', 'eps']),
        'audience_vods': series(['audience', 'vods']),
        'audience_lives': series(['audience', 'lives']),
    }


def _empty_extract():
    """Return a valid but empty data dict when no tracker data exists."""
    return {
        'months': [], 'eps': [], 'vids': [], 'shorts': [], 'lives': [],
        'spotify': [], 'l_eps': [], 'l_perep': [], 'l_total': [],
        'yt_subs': [], 'ctr_vid': [], 'n_sht': [], 'pct_sht': [],
        'srch_pct': [], 'best_of': {'long': [], 'mid': [], 'short': []},
        'best_of_label': '', 'top_content_monthly': {}, 'all_videos': [],
        'subs_gained': [], 'subs_lost': [], 'current_subs': 0,
        'daily_yt': {}, 'audience_eps': [], 'audience_vods': [],
        'audience_lives': [],
    }


def load_socials(csv_path):
    """Load flat socials CSV → {months, platforms, data}."""
    import csv as _csv
    if not os.path.exists(csv_path):
        return {'months': [], 'platforms': [], 'data': {}}

    PLATFORM_ORDER = ['INSTAGRAM', 'TIKTOK', 'X', 'YOUTUBE', 'FACEBOOK']
    raw, platforms_found = {}, set()

    with open(csv_path, encoding='utf-8') as f:
        for r in _csv.DictReader(f):
            period = r['period'].strip()
            platform = r['platform'].strip().upper()
            metric = r['metric'].strip().upper()
            try:
                val = float(r['value'].strip())
            except ValueError:
                val = r['value'].strip()
            raw.setdefault(period, {})[(platform, metric)] = val
            platforms_found.add(platform)

    months = sorted(raw.keys())
    platforms = [p for p in PLATFORM_ORDER if p in platforms_found]
    platforms += [p for p in sorted(platforms_found) if p not in PLATFORM_ORDER]

    all_keys = set()
    for pd in raw.values():
        all_keys.update(pd.keys())

    data = {k: [raw.get(m, {}).get(k) for m in months] for k in all_keys}
    return {'months': months, 'platforms': platforms, 'data': data}


def load_revenue(csv_path):
    """Load flat revenue CSV → {months, sources, totals, order}."""
    import csv as _csv
    if not os.path.exists(csv_path):
        return {'months': [], 'sources': {}, 'totals': [], 'order': []}

    raw = {}
    with open(csv_path, encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            period = r["period"].strip()
            source = r["source"].strip()
            amt_raw = r["amount"].strip()
            try:
                amt = float(amt_raw)
            except ValueError:
                amt = amt_raw
            raw.setdefault(period, {})[source] = amt

    months = sorted(raw.keys())
    if not months:
        return {'months': [], 'sources': {}, 'totals': [], 'order': []}

    present = set()
    for m in months:
        present.update(raw[m].keys())
    order = sorted(present)

    sources = {src: [raw[m].get(src) for m in months] for src in order}
    totals = []
    for m in months:
        t = sum(v for v in raw[m].values() if isinstance(v, (int, float)))
        totals.append(t if t > 0 else None)

    return {'months': months, 'sources': sources, 'totals': totals, 'order': order}


# ─── Formatting helpers ──────────────────────────────────────────

def fmt(v, pct=False):
    if v is None: return '—'
    if pct: return f'{v*100:.1f}%'
    if isinstance(v, (int, float)):
        if v >= 1_000_000: return f'{v/1_000_000:.2f}M'
        if v >= 1_000: return f'{v/1_000:.1f}K'
        return f'{int(v):,}'
    return str(v)


def fmt_period(p):
    try:
        dt = datetime.strptime(p, "%Y-%m")
        now = datetime.now()
        if dt.year == now.year:
            return dt.strftime("%b").upper()
        return dt.strftime("%b").upper() + " " + str(dt.year)[-2:]
    except:
        return p


def jsa(lst):
    def jv(v):
        if v is None: return 'null'
        if isinstance(v, bool): return 'true' if v else 'false'
        if isinstance(v, str): return json.dumps(v)
        return str(v)
    return '[' + ','.join(jv(v) for v in lst) + ']'


# ─── Empty-state block ───────────────────────────────────────────

def empty_state(message, sub=""):
    """Standard empty-state block used across tabs when no data is available."""
    sub_html = f'<div class="empty-sub">{sub}</div>' if sub else ''
    return (f'<div class="empty-state">'
            f'<div class="empty-icon">📭</div>'
            f'<div class="empty-msg">{message}</div>'
            f'{sub_html}</div>')


# ─── HTML builder ────────────────────────────────────────────────

def build_html(d, revenue, socials, generated_at):
    has_yt   = bool(d['months'])
    has_rev  = bool(revenue.get('months'))
    has_soc  = bool(socials.get('months'))
    has_data = has_yt or has_rev or has_soc

    # ── Overview metrics ──
    yt_subs_now = d['current_subs'] or 0

    if has_yt:
        M_raw = d['months']
        M_display = [fmt_period(m) for m in M_raw]
        M = list(reversed(M_display))
        latest_mo = M[-1] if M else '—'
        overview_sub = f"All platforms · {M[0]} – {latest_mo}" if M else "No data yet"
    else:
        M, M_display, latest_mo = [], [], '—'
        overview_sub = "No data connected yet — metrics will appear here once data pipelines are live"

    # ── Overview tab content ──
    if has_data:
        overview_metrics = f"""
    <div class="metrics">
      <div class="metric">
        <div class="metric-label">YT Subscribers</div>
        <div class="metric-value">{fmt(yt_subs_now) if yt_subs_now else '—'}</div>
        <div class="metric-delta" style="color:var(--text2)">{'live count' if yt_subs_now else 'not connected'}</div>
      </div>
      <div class="metric">
        <div class="metric-label">YT Views</div>
        <div class="metric-value">{fmt(sum(filter(None, [
            d['vids'][-1] if d['vids'] else None,
            d['shorts'][-1] if d['shorts'] else None,
            d['lives'][-1] if d['lives'] else None]))) if has_yt else '—'}</div>
        <div class="metric-delta" style="color:var(--text2)">{'latest month' if has_yt else 'not connected'}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Revenue</div>
        <div class="metric-value">{('$' + fmt(revenue['totals'][-1])) if has_rev and revenue['totals'][-1] else '—'}</div>
        <div class="metric-delta" style="color:var(--text2)">{'latest month' if has_rev else 'not connected'}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Social Platforms</div>
        <div class="metric-value">{len(socials.get('platforms', [])) or '—'}</div>
        <div class="metric-delta" style="color:var(--text2)">{'tracked' if has_soc else 'not connected'}</div>
      </div>
    </div>"""
    else:
        overview_metrics = f"""
    <div class="metrics">
      <div class="metric"><div class="metric-label">YT Subscribers</div><div class="metric-value">—</div><div class="metric-delta" style="color:var(--text2)">not connected</div></div>
      <div class="metric"><div class="metric-label">YT Views</div><div class="metric-value">—</div><div class="metric-delta" style="color:var(--text2)">not connected</div></div>
      <div class="metric"><div class="metric-label">Revenue</div><div class="metric-value">—</div><div class="metric-delta" style="color:var(--text2)">not connected</div></div>
      <div class="metric"><div class="metric-label">Social Platforms</div><div class="metric-value">—</div><div class="metric-delta" style="color:var(--text2)">not connected</div></div>
    </div>"""

    # ── YouTube tab ──
    if has_yt:
        vids_full   = list(reversed(d['vids']))
        shorts_full = list(reversed(d['shorts']))
        lives_full  = list(reversed(d['lives']))
        subs_full   = list(reversed(d['yt_subs']))
        chart_px = max(len(M) * 46, 500)
        js_M = jsa(M)
        js_vids = jsa(vids_full)
        js_shorts = jsa(shorts_full)
        js_lives = jsa(lives_full)
        js_subs = jsa(subs_full)
        yt_content = f"""
    <div class="metrics">
      <div class="metric"><div class="metric-label">Subscribers</div><div class="metric-value">{fmt(yt_subs_now)}</div></div>
      <div class="metric"><div class="metric-label">VOD Views ({latest_mo})</div><div class="metric-value">{fmt(d['vids'][0] if d['vids'] else None)}</div></div>
      <div class="metric"><div class="metric-label">Shorts Views ({latest_mo})</div><div class="metric-value">{fmt(d['shorts'][0] if d['shorts'] else None)}</div></div>
      <div class="metric"><div class="metric-label">Live Views ({latest_mo})</div><div class="metric-value">{fmt(d['lives'][0] if d['lives'] else None)}</div></div>
    </div>
    <div class="card">
      <div class="card-title">Views by Content Type</div>
      <div style="height:320px"><canvas id="yt-views-chart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Subscriber Growth</div>
      <div style="height:280px"><canvas id="yt-subs-chart"></canvas></div>
    </div>"""
    else:
        js_M = '[]'; js_vids = '[]'; js_shorts = '[]'; js_lives = '[]'; js_subs = '[]'
        chart_px = 500
        yt_content = empty_state(
            "YouTube Analytics not connected yet",
            "Once the YT API credentials are added to config, data will populate automatically.")

    # ── Revenue tab ──
    if has_rev:
        rev_M = [fmt_period(p) for p in revenue['months']]
        rev_totals = revenue['totals']
        js_rev_m = jsa(rev_M)
        js_rev_totals = jsa([round(t, 2) if t else None for t in rev_totals])
        rev_latest = rev_totals[-1] if rev_totals else 0
        rev_12mo = sum(t for t in rev_totals[-12:] if t)
        revenue_content = f"""
    <div class="metrics">
      <div class="metric"><div class="metric-label">Latest ({rev_M[-1]})</div><div class="metric-value">${rev_latest:,.0f}</div></div>
      <div class="metric"><div class="metric-label">12-mo Total</div><div class="metric-value">${rev_12mo:,.0f}</div></div>
      <div class="metric"><div class="metric-label">Months Tracked</div><div class="metric-value">{len(revenue['months'])}</div></div>
    </div>
    <div class="card">
      <div class="card-title">Monthly Revenue</div>
      <div style="height:320px"><canvas id="rev-chart"></canvas></div>
    </div>"""
    else:
        js_rev_m = '[]'; js_rev_totals = '[]'
        revenue_content = empty_state(
            "No revenue data yet",
            "Add rows to revenue_poa.csv to start tracking. Format: period,source,amount")

    # ── Socials tab ──
    if has_soc:
        soc_platforms = socials['platforms']
        PLATFORM_COLORS = {
            'INSTAGRAM': '#E08C2A', 'TIKTOK': '#7C5BD8', 'X': '#6B7280',
            'YOUTUBE': '#2F6DDE', 'FACEBOOK': '#1877F2',
        }
        PLATFORM_DISPLAY = {
            'INSTAGRAM': 'Instagram', 'TIKTOK': 'TikTok', 'X': 'X / Twitter',
            'YOUTUBE': 'YouTube', 'FACEBOOK': 'Facebook',
        }

        def soc_latest_for(plat, metric):
            series = socials['data'].get((plat, metric), [])
            for v in reversed(series):
                if isinstance(v, (int, float)) and v > 0: return v
            return None

        platform_cards = ''
        for p in soc_platforms:
            color = PLATFORM_COLORS.get(p, '#6B7280')
            display = PLATFORM_DISPLAY.get(p, p.title())
            followers = soc_latest_for(p, 'FOLLOWERS')
            views = soc_latest_for(p, 'VIEWS')
            eng = soc_latest_for(p, 'ENGAGEMENTS')
            platform_cards += (
                f'<div class="card soc-card">'
                f'<div class="soc-card-head" style="border-color:{color}">'
                f'<span class="soc-name">{display}</span>'
                f'<span class="soc-followers">{fmt(followers)}</span></div>'
                f'<div class="soc-stats">'
                f'<div><div class="soc-stat-lbl">Views</div><div class="soc-stat-val">{fmt(views)}</div></div>'
                f'<div><div class="soc-stat-lbl">Engagements</div><div class="soc-stat-val">{fmt(eng)}</div></div>'
                f'</div></div>')

        socials_content = f"""
    <div class="soc-grid">{platform_cards}</div>"""
    else:
        socials_content = empty_state(
            "No socials data yet",
            "Add rows to socials_poa.csv to start tracking. Format: period,platform,metric,value")

    # ── Tracker tab ──
    if has_yt:
        tracker_content = _tracker_tables(d, M_display)
    else:
        tracker_content = empty_state(
            "Tracker data will appear here once YouTube + Megaphone pipelines are connected")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Point of Attack — Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ─────────────────────────────────────────────────────────────
   POINT OF ATTACK DASHBOARD — Rain Delay Media
   Brand color: #3AA88C (gold)
   ───────────────────────────────────────────────────────────── */
:root{{
  --brand:        #3AA88C;
  --brand-deep:   #2D8A72;
  --brand-soft:   rgba(58,168,140,.08);
  --brand-tint:   rgba(58,168,140,.16);
  --bg:           #f7f8fb;
  --surface:      #ffffff;
  --surface2:     #eef1f7;
  --surface3:     #dde3ee;
  --border:       rgba(20,30,55,.08);
  --border2:      rgba(20,30,55,.16);
  --text:         #0f1729;
  --text2:        #4a5468;
  --text3:        #8a93a6;
  --green:        #1B7A3A;
  --red:          #BC2E3A;
  --r:            10px;
  --rsm:          6px;
  --shadow:       0 1px 3px rgba(15,23,41,.06), 0 1px 2px rgba(15,23,41,.04);
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px}}

.shell{{display:flex;height:100vh;overflow:hidden}}

/* ── Sidebar ── */
.sidebar{{
  width:212px; min-width:212px;
  background:var(--surface);
  border-right:1px solid var(--border);
  display:flex; flex-direction:column;
}}
.sidebar-logo{{
  padding:18px; border-bottom:1px solid var(--border);
  display:flex; align-items:center; gap:10px;
}}
.logo-mark{{
  width:32px; height:32px; flex-shrink:0;
  background:var(--brand); border-radius:7px;
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:700; font-size:11px;
  box-shadow:0 2px 4px rgba(58,168,140,.25);
}}
.logo-text{{display:flex;flex-direction:column;line-height:1.15}}
.logo-main{{font-size:14px;font-weight:600;letter-spacing:-.3px;color:var(--text)}}
.logo-sub{{font-size:11px;color:var(--text3);margin-top:1px}}
.nav{{padding:14px 10px 10px;flex:1}}
.nav-section{{font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);padding:8px 12px 6px;font-weight:600}}
.nav-item{{
  display:flex; align-items:center; gap:10px;
  padding:8px 11px; border-radius:var(--rsm);
  cursor:pointer; font-size:13px; color:var(--text2);
  margin-bottom:1px; user-select:none;
  transition:background .12s, color .12s;
  position:relative;
}}
.nav-item:hover{{background:var(--surface2);color:var(--text)}}
.nav-item.active{{background:var(--brand-soft);color:var(--brand);font-weight:500}}
.nav-item.active::before{{
  content:''; position:absolute; left:-10px; top:6px; bottom:6px;
  width:3px; background:var(--brand); border-radius:0 2px 2px 0;
}}
.nav-icon{{width:15px;height:15px;opacity:.55;flex-shrink:0}}
.nav-item.active .nav-icon{{opacity:1;color:var(--brand)}}
.sidebar-footer{{
  padding:14px 18px; border-top:1px solid var(--border);
  font-size:11px; color:var(--text3);
}}

/* ── Main content ── */
.main{{flex:1;overflow-y:auto;padding:28px 36px 60px}}
.page{{display:none}}
.page.active{{display:block}}
.page-header{{margin-bottom:24px}}
.page-title{{font-size:22px;font-weight:600;letter-spacing:-.4px}}
.page-sub{{font-size:13px;color:var(--text3);margin-top:4px}}

/* ── Metric cards ── */
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:24px}}
.metric{{
  background:var(--surface); border:1px solid var(--border);
  border-radius:var(--r); padding:16px 18px; box-shadow:var(--shadow);
}}
.metric-label{{font-size:11px;color:var(--text2);font-weight:500;text-transform:uppercase;letter-spacing:.04em}}
.metric-value{{font-size:24px;font-weight:600;letter-spacing:-.4px;margin:6px 0 2px}}
.metric-delta{{font-size:12px;color:var(--text3)}}

/* ── Cards ── */
.card{{
  background:var(--surface); border:1px solid var(--border);
  border-radius:var(--r); padding:20px; margin-bottom:16px;
  box-shadow:var(--shadow);
}}
.card-title{{font-size:13px;font-weight:600;margin-bottom:14px;letter-spacing:-.1px}}

/* ── Empty state ── */
.empty-state{{
  background:var(--surface); border:1px dashed var(--border2);
  border-radius:var(--r); padding:48px 24px; text-align:center;
  margin:16px 0;
}}
.empty-icon{{font-size:32px;margin-bottom:12px}}
.empty-msg{{font-size:14px;font-weight:500;color:var(--text2)}}
.empty-sub{{font-size:12px;color:var(--text3);margin-top:6px;max-width:420px;margin-left:auto;margin-right:auto}}

/* ── Data tables (Tracker tab) ── */
.tracker-section{{margin-bottom:24px}}
.tracker-section-title{{
  font-size:13px; font-weight:600; color:var(--text);
  margin-bottom:10px; padding-bottom:10px;
  border-bottom:1px solid var(--border2);
}}
.table-scroll{{overflow-x:auto;scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.1) transparent}}
.data-table{{border-collapse:collapse;font-size:12px;font-family:'DM Mono',monospace;white-space:nowrap}}
.data-table th{{
  background:var(--surface2); padding:7px 12px;
  text-align:right; font-weight:600; font-size:10px;
  color:var(--text2); border:1px solid var(--border);
  text-transform:uppercase; letter-spacing:.06em;
  position:sticky; top:0; z-index:2;
}}
.data-table th:first-child{{text-align:left;position:sticky;left:0;z-index:3;background:var(--surface2);min-width:150px}}
.data-table td{{padding:6px 12px;text-align:right;border:.5px solid var(--border)}}
.data-table td:first-child{{text-align:left;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:500;color:var(--text2);position:sticky;left:0;background:var(--surface);z-index:1;min-width:150px}}
.data-table tr:nth-child(even) td{{background:rgba(20,30,55,.02)}}
.data-table tr:nth-child(even) td:first-child{{background:#f8f9fc}}
.data-table th.lifetime-col{{background:var(--surface3);border-left:1px solid var(--border2)}}
.data-table td.lifetime-col{{font-weight:600;color:var(--text);background:var(--surface3)!important;border-left:1px solid var(--border2)}}
.data-table tr.total-row td{{background:var(--surface2)!important;border-top:1px solid var(--border2);font-weight:600;color:var(--text)}}
.na{{color:var(--text3)}}

/* ── Socials ── */
.soc-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
.soc-card{{padding:0;overflow:hidden}}
.soc-card-head{{display:flex;justify-content:space-between;align-items:baseline;padding:14px 18px;border-bottom:2px solid}}
.soc-name{{font-size:13px;font-weight:600}}
.soc-followers{{font-size:18px;font-weight:600;letter-spacing:-.3px}}
.soc-stats{{display:grid;grid-template-columns:1fr 1fr;padding:12px 18px;gap:8px}}
.soc-stat-lbl{{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:.04em}}
.soc-stat-val{{font-size:14px;font-weight:600;margin-top:2px}}

/* ── Mobile ── */
@media(max-width:740px){{
  .sidebar{{width:56px;min-width:56px}}
  .logo-main,.logo-sub,.nav-item span,.sidebar-footer{{display:none}}
  .nav-item{{justify-content:center;padding:10px}}
  .main{{padding:20px 16px 40px}}
  .metrics{{grid-template-columns:1fr 1fr}}
}}

.up{{color:var(--green)}}
.down{{color:var(--red)}}
</style>
</head>
<body>
<div class="shell">

<nav class="sidebar">
  <div class="sidebar-logo">
    <div class="logo-mark">POA</div>
    <div class="logo-text">
      <div class="logo-main">Point of Attack</div>
      <div class="logo-sub">Rain Delay Media</div>
    </div>
  </div>
    <a href="../../../index.html" style="display:flex;align-items:center;gap:6px;padding:10px 18px;font-size:11px;color:var(--text3);text-decoration:none;border-bottom:1px solid var(--border);letter-spacing:.02em;font-weight:500;transition:color .12s" onmouseover="this.style.color='var(--brand)'" onmouseout="this.style.color='var(--text3)'">
    ← RDM Network
  </a>
  <div class="nav">
    <div class="nav-section">Analytics</div>
    <div class="nav-item active" onclick="showPage('overview',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><rect x="1" y="1" width="6" height="6" rx="1.5" fill="currentColor"/><rect x="9" y="1" width="6" height="6" rx="1.5" fill="currentColor" opacity=".5"/><rect x="1" y="9" width="6" height="6" rx="1.5" fill="currentColor" opacity=".5"/><rect x="9" y="9" width="6" height="6" rx="1.5" fill="currentColor" opacity=".3"/></svg>
      <span>Overview</span>
    </div>
    <div class="nav-item" onclick="showPage('youtube',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><rect x="1" y="3" width="14" height="10" rx="2" fill="currentColor" opacity=".2"/><path d="M6.5 5.5l4 2.5-4 2.5V5.5z" fill="currentColor"/></svg>
      <span>YouTube</span>
    </div>
    <div class="nav-item" onclick="showPage('socials',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M5 7a2 2 0 100-4 2 2 0 000 4zm6 6a2 2 0 100-4 2 2 0 000 4zm0-10a2 2 0 100 4 2 2 0 000-4zM6.6 8.5l3 2.5M9.4 5l-3 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
      <span>Socials</span>
    </div>
    <div class="nav-item" onclick="showPage('revenue',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M5 5h4.5a1.5 1.5 0 010 3h-3a1.5 1.5 0 000 3H11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <span>Revenue</span>
    </div>
    <div class="nav-section" style="margin-top:14px">Resources</div>
    <div class="nav-item" onclick="showPage('tracker',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><rect x="1" y="1" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M1 5h14M5 5v10" stroke="currentColor" stroke-width="1.2"/></svg>
      <span>Tracker</span>
    </div>
  </div>
  <div class="sidebar-footer">Updated {generated_at}</div>
</nav>

<div class="main">

<!-- ═══ OVERVIEW ═══ -->
<div class="page active" id="page-overview">
  <div class="page-header">
    <div class="page-title">Overview</div>
    <div class="page-sub">{overview_sub}</div>
  </div>
  {overview_metrics}
  {empty_state("Dashboard ready — data will populate as pipelines come online",
               "YouTube API · Socials CSV · Revenue CSV") if not has_data else ''}
</div>

<!-- ═══ YOUTUBE ═══ -->
<div class="page" id="page-youtube">
  <div class="page-header">
    <div class="page-title">YouTube</div>
    <div class="page-sub">{'Channel analytics · views, subscribers, content mix' if has_yt else 'Not connected'}</div>
  </div>
  {yt_content}
</div>

<!-- ═══ SOCIALS ═══ -->
<div class="page" id="page-socials">
  <div class="page-header">
    <div class="page-title">Socials</div>
    <div class="page-sub">{'Cross-platform social metrics' if has_soc else 'Not connected'}</div>
  </div>
  {socials_content}
</div>

<!-- ═══ REVENUE ═══ -->
<div class="page" id="page-revenue">
  <div class="page-header">
    <div class="page-title">Revenue</div>
    <div class="page-sub">{'All monthly revenue sources' if has_rev else 'Not connected'}</div>
  </div>
  {revenue_content}
</div>

<!-- ═══ TRACKER ═══ -->
<div class="page" id="page-tracker">
  <div class="page-header">
    <div class="page-title">Tracker</div>
    <div class="page-sub">{'Full data export · newest left, oldest right' if has_yt else 'Not connected'}</div>
  </div>
  {tracker_content}
</div>

</div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<script>
// ─── Navigation ──
function showPage(id, el) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const page = document.getElementById('page-' + id);
  if (page) page.classList.add('active');
  if (el) el.classList.add('active');
}}

// ─── Charts (only render if data exists) ──
document.addEventListener('DOMContentLoaded', function() {{
  if (typeof Chart === 'undefined') return;

  const M = {js_M};
  const vids = {js_vids};
  const shorts = {js_shorts};
  const lives = {js_lives};
  const subs = {js_subs};
  const revM = {js_rev_m};
  const revTotals = {js_rev_totals};

  // YT Views stacked bar
  if (M.length && document.getElementById('yt-views-chart')) {{
    new Chart(document.getElementById('yt-views-chart'), {{
      type: 'bar',
      data: {{
        labels: M,
        datasets: [
          {{ label: 'VOD', data: vids, backgroundColor: '#2F6DDE', borderRadius: 2, stack: 's' }},
          {{ label: 'Shorts', data: shorts, backgroundColor: '#1B9B96', borderRadius: 2, stack: 's' }},
          {{ label: 'Live', data: lives, backgroundColor: '#E08C2A', borderRadius: 2, stack: 's' }},
        ]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, font: {{ size: 11 }} }} }} }},
        scales: {{
          x: {{ stacked: true, grid: {{ display: false }} }},
          y: {{ stacked: true, ticks: {{ callback: v => v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v }} }}
        }}
      }}
    }});
  }}

  // YT Subscribers line
  if (M.length && document.getElementById('yt-subs-chart')) {{
    new Chart(document.getElementById('yt-subs-chart'), {{
      type: 'line',
      data: {{
        labels: M,
        datasets: [{{ label: 'Subscribers', data: subs, borderColor: '#3AA88C', backgroundColor: 'rgba(58,168,140,.08)', fill: true, tension: .3, pointRadius: 2, borderWidth: 2 }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ grid: {{ display: false }} }}, y: {{ ticks: {{ callback: v => v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v }} }} }}
      }}
    }});
  }}

  // Revenue bar
  if (revM.length && document.getElementById('rev-chart')) {{
    new Chart(document.getElementById('rev-chart'), {{
      type: 'bar',
      data: {{
        labels: revM,
        datasets: [{{ label: 'Revenue', data: revTotals, backgroundColor: '#3AA88C', borderRadius: 3 }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          x: {{ grid: {{ display: false }} }},
          y: {{ ticks: {{ callback: v => '$' + (v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v) }} }}
        }}
      }}
    }});
  }}
}});
</script>
</body></html>"""


def _tracker_tables(d, M_display):
    """Build the Tracker tab data tables — same layout as RT."""
    def table_html(title, icon, rows, months):
        header = ('<tr><th>' + icon + ' ' + title + '</th>' +
                  ''.join(f'<th>{m}</th>' for m in months) +
                  '<th class="lifetime-col">Lifetime</th></tr>')
        body = ''
        for label, data, fmt_type in rows:
            cells = ''
            lifetime = 0
            is_pct = fmt_type == 'pct'
            for v in data:
                if v is None:
                    cells += '<td><span class="na">—</span></td>'
                elif is_pct:
                    cells += f'<td>{v*100:.1f}%</td>'
                elif isinstance(v, (int, float)):
                    cells += f'<td>{int(v):,}</td>'
                    lifetime += v
                else:
                    cells += f'<td>{v}</td>'
            lt_cell = (f'<td class="lifetime-col">{int(lifetime):,}</td>'
                       if not is_pct else '<td class="lifetime-col">—</td>')
            body += f'<tr><td>{label}</td>{cells}{lt_cell}</tr>'
        return (f'<div class="tracker-section"><div class="tracker-section-title">{icon} {title}</div>'
                f'<div class="table-scroll"><table class="data-table"><thead>{header}</thead>'
                f'<tbody>{body}</tbody></table></div></div>')

    return (
        table_html('Views', '📺', [
            ('YT Videos', d['vids'], 'int'),
            ('YT Shorts', d['shorts'], 'int'),
            ('YT Lives', d['lives'], 'int'),
        ], M_display) +
        table_html('Subscribers', '👥', [
            ('YouTube', d['yt_subs'], 'int'),
        ], M_display) +
        table_html('KPIs', '🔑', [
            ('CTR – Videos', d['ctr_vid'], 'pct'),
            ('# of Shorts', d['n_sht'], 'int'),
            ('Shorts % of Views', d['pct_sht'], 'pct'),
            ('Search % of Views', d['srch_pct'], 'pct'),
        ], M_display)
    )


# ─── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Point of Attack — Dashboard Generator")
    parser.add_argument("--tracker",  default=None, help="Path to tracker_data_poa.json")
    parser.add_argument("--revenue",  default=None)
    parser.add_argument("--socials",  default=None)
    parser.add_argument("--output",   default="point_of_attack.html")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")

    tracker_path = args.tracker or os.path.join(data_dir, "tracker_data_poa.json")
    revenue_path = args.revenue or os.path.join(data_dir, "revenue_poa.csv")
    socials_path = args.socials or os.path.join(data_dir, "socials_poa.csv")
    out = os.path.join(script_dir, args.output)

    print("=" * 55)
    print("POINT OF ATTACK — DASHBOARD GENERATOR")
    print("=" * 55)

    # Tracker: load if present, otherwise use empty
    if os.path.exists(tracker_path):
        d = extract(tracker_path)
        print(f"Tracker: {tracker_path}")
        print(f"  Months: {len(d['months'])}")
    else:
        d = _empty_extract()
        print(f"Tracker: not found ({tracker_path}) — using empty data")

    revenue = load_revenue(revenue_path)
    socials = load_socials(socials_path)
    generated_at = datetime.now().strftime("%b %d, %Y")

    print(f"Revenue: {len(revenue['months'])} months from {revenue_path}")
    print(f"Socials: {len(socials['months'])} months × {len(socials['platforms'])} platforms from {socials_path}")

    html = build_html(d, revenue, socials, generated_at)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nSaved: {out}")
    print("=" * 55)


if __name__ == "__main__":
    main()
