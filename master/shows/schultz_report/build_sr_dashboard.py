"""
The Schultz Report — Dashboard Generator
Reads tracker_data_sr.json, revenue_sr.csv, and socials_sr.csv and generates
a standalone HTML dashboard. Mirrors Road Trippin's architecture with graceful
degradation when data sources are missing or empty.

Usage:
    python build_sr_dashboard.py
    python build_sr_dashboard.py --output schultz_report.html
"""

import argparse
import json
import os
from datetime import datetime


# ─── Data loaders (same contract as RT) ──────────────────────────

def extract(path):
    """Load tracker_data_sr.json → dict matching the dashboard schema.
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
        'traffic': j.get('traffic', {}),
        'collab': j.get('collab', {}),
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
            d['vids'][0] if d['vids'] else None,
            d['shorts'][0] if d['shorts'] else None,
            d['lives'][0] if d['lives'] else None]))) if has_yt else '—'}</div>
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

        # Traffic data (paid vs organic)
        traffic = d.get('traffic', {})
        traffic_organic = []
        traffic_paid = []
        for m_ in reversed(d['months']):
            traffic_organic.append(round((traffic.get('organic_pct', {}).get(m_) or 0) * 100, 1))
            traffic_paid.append(round((traffic.get('paid_pct', {}).get(m_) or 0) * 100, 1))
        js_traffic_organic = jsa(traffic_organic)
        js_traffic_paid = jsa(traffic_paid)
        has_traffic = any(v > 0 for v in traffic_organic + traffic_paid)

        # Latest organic %
        latest_organic = traffic_organic[-1] if traffic_organic else 0
        latest_paid = traffic_paid[-1] if traffic_paid else 0
        yt_content = f"""
    <div class="metrics">
      <div class="metric"><div class="metric-label">Subscribers</div><div class="metric-value">{fmt(yt_subs_now)}</div></div>
      <div class="metric"><div class="metric-label">VOD Views ({latest_mo})</div><div class="metric-value">{fmt(d['vids'][0] if d['vids'] else None)}</div></div>
      <div class="metric"><div class="metric-label">Shorts Views ({latest_mo})</div><div class="metric-value">{fmt(d['shorts'][0] if d['shorts'] else None)}</div></div>
      <div class="metric"><div class="metric-label">Organic ({latest_mo})</div><div class="metric-value">{latest_organic:.0f}%</div><div class="metric-delta" style="color:{'var(--green)' if latest_organic >= 50 else 'var(--red)'}">{latest_paid:.0f}% paid</div></div>
    </div>
    <div class="card">
      <div class="card-title">Views by Content Type</div>
      <div style="height:320px"><canvas id="yt-views-chart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Subscriber Growth</div>
      <div style="height:280px"><canvas id="yt-subs-chart"></canvas></div>
    </div>
    <div class="card">
      <div class="card-title">Traffic Sources · Paid vs Organic</div>
      <div style="height:280px"><canvas id="traffic-chart"></canvas></div>
    </div>"""
    else:
        js_M = '[]'; js_vids = '[]'; js_shorts = '[]'; js_lives = '[]'; js_subs = '[]'
        js_traffic_organic = '[]'; js_traffic_paid = '[]'
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
            "Add rows to revenue_sr.csv to start tracking. Format: period,source,amount")

    # ── Socials tab ──
    PLATFORM_COLORS = {
        'INSTAGRAM': '#E08C2A', 'TIKTOK': '#7C5BD8', 'X': '#6B7280',
        'YOUTUBE': '#2F6DDE', 'FACEBOOK': '#1877F2',
    }
    PLATFORM_DISPLAY = {
        'INSTAGRAM': 'Instagram', 'TIKTOK': 'TikTok', 'X': 'X / Twitter',
        'YOUTUBE': 'YouTube', 'FACEBOOK': 'Facebook',
    }
    METRIC_LABELS = {'FOLLOWERS': 'Followers', 'FOLLOWER_GAIN': 'Follower Gain',
                     'VIEWS': 'Views', 'ENGAGEMENTS': 'Engagements', 'POSTS': 'Posts',
                     'ENGAGEMENT_RATE': 'ER', 'TOP_POST_VIEWS': 'Top Post Views',
                     'VIEWS_VIDS': 'YT VOD Views', 'VIEWS_SHORTS': 'YT Shorts Views',
                     'ENGAGED_VIEWS_VIDS': 'Engaged VOD', 'ENGAGED_VIEWS_SHORTS': 'Engaged Shorts'}

    if has_soc:
        soc_platforms = socials['platforms']
        soc_months_display = [fmt_period(m) for m in socials['months']]

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
            views = soc_latest_for(p, 'VIEWS') or soc_latest_for(p, 'VIEWS_VIDS')
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

        # Readonly data tracker table
        soc_table = '<div class="table-scroll"><table class="data-table"><thead><tr><th>Platform · Metric</th>'
        for ml in soc_months_display:
            soc_table += f'<th>{ml}</th>'
        soc_table += '</tr></thead><tbody>'
        last_plat = None
        all_keys = sorted(socials['data'].keys(), key=lambda k: (k[0], k[1]))
        for (plat, metric) in all_keys:
            if plat != last_plat:
                display = PLATFORM_DISPLAY.get(plat, plat.title())
                soc_table += f'<tr><td style="font-weight:700;background:#161680;color:var(--text)">{display}</td>'
                for _ in socials['months']:
                    soc_table += '<td style="background:#161680"></td>'
                soc_table += '</tr>'
                last_plat = plat
            label = METRIC_LABELS.get(metric, metric.replace('_',' ').title())
            soc_table += f'<tr><td style="padding-left:18px;color:var(--text2)">{label}</td>'
            vals = socials['data'][(plat, metric)]
            for v in vals:
                if v is None:
                    soc_table += '<td><span class="na">—</span></td>'
                elif metric == 'ENGAGEMENT_RATE' and isinstance(v, (int, float)):
                    soc_table += f'<td>{v*100:.2f}%</td>'
                elif isinstance(v, (int, float)):
                    soc_table += f'<td>{int(v):,}</td>'
                else:
                    soc_table += f'<td>{v}</td>'
            soc_table += '</tr>'
        soc_table += '</tbody></table></div>'

        socials_content = f"""
    <div class="soc-grid">{platform_cards}</div>
    <div style="margin-top:20px">{soc_table}</div>"""
    else:
        socials_content = empty_state(
            "No socials data yet",
            "Add rows to socials_sr.csv to start tracking")

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
<title>The Schultz Report — Dashboard</title>
<link rel="icon" type="image/png" href="data:image/png;base64,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">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=DM+Mono:wght@400;500&family=Oswald:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ─────────────────────────────────────────────────────────────
   THE SCHULTZ REPORT DASHBOARD — Rain Delay Media
   Brand color: #C9A84C (gold)
   ───────────────────────────────────────────────────────────── */
:root{{
  --brand:        #E8C840;
  --brand-deep:   #C9A830;
  --brand-soft:   rgba(232,200,64,.10);
  --brand-tint:   rgba(232,200,64,.18);
  --bg:           #11116b;
  --surface:      rgba(255,255,255,.06);
  --surface2:     rgba(255,255,255,.10);
  --surface3:     rgba(255,255,255,.14);
  --border:       rgba(255,255,255,.10);
  --border2:      rgba(255,255,255,.18);
  --text:         #FFFFFF;
  --text2:        #FFFFFF;
  --text3:        #f2f2f2;
  --green:        #34D058;
  --red:          #F85149;
  --r:            10px;
  --rsm:          6px;
  --shadow:       0 1px 3px rgba(0,0,0,.3), 0 1px 2px rgba(0,0,0,.2);
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px;position:relative}}
body::before{{content:'';position:fixed;top:0;left:0;width:100%;height:100%;z-index:0;pointer-events:none;background:url("data:image/jpeg;base64,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") repeat;background-size:700px auto;opacity:.3}}
body > *{{position:relative;z-index:1}}

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
  color:#11116b; font-family:'Oswald',sans-serif; font-weight:700; font-size:12px;
  box-shadow:0 2px 4px rgba(232,200,64,.3);
}}
.logo-text{{display:flex;flex-direction:column;line-height:1.15}}
.logo-main{{font-size:14px;font-weight:600;letter-spacing:-.3px;color:var(--text)}}
.logo-sub{{font-size:11px;color:var(--text3);margin-top:1px}}
.nav{{padding:14px 10px 10px;flex:1}}
.nav-section{{font-family:'Oswald',sans-serif;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);padding:8px 12px 6px;font-weight:600}}
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
.metric-value{{font-family:'Oswald',sans-serif;font-size:26px;font-weight:600;letter-spacing:-.3px;margin:6px 0 2px}}
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
.data-table th{{background:#161680;
  background:var(--surface2); padding:7px 12px;
  text-align:right; font-weight:600; font-size:10px;
  color:var(--text2); border:1px solid var(--border);
  text-transform:uppercase; letter-spacing:.06em;
  position:sticky; top:0; z-index:2;
}}
.data-table th:first-child{{text-align:left;position:sticky;left:0;z-index:3;background:#161680;min-width:150px}}
.data-table td{{padding:6px 12px;text-align:right;border:.5px solid var(--border)}}
.data-table td:first-child{{text-align:left;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:500;color:var(--text2);position:sticky;left:0;background:#11116b;z-index:1;min-width:150px}}
.data-table tr:nth-child(even) td{{background:rgba(255,255,255,.03)}}
.data-table tr:nth-child(even) td:first-child{{background:#141470}}
.data-table th.lifetime-col{{background:#1a1a85;border-left:1px solid var(--border2)}}
.data-table td.lifetime-col{{font-weight:600;color:var(--text);background:#1a1a85!important;border-left:1px solid var(--border2)}}
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
    <div class="logo-mark">SR</div>
    <div class="logo-text">
      <div class="logo-main">Schultz Report</div>
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
          x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ color:'#f2f2f2' }} }},
          y: {{ stacked: true, ticks: {{ color:'#f2f2f2',callback: v => v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v }} }}
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
        datasets: [{{ label: 'Subscribers', data: subs, borderColor: '#C9A84C', backgroundColor: 'rgba(201,168,76,.08)', fill: true, tension: .3, pointRadius: 2, borderWidth: 2 }}]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{ x: {{ grid: {{ display: false }}, ticks: {{ color:'#f2f2f2' }} }},
        y: {{ ticks: {{ color:'#f2f2f2', callback: v => v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v }} }} }}
      }}
    }});
  }}

  // Revenue bar
  if (revM.length && document.getElementById('rev-chart')) {{
    new Chart(document.getElementById('rev-chart'), {{
      type: 'bar',
      data: {{
        labels: revM,
        datasets: [{{ label: 'Revenue', data: revTotals, backgroundColor: '#C9A84C', borderRadius: 3 }}]
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

  // Traffic Sources chart (paid vs organic)
  const tOrganic = {js_traffic_organic};
  const tPaid = {js_traffic_paid};
  if (M.length && document.getElementById('traffic-chart') && (tOrganic.some(v=>v>0) || tPaid.some(v=>v>0))) {{
    new Chart(document.getElementById('traffic-chart'), {{
      type: 'bar',
      data: {{
        labels: M,
        datasets: [
          {{ label: 'Organic %', data: tOrganic, backgroundColor: '#34D058', borderRadius: 2, stack: 's' }},
          {{ label: 'Paid %', data: tPaid, backgroundColor: '#F85149', borderRadius: 2, stack: 's' }},
        ]
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#f2f2f2', boxWidth: 10, font: {{ size: 11 }} }} }} }},
        scales: {{
          x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ color: '#f2f2f2' }} }},
          y: {{ stacked: true, max: 100, grid: {{ color: 'rgba(255,255,255,.06)' }}, ticks: {{ color: '#f2f2f2', callback: v => v + '%' }} }}
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
    parser = argparse.ArgumentParser(description="The Schultz Report — Dashboard Generator")
    parser.add_argument("--tracker",  default=None, help="Path to tracker_data_sr.json")
    parser.add_argument("--revenue",  default=None)
    parser.add_argument("--socials",  default=None)
    parser.add_argument("--output",   default="schultz_report.html")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data_sr")

    tracker_path = args.tracker or os.path.join(data_dir, "tracker_data_sr.json")
    revenue_path = args.revenue or os.path.join(data_dir, "revenue_sr.csv")
    socials_path = args.socials or os.path.join(data_dir, "socials_sr.csv")
    out = os.path.join(script_dir, args.output)

    print("=" * 55)
    print("THE SCHULTZ REPORT — DASHBOARD GENERATOR")
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