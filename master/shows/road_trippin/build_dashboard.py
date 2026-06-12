"""
Road Trippin' — Dashboard Generator v3
Reads the Analytics Tracker Excel and generates a standalone HTML dashboard.

Changes in v3:
  - Fixed chart containers: fixed-px height outer, explicit-px width inner (scrollable)
  - Tracker tab: all sheets shown at once with section titles (no tabs)
  - Reports tab: scaffold for Fanatics + Revenue PDFs (auto-scans data/reports/)
  - Rain Delay brand stylesheet prepped (commented, activate when ready)

Usage:
    python build_dashboard.py
    python build_dashboard.py
    python build_dashboard.py --output data/road_trippin_dashboard.html
"""

import argparse
import json
import os
from datetime import datetime


# ─── Rain Delay brand notes (implement in future stylesheet) ─────
# Site: raindelaymedia.com
# Aesthetic: dark/black backgrounds, white text, minimal, editorial
# Logo: lowercase "rain delay" wordmark, no icon, clean sans-serif
# Palette observed: near-black bg (~#0a0a0a), white text, gold/amber accent
# Typography: appears to use a condensed grotesque (similar to Barlow Condensed)
# Vibe: high-end sports media, not garish — think The Athletic x ESPN Films
# Current dashboard uses neutral light theme — swap CSS vars below to go dark:
#   --bg → #0d0d0d
#   --surface → #161616
#   --surface2 → #222222
#   --text → #f5f5f5
#   --text2 → #a0a0a0
#   --text3 → #606060
#   --border → rgba(255,255,255,.08)
#   --accent → #C9A84C  (gold)
# ─────────────────────────────────────────────────────────────────




def extract(path):
    """Load tracker_data.json and return a dict matching the dashboard's expected schema."""
    import json as _json
    with open(path, encoding='utf-8') as f:
        j = _json.load(f)

    months = j['months']  # newest first: ['2026-05', '2026-04', ...]

    def series(keys, default=None):
        """Navigate full key path, then look up each month."""
        src = j
        for k in keys:
            src = src.get(k, {})
        # src is now the month-keyed dict e.g. {'2026-05': 227945, ...}
        if isinstance(src, dict):
            return [src.get(m, default) for m in months]
        return [default] * len(months)

    # Build running subscriber total from subs_gained/lost + current_subs
    current_subs = j.get('current_subs', 0)
    subs_gained  = series(['yt', 'subs_gained'], 0)
    subs_lost    = series(['yt', 'subs_lost'],   0)
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

    best_of_raw   = j.get('best_of', {})
    best_of_label = best_of_raw.get('label', '')
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
        'apple_subs':   [None] * len(months),
        'spotify_subs': [None] * len(months),
        'ctr_vid':      series(['kpis', 'ctr']),
        'ctr_sht':      [None] * len(months),
        'n_sht':        series(['kpis', 'shorts_count']),
        'pct_sht':      pct_sht,
        'srch_pct':     series(['kpis', 'search_pct']),
        'srch_ctr':     [None] * len(months),
        'ig_fol':       [None] * len(months),
        'tt_fol':       [None] * len(months),
        'x_fol':        [None] * len(months),
        'best_of':      best_of,
        'best_of_label': best_of_label,
        'top_content_monthly': j.get('top_content_monthly', {}),
        'subs_gained':  subs_gained,
        'subs_lost':    subs_lost,
        'current_subs': current_subs,
    }

def load_socials(csv_path):
    """Load flat socials CSV. Returns:
    {
      'months': ['2024-08', ..., '2026-04'],   # chronological
      'platforms': ['INSTAGRAM','TIKTOK','X','YOUTUBE'],
      'data': {('INSTAGRAM','FOLLOWERS'): [None, ..., 112471], ...}
    }
    """
    import csv as _csv
    if not os.path.exists(csv_path):
        return {'months': [], 'platforms': [], 'data': {}}

    PLATFORM_ORDER = ['INSTAGRAM', 'TIKTOK', 'X', 'YOUTUBE', 'FACEBOOK']
    raw = {}
    platforms_found = set()

    with open(csv_path, encoding='utf-8') as f:
        for r in _csv.DictReader(f):
            period = r['period'].strip()
            platform = r['platform'].strip().upper()
            metric = r['metric'].strip().upper()
            val_raw = r['value'].strip()
            try:
                val = float(val_raw)
            except ValueError:
                val = val_raw
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
    """Load flat revenue CSV. Returns dict with months list and per-source data.
    Months returned in chronological order (oldest first)."""
    import csv as _csv
    if not os.path.exists(csv_path):
        return {'months': [], 'sources': {}, 'totals': []}

    # Canonical display order. Anything in the CSV that isn't here (custom /
    # misc sources added via the tracker) is appended afterward, alphabetically.
    CANON = ["YT_VIDEOS", "YT_SHORTS", "YT_LIVES", "CULTURE_GENESIS",
             "UPTIDES", "ACAST", "FANATICS",
             "BACKYARD_PODCAST", "BACKYARD_PROGRAMMATIC",
             "SOCIAL", "MERCH"]

    # Legacy rows used "BRANDS"/"AUDIO"; Fanatics and Acast now own that money.
    # Remap on load so the dashboard is correct even if revenue.csv hasn't been migrated.
    REMAP = {"BRANDS": "FANATICS", "AUDIO": "ACAST"}

    raw = {}
    with open(csv_path, encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            period = r["period"].strip()
            source = r["source"].strip()
            source = REMAP.get(source, source)
            amt_raw = r["amount"].strip()
            try:
                amt = float(amt_raw)
            except ValueError:
                amt = amt_raw  # TBD, N/A, etc.
            # If a month somehow has both BRANDS and FANATICS, sum the numerics.
            bucket = raw.setdefault(period, {})
            if source in bucket and isinstance(bucket[source], (int, float)) \
                    and isinstance(amt, (int, float)):
                bucket[source] += amt
            else:
                bucket[source] = amt

    months = sorted(raw.keys())  # oldest first

    # Every source that actually appears anywhere in the file.
    present = set()
    for m in months:
        present.update(raw[m].keys())

    # Canonical sources first (only those present), then custom ones sorted.
    order = [s for s in CANON if s in present]
    order += sorted(present - set(CANON))

    sources = {}
    for src in order:
        sources[src] = [raw[m].get(src) for m in months]

    totals = []
    for m in months:
        t = sum(v for v in raw[m].values() if isinstance(v, (int, float)))
        totals.append(t if t > 0 else None)

    return {'months': months, 'sources': sources, 'totals': totals, 'order': order}


def fmt_period(p):
    """Convert YYYY-MM to MMM YY display."""
    from datetime import datetime as _dt
    try:
        dt = _dt.strptime(p, "%Y-%m")
        now = _dt.now()
        if dt.year == now.year:
            return dt.strftime("%b").upper()
        return dt.strftime("%b").upper() + " " + str(dt.year)[-2:]
    except:
        return p


def scan_reports(data_dir):
    """Scan data/reports/ for PDFs and return structured list."""
    reports = {'fanatics': [], 'revenue': []}
    for category in ('fanatics', 'revenue'):
        folder = os.path.join(data_dir, 'reports', category)
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder), reverse=True):
                if f.lower().endswith('.pdf'):
                    reports[category].append({
                        'filename': f,
                        'label': f.replace('_', ' ').replace('.pdf', ''),
                        'path': os.path.join('reports', category, f).replace('\\', '/'),
                    })
    return reports


def jsa(lst):
    def jv(v):
        if v is None: return 'null'
        if isinstance(v, bool): return 'true' if v else 'false'
        if isinstance(v, str): return json.dumps(v)
        return str(v)
    return '[' + ','.join(jv(v) for v in lst) + ']'


def latest(lst):
    for v in reversed(lst):
        if v is not None and v != 0: return v
    return None


def prev_val(lst):
    found = 0
    for v in reversed(lst):
        if v is not None and v != 0:
            found += 1
            if found == 2: return v
    return None


def fmt(v, pct=False):
    if v is None: return '—'
    if pct: return f'{v*100:.1f}%'
    if isinstance(v, (int, float)):
        if v >= 1_000_000: return f'{v/1_000_000:.2f}M'
        if v >= 1_000: return f'{v/1_000:.1f}K'
        return f'{int(v):,}'
    return str(v)


def delta_str(lst):
    a, b = latest(lst), prev_val(lst)
    if a is None or b is None or b == 0: return '—'
    d = a - b
    cls = 'up' if d >= 0 else 'down'
    return f'<span class="{cls}">{"+" if d>=0 else ""}{fmt(d)} vs prev</span>'


def bar_html(v, color, name, val_str=None, baseline=1):
    pct = min(100, round((v or 0) / max(baseline, 1) * 100))
    display = val_str if val_str else (fmt(v) if v else '—')
    return (f'<div class="plat-row"><span class="plat-name">{name}</span>'
            f'<div class="plat-bar-bg"><div class="plat-bar" style="width:{pct}%;background:{color}"></div></div>'
            f'<span class="plat-val">{display}</span></div>')


def table_html(title, icon, rows, months):
    """Render a full-width data table with a section title above it."""
    header = '<tr><th>' + icon + ' ' + title + '</th>' + ''.join(f'<th>{m}</th>' for m in months) + '</tr>'
    body = ''
    for label, data, fmt_type in rows:
        cells = ''
        for v in data:
            if v is None:
                cells += '<td><span class="na">—</span></td>'
            elif fmt_type == 'pct' or (isinstance(v, float) and 0 < v < 1):
                cells += f'<td>{v*100:.1f}%</td>'
            elif isinstance(v, (int, float)):
                cells += f'<td>{int(v):,}</td>'
            else:
                cells += f'<td>{v}</td>'
        body += f'<tr><td>{label}</td>{cells}</tr>'
    return (f'<div class="tracker-section"><div class="tracker-section-title">{icon} {title}</div>'
            f'<div class="table-scroll"><table class="data-table"><thead>{header}</thead><tbody>{body}</tbody></table></div></div>')


def reports_html(reports):
    """Render the Reports tab content."""
    def section(title, icon, items):
        if not items:
            return (f'<div class="reports-section"><div class="reports-section-title">{icon} {title}</div>'
                    f'<div class="reports-empty">No reports yet — generate one with <code>build_report.py</code></div></div>')
        cards = ''
        for r in items:
            cards += (f'<div class="report-card" onclick="openReport(\'{r["path"]}\')">'
                      f'<div class="report-icon">📄</div>'
                      f'<div class="report-info"><div class="report-label">{r["label"]}</div>'
                      f'<div class="report-filename">{r["filename"]}</div></div>'
                      f'<div class="report-arrow">→</div></div>')
        return (f'<div class="reports-section"><div class="reports-section-title">{icon} {title}</div>'
                f'<div class="report-cards">{cards}</div></div>')

    embed = ('<div id="pdf-viewer" style="display:none;margin-top:20px;">'
             '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
             '<span id="pdf-label" style="font-size:13px;font-weight:500;"></span>'
             '<button onclick="closePdf()" style="font-size:12px;padding:4px 10px;border-radius:6px;border:.5px solid var(--border2);background:var(--surface2);cursor:pointer;">✕ Close</button>'
             '</div>'
             '<iframe id="pdf-frame" style="width:100%;height:75vh;border:none;border-radius:var(--r);border:.5px solid var(--border);"></iframe>'
             '</div>')

    fanatics = section('Fanatics Delivery Reports', '📊', reports['fanatics'])
    revenue = section('Revenue Reports', '💰', reports['revenue'])
    return fanatics + revenue + embed


def build_html(d, reports, revenue, socials, generated_at):
    M_raw = d['months']  # newest first: ['2026-05', '2026-04', ...]
    n = len(M_raw)

    # Convert YYYY-MM → display labels
    M_display = [fmt_period(m) for m in M_raw]

    # Reverse everything to oldest-first for left-to-right charts
    M      = list(reversed(M_display))  # ['AUG 24', ..., 'MAY 26']
    M_full = M  # full 22-month history

    def rev(lst):
        return list(reversed(lst)) if lst else []

    # All data series reversed to match oldest-first
    vids_full   = rev(d['vids'])
    shorts_full = rev(d['shorts'])
    lives_full  = rev(d['lives'])
    subs_full   = rev(d['yt_subs'])
    ltotal_full = rev(d['l_total'])
    lstrm_full  = rev(d['spotify'])
    perep_full  = rev(d['l_perep'])
    nsht_full   = rev(d['n_sht'])
    pctsht_full = rev(d['pct_sht'])

    # 12-month window (most recent 12, oldest-first within that window)
    WINDOW = 12
    M12       = M[-WINDOW:]
    vids12    = vids_full[-WINDOW:]
    shorts12  = shorts_full[-WINDOW:]
    lives12   = lives_full[-WINDOW:]
    subs12    = subs_full[-WINDOW:]
    ltotal12  = ltotal_full[-WINDOW:]
    lstrm12   = lstrm_full[-WINDOW:]
    perep12   = perep_full[-WINDOW:]
    nsht12    = nsht_full[-WINDOW:]
    pctsht12  = pctsht_full[-WINDOW:]

    # Use latest value for metric cards (last item = most recent)
    latest_mo   = M[-1] if M else '—'
    yt_subs_now = subs_full[-1] if subs_full else 0
    listens_now = next((v for v in reversed(ltotal_full) if v), 0)
    eps_now     = next((v for v in reversed(rev(d['eps'])) if v), 0)
    pct_sht_now = next((v for v in reversed(pctsht_full) if v is not None), None)
    streams_now = next((v for v in reversed(lstrm_full) if v), 0)

    chart_px    = max(n * 46, 500)
    chart_px_12 = max(WINDOW * 46, 500)

    # Platform reach — pull latest follower counts from socials.csv (fallback to xlsx if missing)
    def soc_latest(platform, metric):
        series = socials['data'].get((platform, metric), [])
        for v in reversed(series):
            if isinstance(v, (int, float)) and v > 0:
                return v
        return None

    ig_followers = soc_latest('INSTAGRAM', 'FOLLOWERS') or latest(d['ig_fol'])
    tt_followers = soc_latest('TIKTOK', 'FOLLOWERS')    or latest(d['tt_fol'])
    x_followers  = soc_latest('X', 'FOLLOWERS')         or latest(d['x_fol'])
    fb_followers = soc_latest('FACEBOOK', 'FOLLOWERS')

    platform_bars = (
        bar_html(yt_subs_now, '#2F6DDE', 'YouTube', fmt(yt_subs_now), yt_subs_now) +
        bar_html(ig_followers, '#E08C2A', 'Instagram', baseline=yt_subs_now) +
        bar_html(latest(d['apple_subs']), '#DD4B5C', 'Apple Podcasts', baseline=yt_subs_now) +
        bar_html(tt_followers, '#7C5BD8', 'TikTok', baseline=yt_subs_now) +
        bar_html(latest(d['spotify_subs']), '#1B7A3A', 'Spotify', baseline=yt_subs_now) +
        bar_html(x_followers, '#6B7280', 'X / Twitter', baseline=yt_subs_now)
    )

    tracker_tables = (
        table_html('Views', '📺', [
            ('# of Episodes', d['eps'], 'int'),
            ('YT Videos', d['vids'], 'int'),
            ('YT Shorts', d['shorts'], 'int'),
            ('YT Lives', d['lives'], 'int'),
            ('Spotify Streams', d['spotify'], 'int'),
        ], M) +
        table_html('Listens', '🎧', [
            ('# of Episodes', d['l_eps'], 'int'),
            ('Per-ep Listens', d['l_perep'], 'int'),
            ('Total Listens', d['l_total'], 'int'),
        ], M) +
        table_html('Subscribers', '👥', [
            ('YouTube', d['yt_subs'], 'int'),
            ('Apple Podcasts', d['apple_subs'], 'int'),
            ('Spotify', d['spotify_subs'], 'int'),
        ], M) +
        table_html('KPIs', '🔑', [
            ('CTR – Videos', d['ctr_vid'], 'pct'),
            ('CTR – Shorts', d['ctr_sht'], 'pct'),
            ('# of Shorts', d['n_sht'], 'int'),
            ('Shorts % of Views', d['pct_sht'], 'pct'),
            ('Search % of Views', d['srch_pct'], 'pct'),
            ('CTR in Search', d['srch_ctr'], 'pct'),
        ], M)
    )

    reports_content = reports_html(reports)

    # ─── Revenue ───────────────────────────────────────────────
    rev_M_raw = revenue.get('months', [])
    rev_sources = revenue.get('sources', {})
    rev_totals_raw = revenue.get('totals', [])
    rev_order = revenue.get('order', [])

    # Display labels (oldest left, newest right — same as charts)
    rev_M_display = [fmt_period(p) for p in rev_M_raw]
    rev_chart_px = max(len(rev_M_raw) * 46, 500) if rev_M_raw else 500

    # Latest month metrics
    rev_latest_total = rev_totals_raw[-1] if rev_totals_raw else 0
    rev_prev_total = rev_totals_raw[-2] if len(rev_totals_raw) >= 2 else 0
    rev_latest_label = rev_M_display[-1] if rev_M_display else '—'

    # Last 12 months total
    rev_12mo_total = sum(t for t in rev_totals_raw[-12:] if t)
    # Average per month over last 12
    rev_12mo_avg = rev_12mo_total / max(len([t for t in rev_totals_raw[-12:] if t]), 1)

    # Color map for revenue sources
    SOURCE_COLORS = {
        'YT_VIDEOS':              '#2F6DDE',  # brand blue
        'YT_SHORTS':              '#1B9B96',  # teal
        'YT_LIVES':               '#E08C2A',  # amber
        'CULTURE_GENESIS':        '#DD4B5C',  # coral
        'UPTIDES':                '#7C5BD8',  # violet
        'ACAST':                  '#1B7A3A',  # green (audio payout partner)
        'FANATICS':               '#C9A84C',  # gold (presenting partner)
        'BACKYARD_PODCAST':       '#0E7490',  # deep cyan  ── Backyard family
        'BACKYARD_PROGRAMMATIC':  '#67E8F9',  # light cyan ──┘ (two shades, one source)
        'SOCIAL':                 '#E27CC4',  # pink
        'MERCH':                  '#6B7280',  # gray
    }
    SOURCE_DISPLAY = {
        'YT_VIDEOS': 'YT Videos', 'YT_SHORTS': 'YT Shorts', 'YT_LIVES': 'YT Lives',
        'CULTURE_GENESIS': 'Culture Genesis', 'UPTIDES': 'Uptides',
        'ACAST': 'Acast', 'FANATICS': 'Fanatics',
        'BACKYARD_PODCAST': 'Backyard Ventures · Podcast',
        'BACKYARD_PROGRAMMATIC': 'Backyard Ventures · Programmatic',
        'SOCIAL': 'Social', 'MERCH': 'Merch',
    }

    # Auto-fill any custom / misc source (e.g. PATREON, LIVE_EVENTS, TEST) that
    # the tracker wrote to revenue.csv but isn't hardcoded above. Gives each a
    # stable color from a fallback palette and a Title-Cased label, so it flows
    # into the legend, stacked chart, mix donut, and table like everything else.
    _CUSTOM_PALETTE = ['#9CA3AF', '#A78BFA', '#FBBF24', '#F472B6',
                       '#4ADE80', '#60A5FA', '#FB923C', '#22D3EE']
    _ci = 0
    for src in rev_order:
        if src not in SOURCE_DISPLAY:
            SOURCE_DISPLAY[src] = src.replace('_', ' ').title()
        if src not in SOURCE_COLORS:
            SOURCE_COLORS[src] = _CUSTOM_PALETTE[_ci % len(_CUSTOM_PALETTE)]
            _ci += 1

    def num_only(lst):
        """Convert TBD/N/A to None, keep numbers."""
        return [v if isinstance(v, (int, float)) else None for v in lst]

    # Stacked dataset for "By source" view
    stacked_ds = []
    for src in rev_order:
        vals = num_only(rev_sources.get(src, []))
        if any(v for v in vals if v):
            stacked_ds.append({
                'label': SOURCE_DISPLAY.get(src, src),
                'data': vals,
                'backgroundColor': SOURCE_COLORS.get(src, '#6B7280'),
                'borderRadius': 2,
                'stack': 's',
            })

    # Source mix (pie/doughnut) — last 12 months
    mix_labels, mix_values, mix_colors = [], [], []
    for src in rev_order:
        vals = num_only(rev_sources.get(src, []))
        total = sum(v for v in vals[-12:] if v)
        if total > 0:
            mix_labels.append(SOURCE_DISPLAY.get(src, src))
            mix_values.append(round(total, 2))
            mix_colors.append(SOURCE_COLORS.get(src, '#6B7280'))

    # YouTube AdSense breakdown (V/S/L)
    yt_videos_data = num_only(rev_sources.get('YT_VIDEOS', []))
    yt_shorts_data = num_only(rev_sources.get('YT_SHORTS', []))
    yt_lives_data  = num_only(rev_sources.get('YT_LIVES', []))

    # Revenue subtitle
    if rev_M_raw:
        revenue_subtitle = f"{fmt_period(rev_M_raw[0])} – {rev_latest_label} · all monthly revenue sources"
    else:
        revenue_subtitle = "No revenue data yet — run build_revenue_tracker.py to add months"

    # Revenue metric cards
    delta_pct = ((rev_latest_total - rev_prev_total) / rev_prev_total * 100) if rev_prev_total else None
    delta_str_html = ''
    if delta_pct is not None:
        cls = 'up' if delta_pct >= 0 else 'down'
        sign = '+' if delta_pct >= 0 else ''
        delta_str_html = f'<span class="{cls}">{sign}{delta_pct:.1f}% vs prev</span>'
    else:
        delta_str_html = '—'

    revenue_metrics = (
        f'<div class="metric"><div class="metric-label">Latest ({rev_latest_label})</div>'
        f'<div class="metric-value">${rev_latest_total:,.0f}</div>'
        f'<div class="metric-delta">{delta_str_html}</div></div>'

        f'<div class="metric"><div class="metric-label">12-mo Total</div>'
        f'<div class="metric-value">${rev_12mo_total:,.0f}</div>'
        f'<div class="metric-delta" style="color:var(--text2)">trailing 12 months</div></div>'

        f'<div class="metric"><div class="metric-label">12-mo Avg</div>'
        f'<div class="metric-value">${rev_12mo_avg:,.0f}</div>'
        f'<div class="metric-delta" style="color:var(--text2)">per month</div></div>'

        f'<div class="metric"><div class="metric-label">Months tracked</div>'
        f'<div class="metric-value">{len(rev_M_raw)}</div>'
        f'<div class="metric-delta" style="color:var(--text2)">since {fmt_period(rev_M_raw[0]) if rev_M_raw else "—"}</div></div>'
    )

    # Legend chips for stacked view
    revenue_legend = ''.join(
        f'<span class="legend-item"><span class="leg-dot" style="background:{SOURCE_COLORS.get(src, "#6B7280")}"></span>{SOURCE_DISPLAY.get(src, src)}</span>'
        for src in rev_order if any(v for v in num_only(rev_sources.get(src, [])) if v)
    )

    # ─── Revenue table — 90 / 6 / 12 / >12 layout ────────────────
    # Layout: oldest first in CSV, but we want newest first in display (left-to-right)
    # Reverse for the table to show newest on left.
    rev_M_table = list(reversed(rev_M_display))
    rev_M_periods_table = list(reversed(rev_M_raw))

    def reverse_data(lst):
        return list(reversed(lst))

    def fmt_currency(v):
        if v is None: return '<span class="na">—</span>'
        if isinstance(v, str): return f'<span class="na">{v}</span>'
        if v == 0: return '$0.00'
        return f'${v:,.2f}'

    def revenue_table_html():
        if not rev_M_table:
            return '<div class="reports-empty">No revenue data yet — run build_revenue_tracker.py to add months.</div>'

        n = len(rev_M_table)
        # Section column ranges (1-indexed for display)
        # B-D = Past 90 (cols 0-2), E-G = Past 6 (3-5), H-M = Past 12 (6-11), N+ = >12 (12+)
        sections = []
        if n >= 1: sections.append(('PAST 90 DAYS', 0, min(2, n-1)))
        if n >= 4: sections.append(('PAST 6 MONTHS', 3, min(5, n-1)))
        if n >= 7: sections.append(('PAST 12 MONTHS', 6, min(11, n-1)))
        if n >= 13: sections.append(('> 12 MONTHS', 12, n-1))

        # Build header rows: section labels (row 1) + month labels (row 2)
        section_row = '<tr><th class="section-label-cell">&nbsp;</th>'
        for label, start, end in sections:
            colspan = end - start + 1
            section_row += f'<th colspan="{colspan}" class="section-label">{label}</th>'
        section_row += '</tr>'

        month_row = '<tr><th>Source</th>'
        for m in rev_M_table:
            month_row += f'<th>{m}</th>'
        month_row += '</tr>'

        # Source data rows
        body = ''
        for src in rev_order:
            vals = reverse_data(num_only(rev_sources.get(src, [])))
            # Also include TBD/N/A as raw strings
            raw_vals = reverse_data(rev_sources.get(src, []))
            display = SOURCE_DISPLAY.get(src, src)
            body += f'<tr><td>{display}</td>'
            for v in raw_vals:
                body += f'<td>{fmt_currency(v)}</td>'
            body += '</tr>'

        # Total row
        body += '<tr class="total-row"><td><strong>TOTAL</strong></td>'
        for total in reverse_data(rev_totals_raw):
            if total and total > 0:
                body += f'<td><strong>${total:,.2f}</strong></td>'
            else:
                body += '<td><span class="na">—</span></td>'
        body += '</tr>'

        return (f'<div class="table-scroll"><table class="data-table revenue-table">'
                f'<thead>{section_row}{month_row}</thead><tbody>{body}</tbody></table></div>')

    revenue_table = revenue_table_html()

    # ─── Socials ──────────────────────────────────────────────────
    soc_M_raw = socials.get('months', [])
    soc_platforms = socials.get('platforms', [])
    soc_data = socials.get('data', {})
    soc_M_display = [fmt_period(p) for p in soc_M_raw]
    soc_chart_px = max(len(soc_M_raw) * 46, 500) if soc_M_raw else 500

    PLATFORM_COLORS = {
        'INSTAGRAM': '#E08C2A',  # amber (matches platform reach bar)
        'TIKTOK':    '#7C5BD8',  # violet
        'X':         '#6B7280',  # gray
        'YOUTUBE':   '#2F6DDE',  # brand blue
        'FACEBOOK':  '#1B7A3A',  # green
    }
    PLATFORM_DISPLAY = {
        'INSTAGRAM': 'Instagram', 'TIKTOK': 'TikTok', 'X': 'X / Twitter',
        'YOUTUBE': 'YouTube', 'FACEBOOK': 'Facebook',
    }

    def soc_series(platform, metric):
        return soc_data.get((platform, metric), [None] * len(soc_M_raw))

    def soc_latest_for(platform, metric):
        for v in reversed(soc_series(platform, metric)):
            if isinstance(v, (int, float)) and v > 0:
                return v
        return None

    # Latest month metrics — totals across platforms
    soc_latest_label = soc_M_display[-1] if soc_M_display else '—'
    total_followers = sum(filter(None, [soc_latest_for(p, 'FOLLOWERS') for p in soc_platforms]))
    total_impressions = sum(filter(None, [soc_latest_for(p, 'IMPRESSIONS') for p in soc_platforms]))
    total_engagements = sum(filter(None, [soc_latest_for(p, 'ENGAGEMENTS') for p in soc_platforms]))
    total_posts = sum(filter(None, [soc_latest_for(p, 'POSTS') for p in soc_platforms]))

    # Aggregate engagement rate weighted by impressions
    if total_impressions > 0:
        agg_er = total_engagements / total_impressions
    else:
        agg_er = None

    socials_metrics_html = (
        f'<div class="metric"><div class="metric-label">Total Followers ({soc_latest_label})</div>'
        f'<div class="metric-value">{fmt(total_followers)}</div>'
        f'<div class="metric-delta" style="color:var(--text2)">across {len(soc_platforms)} platforms</div></div>'

        f'<div class="metric"><div class="metric-label">Impressions ({soc_latest_label})</div>'
        f'<div class="metric-value">{fmt(total_impressions)}</div>'
        f'<div class="metric-delta" style="color:var(--text2)">all platforms</div></div>'

        f'<div class="metric"><div class="metric-label">Engagements ({soc_latest_label})</div>'
        f'<div class="metric-value">{fmt(total_engagements)}</div>'
        f'<div class="metric-delta" style="color:var(--text2)">{fmt(agg_er, pct=True) if agg_er else "—"} ER</div></div>'

        f'<div class="metric"><div class="metric-label">Posts ({soc_latest_label})</div>'
        f'<div class="metric-value">{int(total_posts) if total_posts else "—"}</div>'
        f'<div class="metric-delta" style="color:var(--text2)">all platforms</div></div>'
    )

    # Per-platform mini cards on Socials page
    def soc_platform_card(platform):
        color = PLATFORM_COLORS.get(platform, '#6B7280')
        display = PLATFORM_DISPLAY.get(platform, platform.title())
        f_now = soc_latest_for(platform, 'FOLLOWERS')
        gain = soc_latest_for(platform, 'FOLLOWER_GAIN')
        imp = soc_latest_for(platform, 'IMPRESSIONS')
        eng = soc_latest_for(platform, 'ENGAGEMENTS')
        posts = soc_latest_for(platform, 'POSTS')
        er = soc_latest_for(platform, 'ENGAGEMENT_RATE')
        top_post = soc_latest_for(platform, 'TOP_POST_VIEWS')

        gain_html = ''
        if gain is not None:
            cls = 'up' if gain >= 0 else 'down'
            sign = '+' if gain >= 0 else ''
            gain_html = f'<span class="{cls}" style="font-size:11px;font-weight:500">{sign}{fmt(gain)}</span>'

        return (
            f'<div class="card soc-platform-card">'
            f'<div class="soc-card-header" style="border-color:{color}">'
            f'<span class="soc-platform-name">{display}</span>'
            f'<span class="soc-platform-followers">{fmt(f_now)} {gain_html}</span>'
            f'</div>'
            f'<div class="soc-stat-grid">'
            f'<div class="soc-stat"><div class="soc-stat-label">Impressions</div><div class="soc-stat-val">{fmt(imp)}</div></div>'
            f'<div class="soc-stat"><div class="soc-stat-label">Engagements</div><div class="soc-stat-val">{fmt(eng)}</div></div>'
            f'<div class="soc-stat"><div class="soc-stat-label">Posts</div><div class="soc-stat-val">{int(posts) if posts else "—"}</div></div>'
            f'<div class="soc-stat"><div class="soc-stat-label">ER</div><div class="soc-stat-val">{fmt(er, pct=True) if er else "—"}</div></div>'
            f'<div class="soc-stat" style="grid-column:span 2"><div class="soc-stat-label">Top Post Views</div><div class="soc-stat-val">{fmt(top_post)}</div></div>'
            f'</div></div>'
        )

    socials_platform_cards = ''.join(soc_platform_card(p) for p in soc_platforms)

    # Socials data table — platform × metric × month
    def socials_table_html():
        if not soc_M_raw:
            return '<div class="reports-empty">No socials data yet — run build_socials.py to add months.</div>'

        # Reverse for display: newest leftmost
        display_months = list(reversed(soc_M_display))

        METRIC_DISPLAY = [
            ('FOLLOWERS', 'Followers', 'int'),
            ('FOLLOWER_GAIN', 'Net Gain', 'int'),
            ('POSTS', 'Posts', 'int'),
            ('IMPRESSIONS', 'Impressions', 'int'),
            ('VIEWS', 'Views', 'int'),
            ('ENGAGEMENTS', 'Engagements', 'int'),
            ('ENGAGEMENT_RATE', 'ER', 'pct'),
            ('TOP_POST_VIEWS', 'Top Post', 'int'),
        ]

        sections_html = ''
        for platform in soc_platforms:
            color = PLATFORM_COLORS.get(platform, '#6B7280')
            display = PLATFORM_DISPLAY.get(platform, platform.title())
            rows_html = ''
            for metric_key, metric_label, fmt_type in METRIC_DISPLAY:
                series = list(reversed(soc_series(platform, metric_key)))
                if not any(v for v in series if v):
                    continue
                cells = ''
                for v in series:
                    if v is None or (isinstance(v, str) and v in ('TBD', 'N/A')):
                        cells += '<td><span class="na">—</span></td>'
                    elif fmt_type == 'pct' and isinstance(v, (int, float)):
                        cells += f'<td>{v*100:.2f}%</td>'
                    elif isinstance(v, (int, float)):
                        cells += f'<td>{int(v):,}</td>'
                    else:
                        cells += f'<td>{v}</td>'
                rows_html += f'<tr><td>{metric_label}</td>{cells}</tr>'

            if rows_html:
                header = f'<tr><th colspan="{len(display_months) + 1}" class="soc-platform-header" style="border-color:{color}">{display}</th></tr>'
                month_row = '<tr><th>Metric</th>' + ''.join(f'<th>{m}</th>' for m in display_months) + '</tr>'
                sections_html += (
                    f'<table class="data-table socials-table">'
                    f'<thead>{header}{month_row}</thead><tbody>{rows_html}</tbody></table>'
                )

        return f'<div class="table-scroll">{sections_html}</div>' if sections_html else '<div class="reports-empty">No socials data populated yet.</div>'

    socials_table = socials_table_html()

    # Socials JS data
    js_soc_m = jsa(soc_M_display)
    # Followers per platform (line chart)
    soc_followers_ds = []
    for p in soc_platforms:
        soc_followers_ds.append({
            'label': PLATFORM_DISPLAY.get(p, p.title()),
            'data': [v if isinstance(v, (int, float)) else None for v in soc_series(p, 'FOLLOWERS')],
            'borderColor': PLATFORM_COLORS.get(p, '#6B7280'),
            'backgroundColor': PLATFORM_COLORS.get(p, '#6B7280') + '15',
            'tension': .3, 'pointRadius': 2, 'borderWidth': 2,
        })
    js_soc_followers_ds = json.dumps(soc_followers_ds)

    # Impressions per platform (stacked bar)
    soc_imp_ds = []
    for p in soc_platforms:
        vals = [v if isinstance(v, (int, float)) else None for v in soc_series(p, 'IMPRESSIONS')]
        if any(v for v in vals if v):
            soc_imp_ds.append({
                'label': PLATFORM_DISPLAY.get(p, p.title()),
                'data': vals,
                'backgroundColor': PLATFORM_COLORS.get(p, '#6B7280'),
                'borderRadius': 2, 'stack': 's',
            })
    js_soc_imp_ds = json.dumps(soc_imp_ds)

    # Engagement Rate per platform (line)
    soc_er_ds = []
    for p in soc_platforms:
        vals = [v if isinstance(v, (int, float)) else None for v in soc_series(p, 'ENGAGEMENT_RATE')]
        if any(v for v in vals if v):
            soc_er_ds.append({
                'label': PLATFORM_DISPLAY.get(p, p.title()),
                'data': vals,
                'borderColor': PLATFORM_COLORS.get(p, '#6B7280'),
                'backgroundColor': 'transparent',
                'tension': .3, 'pointRadius': 2, 'borderWidth': 2, 'fill': False,
            })
    js_soc_er_ds = json.dumps(soc_er_ds)

    soc_legend = ''.join(
        f'<span class="legend-item"><span class="leg-dot" style="background:{PLATFORM_COLORS.get(p, "#6B7280")}"></span>{PLATFORM_DISPLAY.get(p, p.title())}</span>'
        for p in soc_platforms
    )

    socials_subtitle = (
        f"{fmt_period(soc_M_raw[0])} – {soc_latest_label} · {len(soc_platforms)} platforms"
        if soc_M_raw else "No socials data yet — run build_socials.py to add months"
    )

    # JS data for revenue charts
    js_rev_m = jsa(rev_M_display)
    js_rev_totals = jsa([round(t, 2) if t else None for t in rev_totals_raw])
    js_rev_yt_videos = jsa(yt_videos_data)
    js_rev_yt_shorts = jsa(yt_shorts_data)
    js_rev_yt_lives = jsa(yt_lives_data)
    js_rev_stacked_ds = json.dumps(stacked_ds)
    js_rev_mix_labels = jsa(mix_labels)
    js_rev_mix_values = jsa(mix_values)
    js_rev_mix_colors = jsa(mix_colors)

    # Top Content — pre-stored per-month, filtered in JS
    js_top_content_monthly = json.dumps(d.get('top_content_monthly', {}))

    # JS data — pass both 12-month (default) and full history
    js_M      = jsa(M12)
    js_M_full = jsa(M_full)
    js_vids   = jsa(vids12);   js_vids_f   = jsa(vids_full)
    js_shorts = jsa(shorts12); js_shorts_f = jsa(shorts_full)
    js_lives  = jsa(lives12);  js_lives_f  = jsa(lives_full)
    js_subs   = jsa(subs12);   js_subs_f   = jsa(subs_full)
    js_ltotal = jsa(ltotal12); js_ltotal_f = jsa(ltotal_full)
    js_lstrm  = jsa(lstrm12);  js_lstrm_f  = jsa(lstrm_full)
    js_perep  = jsa(perep12);  js_perep_f  = jsa(perep_full)
    js_nsht   = jsa(nsht12);   js_nsht_f   = jsa(nsht_full)
    js_pctsht = jsa(pctsht12); js_pctsht_f = jsa(pctsht_full)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Road Trippin' — Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ─────────────────────────────────────────────────────────────
   ROAD TRIPPIN' DASHBOARD — Rain Delay Media brand styling
   Brand color: #2F6DDE (logo blue)
   Aesthetic:   Clean, modern, professional — bright accents on
                a soft neutral background, plenty of whitespace.
   ───────────────────────────────────────────────────────────── */
:root{{
  /* Brand */
  --brand:        #2F6DDE;            /* Rain Delay blue */
  --brand-deep:   #1F4FA8;            /* Hover/pressed */
  --brand-soft:   rgba(47,109,222,.08);
  --brand-tint:   rgba(47,109,222,.16);

  /* Surfaces */
  --bg:           #f7f8fb;            /* Page bg — cool tinted white */
  --surface:      #ffffff;            /* Cards */
  --surface2:     #eef1f7;            /* Hover / row stripe */
  --surface3:     #dde3ee;            /* Section header */

  /* Borders */
  --border:       rgba(20,30,55,.08);
  --border2:      rgba(20,30,55,.16);

  /* Text */
  --text:         #0f1729;            /* Near-black with blue undertone */
  --text2:        #4a5468;
  --text3:        #8a93a6;

  /* Functional accents */
  --green:        #1B7A3A;
  --green-soft:   rgba(27,122,58,.10);
  --red:          #BC2E3A;
  --amber:        #E08C2A;
  --teal:         #1B9B96;
  --pink:         #DD4B5C;
  --gray:         #6b7280;

  /* Chart palette — coordinated, brand-led */
  --c-blue:       #2F6DDE;            /* Brand blue */
  --c-green:      #1B7A3A;
  --c-amber:      #E08C2A;
  --c-violet:     #7C5BD8;
  --c-coral:      #DD4B5C;
  --c-teal:       #1B9B96;
  --c-gold:       #C9A84C;
  --c-slate:      #6B7280;

  /* Radii / sizing */
  --r:            10px;
  --rsm:          6px;
  --rlg:          14px;
  --shadow-sm:    0 1px 2px rgba(15,23,41,.04);
  --shadow:       0 1px 3px rgba(15,23,41,.06), 0 1px 2px rgba(15,23,41,.04);
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px}}

/* ── Shell layout ── */
.shell{{display:flex;height:100vh;overflow:hidden}}

/* ── Sidebar ── */
.sidebar{{
  width:212px; min-width:212px;
  background:var(--surface);
  border-right:1px solid var(--border);
  display:flex; flex-direction:column;
  padding:0;
}}
.sidebar-logo{{
  padding:18px 18px 18px;
  border-bottom:1px solid var(--border);
  display:flex; align-items:center; gap:10px;
}}
.logo-mark{{
  width:32px; height:32px; flex-shrink:0;
  background:var(--brand);
  border-radius:7px;
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:700; font-size:11px;
  letter-spacing:-.02em;
  box-shadow:0 2px 4px rgba(47,109,222,.25);
}}
.logo-text{{display:flex;flex-direction:column;line-height:1.15}}
.logo-main{{font-size:14px;font-weight:600;letter-spacing:-.3px;color:var(--text)}}
.logo-sub{{font-size:11px;color:var(--text3);margin-top:1px;font-weight:400}}

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
.nav-item.active{{
  background:var(--brand-soft);
  color:var(--brand);
  font-weight:500;
}}
.nav-item.active::before{{
  content:''; position:absolute; left:-10px; top:6px; bottom:6px;
  width:3px; background:var(--brand); border-radius:0 2px 2px 0;
}}
.nav-icon{{width:15px;height:15px;opacity:.55;flex-shrink:0}}
.nav-item.active .nav-icon{{opacity:1;color:var(--brand)}}
.sidebar-footer{{
  padding:14px 18px;
  border-top:1px solid var(--border);
  font-size:11px; color:var(--text3);
  font-family:'DM Mono',monospace;
}}

/* ── Main ── */
.main{{flex:1;overflow-y:auto;overflow-x:hidden;background:var(--bg)}}
.page{{display:none;padding:28px 32px 80px;max-width:1400px}}
.page.active{{display:block}}
.page-header{{margin-bottom:22px;padding-bottom:18px;border-bottom:1px solid var(--border)}}
.page-title{{font-size:22px;font-weight:600;letter-spacing:-.5px;color:var(--text)}}
.page-sub{{font-size:13px;color:var(--text2);margin-top:4px}}

/* ── Metric cards ── */
.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:18px}}
.metric{{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:var(--r);
  padding:14px 16px;
  transition:border-color .15s, box-shadow .15s;
}}
.metric:hover{{border-color:var(--border2);box-shadow:var(--shadow-sm)}}
.metric-label{{
  font-size:11px; text-transform:uppercase; letter-spacing:.08em;
  color:var(--text3); margin-bottom:8px; font-weight:600;
}}
.metric-value{{
  font-size:24px; font-weight:600;
  letter-spacing:-.6px; line-height:1;
  color:var(--text);
}}
.metric-delta{{font-size:11px;margin-top:6px;color:var(--text2);font-weight:500}}
.up{{color:var(--green)}}
.down{{color:var(--red)}}

/* ── Card grid ── */
.grid-2{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;margin-bottom:14px}}
.card{{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:var(--r);
  padding:18px 20px;
  min-width:0;
  transition:box-shadow .15s;
}}
.card:hover{{box-shadow:var(--shadow-sm)}}
.card-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:12px}}
.card-title{{font-size:13px;font-weight:600;color:var(--text)}}
.card-sub{{font-size:11px;color:var(--text3);font-weight:500}}
.mb12{{margin-bottom:12px}}

/* ── Chart containers ──
   .chart-outer: fixed height window that scrolls on x
   inner div: wide enough for all bars, height fills outer completely
   canvas: fills inner div — Chart.js sees a real pixel size */
.chart-outer{{
  overflow-x:auto; overflow-y:hidden;
  width:100%; height:220px;
  -webkit-overflow-scrolling:touch;
  scrollbar-width:thin; scrollbar-color:rgba(0,0,0,.12) transparent;
  cursor:grab;
}}
.chart-outer:active{{cursor:grabbing}}
.chart-outer::-webkit-scrollbar{{height:4px}}
.chart-outer::-webkit-scrollbar-track{{background:transparent}}
.chart-outer::-webkit-scrollbar-thumb{{background:rgba(0,0,0,.15);border-radius:2px}}
.chart-outer-lg{{
  overflow-x:auto; overflow-y:hidden;
  width:100%; height:260px;
  -webkit-overflow-scrolling:touch;
  scrollbar-width:thin; scrollbar-color:rgba(0,0,0,.12) transparent;
  cursor:grab;
}}
.chart-outer-lg:active{{cursor:grabbing}}
.chart-outer-lg::-webkit-scrollbar{{height:4px}}
.chart-outer-lg::-webkit-scrollbar-track{{background:transparent}}
.chart-outer-lg::-webkit-scrollbar-thumb{{background:rgba(0,0,0,.15);border-radius:2px}}

/* ── Legend ── */
.legend{{display:flex;gap:14px;flex-wrap:wrap;margin-bottom:10px}}
.legend-item{{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--text2)}}
.leg-dot{{width:12px;height:4px;border-radius:2px;display:inline-block}}

/* ── Tab toggle ── */
.tabs{{display:flex;gap:4px}}
.tab-btn{{font-size:11px;font-family:'DM Sans',sans-serif;padding:3px 9px;border-radius:var(--rsm);border:.5px solid var(--border);background:transparent;color:var(--text2);cursor:pointer}}
.expand-btn{{
  font-size:13px; padding:3px 7px;
  border-radius:var(--rsm); border:1px solid var(--border);
  background:transparent; color:var(--text3); cursor:pointer;
  transition:all .15s; line-height:1;
}}
.expand-btn:hover{{background:var(--brand-soft);color:var(--brand);border-color:var(--brand)}}
.tab-btn.on{{background:var(--surface2);color:var(--text);border-color:var(--border2)}}

/* ── Platform bars ── */
.plat-row{{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border)}}
.plat-row:last-child{{border-bottom:none}}
.plat-name{{font-size:12px;min-width:96px;color:var(--text2)}}
.plat-bar-bg{{flex:1;height:6px;background:var(--surface2);border-radius:3px;overflow:hidden}}
.plat-bar{{height:100%;border-radius:3px;transition:width .3s}}
.plat-val{{font-size:11px;font-family:'DM Mono',monospace;min-width:50px;text-align:right;color:var(--text)}}

/* ── Tracker tab ── */
.tracker-section{{margin-bottom:24px}}
.tracker-section-title{{
  font-size:13px; font-weight:600; color:var(--text);
  margin-bottom:10px; padding-bottom:10px;
  border-bottom:1px solid var(--border2);
  letter-spacing:-.1px;
}}
.table-scroll{{overflow-x:auto;scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.1) transparent}}
.table-scroll::-webkit-scrollbar{{height:4px}}
.table-scroll::-webkit-scrollbar-thumb{{background:rgba(0,0,0,.1);border-radius:2px}}
.data-table{{border-collapse:collapse;font-size:12px;font-family:'DM Mono',monospace;white-space:nowrap}}
.data-table th{{
  background:var(--surface2); padding:7px 12px;
  text-align:right; font-weight:600; font-size:10px;
  color:var(--text2); border:1px solid var(--border);
  text-transform:uppercase; letter-spacing:.06em;
  white-space:nowrap; position:sticky; top:0; z-index:2;
}}
.data-table th:first-child{{text-align:left;position:sticky;left:0;z-index:3;background:var(--surface2);min-width:150px}}
.data-table td{{padding:6px 12px;text-align:right;border:.5px solid var(--border)}}
.data-table td:first-child{{text-align:left;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:500;color:var(--text2);position:sticky;left:0;background:var(--surface);z-index:1;min-width:150px}}
.data-table tr:nth-child(even) td{{background:rgba(20,30,55,.02)}}
.data-table tr:nth-child(even) td:first-child{{background:#f8f9fc}}
.na{{color:var(--text3)}}
/* Revenue table section header style */
.revenue-table th.section-label{{
  background:var(--surface3); color:var(--text); font-weight:600;
  font-size:10px; letter-spacing:.06em; padding:5px 12px;
  border-bottom:1px solid var(--border2);
}}
.revenue-table th.section-label-cell{{background:var(--surface);border:none;position:sticky;left:0;z-index:3}}
.revenue-table tr.total-row td{{
  background:var(--surface2)!important; border-top:1px solid var(--border2);
  font-family:'DM Mono',monospace;
}}
.revenue-table tr.total-row td:first-child{{font-family:'DM Sans',sans-serif;background:var(--surface2)!important}}

/* ── Reports tab ── */
.reports-section{{margin-bottom:28px}}
.reports-section-title{{font-size:13px;font-weight:600;margin-bottom:12px;padding-bottom:8px;border-bottom:.5px solid var(--border2)}}
.reports-empty{{font-size:13px;color:var(--text3);padding:16px;background:var(--surface);border:.5px solid var(--border);border-radius:var(--r)}}
.reports-empty code{{font-family:'DM Mono',monospace;font-size:12px;background:var(--surface2);padding:2px 6px;border-radius:4px}}
.report-cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}}
.report-card{{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:var(--r);
  padding:14px 16px;
  display:flex; align-items:center; gap:12px;
  cursor:pointer;
  transition:all .15s;
}}
.report-card:hover{{
  border-color:var(--brand);
  background:var(--brand-soft);
  transform:translateY(-1px);
  box-shadow:var(--shadow);
}}
.report-icon{{font-size:22px;flex-shrink:0}}
.report-info{{flex:1;min-width:0}}
.report-label{{font-size:13px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.report-filename{{font-size:11px;color:var(--text3);font-family:'DM Mono',monospace;margin-top:2px}}
.report-arrow{{font-size:16px;color:var(--text3);transition:transform .15s}}
.report-card:hover .report-arrow{{color:var(--brand);transform:translateX(2px)}}

/* chart-inner / chart-inner-wrap: sized by JS prep() */
.chart-inner, .chart-inner-wrap {{
  display:block; height:100%; position:relative;
}}
.chart-inner canvas, .chart-inner-wrap canvas {{
  display:block; width:100% !important; height:100% !important;
}}

/* ── Socials page ── */
.soc-platform-grid{{
  display:grid; grid-template-columns:repeat(auto-fit, minmax(220px, 1fr));
  gap:14px; margin-bottom:18px;
}}
.soc-platform-card{{padding:0; overflow:hidden}}
.soc-card-header{{
  display:flex; justify-content:space-between; align-items:baseline;
  padding:14px 18px; border-bottom:2px solid;
}}
.soc-platform-name{{font-size:13px; font-weight:600; color:var(--text)}}
.soc-platform-followers{{
  font-size:18px; font-weight:600; letter-spacing:-.3px;
  color:var(--text); display:flex; gap:8px; align-items:baseline;
}}
.soc-stat-grid{{
  display:grid; grid-template-columns:1fr 1fr; gap:10px 16px;
  padding:14px 18px;
}}
.soc-stat-label{{
  font-size:10px; text-transform:uppercase; letter-spacing:.06em;
  color:var(--text3); margin-bottom:3px; font-weight:600;
}}
.soc-stat-val{{
  font-size:14px; font-weight:600; color:var(--text);
  font-family:'DM Mono',monospace;
}}
.socials-table{{margin-bottom:18px}}
.socials-table th.soc-platform-header{{
  background:var(--surface); color:var(--text);
  font-size:12px; font-weight:600; letter-spacing:0;
  text-transform:none; padding:10px 12px; text-align:left;
  border-left:3px solid; border-bottom:1px solid var(--border2);
}}

@media(max-width:700px){{
  .grid-2{{grid-template-columns:1fr}}
  .sidebar{{width:50px;min-width:50px}}
  .logo-main,.logo-sub,.nav-item span,.sidebar-footer{{display:none}}
  .nav-item{{justify-content:center;padding:10px}}
}}

/* ─── Top Content ─── */
.tc-controls {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap;
  margin:0 0 18px; padding:10px 14px; background:var(--surface2); border:1px solid var(--border); border-radius:8px; }}
.tc-preset {{ padding:6px 12px; border:1px solid var(--border); background:var(--surface);
  border-radius:6px; cursor:pointer; font-size:12px; color:var(--text); font-weight:500;
  transition:background .12s, color .12s, border-color .12s; }}
.tc-preset:hover {{ background:var(--surface2); border-color:var(--brand); }}
.tc-preset.active {{ background:var(--brand); color:#fff; border-color:var(--brand); }}
.tc-sep {{ width:1px; height:18px; background:var(--border); margin:0 4px; }}
.tc-label {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; color:var(--text2); }}
.tc-label select {{ padding:5px 8px; border:1px solid var(--border); background:var(--surface);
  color:var(--text); border-radius:4px; font-size:12px; font-family:inherit; cursor:pointer; }}
.tc-summary {{ color:var(--text3); font-size:11px; margin-left:auto; letter-spacing:.04em; }}
.tc-section {{ margin-bottom:24px; }}
.tc-section-h {{ font-size:13px; font-weight:600; color:var(--brand); margin:0 0 10px;
  text-transform:uppercase; letter-spacing:.1em; display:flex; align-items:center; gap:10px; }}
.tc-tag {{ font-size:10px; color:var(--text3); font-weight:500; letter-spacing:.04em; text-transform:none; }}
.tc-grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:12px; }}
.tc-card {{ background:var(--surface); border:1px solid var(--border); border-radius:6px;
  overflow:hidden; text-decoration:none; color:inherit; display:block;
  transition:transform .12s, box-shadow .12s, border-color .12s; }}
.tc-card:hover {{ transform:translateY(-2px); box-shadow:0 6px 16px rgba(0,0,0,.08); border-color:var(--brand); }}
.tc-thumb {{ aspect-ratio:16/9; width:100%; object-fit:cover; background:#222; display:block; }}
.tc-body {{ padding:10px 12px 12px; }}
.tc-rank-row {{ display:flex; align-items:baseline; gap:8px; margin-bottom:4px; }}
.tc-rank {{ font-size:17px; font-weight:700; color:var(--text2); }}
.tc-views {{ font-size:13px; font-weight:600; color:var(--brand); }}
.tc-date {{ font-size:10px; color:var(--text3); text-transform:uppercase;
  letter-spacing:.08em; margin-bottom:5px; }}
.tc-title {{ font-size:12px; line-height:1.35; font-weight:500; color:var(--text); }}
.tc-empty {{ color:var(--text3); font-size:13px; padding:24px; text-align:center;
  background:var(--surface2); border:1px dashed var(--border); border-radius:6px; }}
</style>
</head>
<body>
<div class="shell">

<nav class="sidebar">
  <div class="sidebar-logo">
    <div class="logo-mark">RD</div>
    <div class="logo-text">
      <div class="logo-main">Road Trippin'</div>
      <div class="logo-sub">Rain Delay Media</div>
    </div>
  </div>
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
    <div class="nav-item" onclick="showPage('audio',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="8" r="2.5" fill="currentColor"/></svg>
      <span>Audio</span>
    </div>
    <div class="nav-item" onclick="showPage('socials',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M5 7a2 2 0 100-4 2 2 0 000 4zm6 6a2 2 0 100-4 2 2 0 000 4zm0-10a2 2 0 100 4 2 2 0 000-4zM6.6 8.5l3 2.5M9.4 5l-3 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
      <span>Socials</span>
    </div>
    <div class="nav-item" onclick="showPage('revenue',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M5 5h4.5a1.5 1.5 0 010 3h-3a1.5 1.5 0 000 3H11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <span>Revenue</span>
    </div>
    <div class="nav-item" onclick="showPage('top-content',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M2 4h12M2 8h12M2 12h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="14" cy="12" r="1.5" stroke="currentColor" stroke-width="1.3"/></svg>
      <span>Top Content</span>
    </div>
    <div class="nav-section" style="margin-top:14px">Resources</div>
    <div class="nav-item" onclick="showPage('tracker',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><rect x="1" y="1" width="14" height="14" rx="2" stroke="currentColor" stroke-width="1.5"/><path d="M1 5h14M5 5v10" stroke="currentColor" stroke-width="1.2"/></svg>
      <span>Tracker</span>
    </div>
    <div class="nav-item" onclick="showPage('reports',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M3 2h7l3 3v9a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" stroke-width="1.4"/><path d="M10 2v3h3M5 8h6M5 11h4" stroke="currentColor" stroke-width="1.2"/></svg>
      <span>Reports</span>
    </div>
  </div>
  <div class="sidebar-footer">Updated {generated_at}</div>
</nav>

<div class="main">

<!-- ═══ OVERVIEW ═══ -->
<div class="page active" id="page-overview">
  <div class="page-header">
    <div class="page-title">Overview</div>
    <div class="page-sub">All platforms · {M[0] if M else ''} – {latest_mo}</div>
  </div>

  <div class="metrics">
    <div class="metric">
      <div class="metric-label">YT Subscribers</div>
      <div class="metric-value">{fmt(yt_subs_now)}</div>
      <div class="metric-delta">{delta_str(d['yt_subs'])}</div>
    </div>
    <div class="metric">
      <div class="metric-label">YT Views ({latest_mo})</div>
      <div class="metric-value">{fmt(sum(filter(None,[latest(d['vids']),latest(d['shorts']),latest(d['lives'])])))}</div>
      <div class="metric-delta">{delta_str([sum(x or 0 for x in t) for t in zip(d['vids'],d['shorts'],d['lives'])])}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Audio ({latest_mo})</div>
      <div class="metric-value">{fmt(listens_now)}</div>
      <div class="metric-delta">{delta_str(d['l_total'])}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Episodes ({latest_mo})</div>
      <div class="metric-value">{eps_now}</div>
      <div class="metric-delta" style="color:var(--text2)">published</div>
    </div>
    <div class="metric">
      <div class="metric-label">Shorts % ({latest_mo})</div>
      <div class="metric-value">{fmt(pct_sht_now, pct=True)}</div>
      <div class="metric-delta" style="color:var(--text2)">of total views</div>
    </div>
  </div>

  <div class="card mb12">
    <div class="card-header">
      <span class="card-title">YouTube views by content type</span>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="expand-btn" onclick="openHistory('ov', 'YouTube views by content type')" title="View full history">↗</button>
        <div class="tabs">
          <button class="tab-btn on" onclick="switchOv('stacked',this)">Stacked</button>
          <button class="tab-btn" onclick="switchOv('line',this)">Total</button>
        </div>
      </div>
    </div>
    <div class="legend">
      <span class="legend-item"><span class="leg-dot" style="background:#2F6DDE"></span>Videos</span>
      <span class="legend-item"><span class="leg-dot" style="background:#1B9B96"></span>Shorts</span>
      <span class="legend-item"><span class="leg-dot" style="background:#E08C2A"></span>Lives</span>
    </div>
    <div class="chart-outer-lg" id="ov-stacked-outer">
      <div style="position:relative;width:{chart_px}px;height:100%">
        <canvas id="ovStacked"></canvas>
      </div>
    </div>
    <div class="chart-outer-lg" id="ov-line-outer" style="display:none">
      <div style="position:relative;width:{chart_px}px;height:100%">
        <canvas id="ovLine"></canvas>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <div class="card-header"><span class="card-title">Subscriber growth</span><span class="card-sub">YouTube</span><button class="expand-btn" onclick="openHistory('subs','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px">
        <div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ovSubs"></canvas></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Platform reach</span><span class="card-sub">Current snapshot</span></div>
      {platform_bars}
    </div>
  </div>
</div>

<!-- ═══ YOUTUBE ═══ -->
<div class="page" id="page-youtube">
  <div class="page-header"><div class="page-title">YouTube</div><div class="page-sub">Views, subscribers, content type breakdown · {M[0] if M else ''} – {latest_mo}</div></div>
  <div class="grid-2 mb12">
    <div class="card">
      <div class="card-header"><span class="card-title">Videos (VOD)</span><span class="card-sub">Monthly views</span></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytVids"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Shorts</span><span class="card-sub">Monthly views</span></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytShorts"></canvas></div></div>
    </div>
  </div>
  <div class="grid-2 mb12">
    <div class="card">
      <div class="card-header"><span class="card-title">Lives</span><span class="card-sub">Monthly views</span></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytLives"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Subscribers</span><span class="card-sub">Running total</span></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytSubsLine"></canvas></div></div>
    </div>
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="card-header"><span class="card-title">Shorts % of views</span></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytPct"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title"># of Shorts published</span></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytNSht"></canvas></div></div>
    </div>
  </div>
</div>

<!-- ═══ AUDIO ═══ -->
<div class="page" id="page-audio">
  <div class="page-header"><div class="page-title">Audio</div><div class="page-sub">Megaphone downloads, streams, per-episode performance</div></div>
  <div class="metrics">
    <div class="metric">
      <div class="metric-label">Downloads ({latest_mo})</div>
      <div class="metric-value">{fmt(listens_now)}</div>
      <div class="metric-delta">{delta_str(d['l_total'])}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Streams ({latest_mo})</div>
      <div class="metric-value">{fmt(streams_now)}</div>
      <div class="metric-delta" style="color:var(--text2)">Spotify + Apple</div>
    </div>
    <div class="metric">
      <div class="metric-label">Per-ep ({latest_mo})</div>
      <div class="metric-value">{fmt(latest(d['l_perep']))}</div>
      <div class="metric-delta" style="color:var(--text2)">{eps_now} eps</div>
    </div>
  </div>
  <div class="card mb12">
    <div class="card-header"><span class="card-title">Total downloads</span><span class="card-sub">Megaphone</span><button class="expand-btn" onclick="openHistory('audio','')" title="Full history">↗</button></div>
    <div class="chart-outer-lg" style="height:260px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="audioTotal"></canvas></div></div>
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="card-header"><span class="card-title">Streams</span><span class="card-sub">Spotify + Apple</span><button class="expand-btn" onclick="openHistory('streams','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="audioStrm"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Per-episode listens</span><button class="expand-btn" onclick="openHistory('perep','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="audioPerEp"></canvas></div></div>
    </div>
  </div>
</div>

<!-- ═══ SOCIALS ═══ -->
<div class="page" id="page-socials">
  <div class="page-header">
    <div class="page-title">Socials</div>
    <div class="page-sub">{socials_subtitle}</div>
  </div>

  <div class="metrics">
    {socials_metrics_html}
  </div>

  <div class="soc-platform-grid">
    {socials_platform_cards}
  </div>

  <div class="card mb12">
    <div class="card-header">
      <span class="card-title">Follower growth by platform</span>
      <span class="card-sub">monthly snapshot</span>
    </div>
    <div class="legend">{soc_legend}</div>
    <div class="chart-outer-lg" style="height:260px">
      <div style="position:relative;width:{soc_chart_px}px;height:100%"><canvas id="socFollowers"></canvas></div>
    </div>
  </div>

  <div class="grid-2 mb12">
    <div class="card">
      <div class="card-header"><span class="card-title">Impressions by platform</span><span class="card-sub">stacked monthly</span></div>
      <div class="chart-outer" style="height:220px">
        <div style="position:relative;width:{soc_chart_px}px;height:100%"><canvas id="socImpressions"></canvas></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Engagement rate</span><span class="card-sub">per platform</span></div>
      <div class="chart-outer" style="height:220px">
        <div style="position:relative;width:{soc_chart_px}px;height:100%"><canvas id="socER"></canvas></div>
      </div>
    </div>
  </div>

  <div class="tracker-section">
    <div class="tracker-section-title">📱 Per-platform breakdown</div>
    {socials_table}
  </div>
</div>

<!-- ═══ REVENUE ═══ -->
<div class="page" id="page-revenue">
  <div class="page-header">
    <div class="page-title">Revenue</div>
    <div class="page-sub">{revenue_subtitle}</div>
  </div>

  <div class="metrics">
    {revenue_metrics}
  </div>

  <div class="card mb12">
    <div class="card-header">
      <span class="card-title">Total revenue by month</span>
      <div class="tabs">
        <button class="tab-btn on" onclick="switchRev('total',this)">Total</button>
        <button class="tab-btn" onclick="switchRev('stacked',this)">By source</button>
      </div>
    </div>
    <div class="legend" id="rev-legend" style="display:none">
      {revenue_legend}
    </div>
    <div class="chart-outer-lg" style="height:260px" id="rev-total-outer">
      <div style="position:relative;width:{rev_chart_px}px;height:100%"><canvas id="revTotal"></canvas></div>
    </div>
    <div class="chart-outer-lg" style="height:260px" id="rev-stacked-outer" style="display:none">
      <div style="position:relative;width:{rev_chart_px}px;height:100%"><canvas id="revStacked"></canvas></div>
    </div>
  </div>

  <div class="grid-2 mb12">
    <div class="card">
      <div class="card-header"><span class="card-title">Source mix</span><span class="card-sub">Last 12 months</span></div>
      <div style="position:relative;height:220px;width:100%"><canvas id="revMix"></canvas></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">YouTube AdSense</span><span class="card-sub">Videos + Shorts + Lives</span></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{rev_chart_px}px;height:100%"><canvas id="revYT"></canvas></div></div>
    </div>
  </div>

  <div class="tracker-section">
    <div class="tracker-section-title">💲 Revenue Breakdown</div>
    {revenue_table}
  </div>
</div>

<!-- ═══ TRACKER ═══ -->
<div class="page" id="page-tracker">
  <div class="page-header">
    <div class="page-title">Tracker</div>
    <div class="page-sub">Full data export · {M[0] if M else ''} – {latest_mo} · oldest left, newest right</div>
  </div>
  {tracker_tables}
</div>

<!-- ═══ TOP CONTENT ═══ -->
<div class="page" id="page-top-content">
  <div class="page-header">
    <div class="page-title">Top Content</div>
    <div class="page-sub">Best performing videos by lifetime views · filter by publish range</div>
  </div>

  <div class="tc-controls">
    <button class="tc-preset" data-range="30">Last 30d</button>
    <button class="tc-preset" data-range="90">Last 90d</button>
    <button class="tc-preset" data-range="ytd">YTD</button>
    <button class="tc-preset active" data-range="all">All time</button>
    <span class="tc-sep"></span>
    <label class="tc-label">From <select id="tc-start"></select></label>
    <label class="tc-label">To <select id="tc-end"></select></label>
    <span class="tc-summary" id="tc-summary"></span>
  </div>

  <div class="tc-section">
    <div class="tc-section-h">★ Top Full Episodes <span class="tc-tag">&gt;30 min</span></div>
    <div class="tc-grid" id="tc-long"></div>
  </div>

  <div class="tc-section">
    <div class="tc-section-h">★ Top Clips <span class="tc-tag">3–30 min</span></div>
    <div class="tc-grid" id="tc-mid"></div>
  </div>

  <div class="tc-section">
    <div class="tc-section-h">★ Top Shorts <span class="tc-tag">≤3 min</span></div>
    <div class="tc-grid" id="tc-short"></div>
  </div>
</div>

<!-- ═══ REPORTS ═══ -->
<div class="page" id="page-reports">
  <div class="page-header">
    <div class="page-title">Reports</div>
    <div class="page-sub">Fanatics delivery reports and revenue summaries</div>
  </div>
  {reports_content}
</div>

</div><!-- /main -->
</div><!-- /shell -->

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
// 12-month view (default) + full history
const M12   = {js_M};       const M_FULL = {js_M_full};
const VIDS12={js_vids};     const VIDS_F ={js_vids_f};
const SH12  ={js_shorts};   const SH_F   ={js_shorts_f};
const LV12  ={js_lives};    const LV_F   ={js_lives_f};
const SUBS12={js_subs};     const SUBS_F ={js_subs_f};
const LT12  ={js_ltotal};   const LT_F   ={js_ltotal_f};
const LS12  ={js_lstrm};    const LS_F   ={js_lstrm_f};
const PE12  ={js_perep};    const PE_F   ={js_perep_f};
const NS12  ={js_nsht};     const NS_F   ={js_nsht_f};
const PS12  ={js_pctsht};   const PS_F   ={js_pctsht_f};

let M = M12, VIDS=VIDS12, SHORTS=SH12, LIVES=LV12, SUBS=SUBS12;
let LTOTAL=LT12, LSTRM=LS12, PEREP=PE12, NSHT=NS12, PCTSHT=PS12;

// Revenue data
const REV_M = {js_rev_m};
const REV_TOTALS = {js_rev_totals};
const REV_YT_VIDEOS = {js_rev_yt_videos};
const REV_YT_SHORTS = {js_rev_yt_shorts};
const REV_YT_LIVES = {js_rev_yt_lives};
const REV_STACKED_DS = {js_rev_stacked_ds};
const REV_MIX_LABELS = {js_rev_mix_labels};
const REV_MIX_VALUES = {js_rev_mix_values};
const REV_MIX_COLORS = {js_rev_mix_colors};

// Socials data
const SOC_M = {js_soc_m};
const SOC_FOLLOWERS_DS = {js_soc_followers_ds};
const SOC_IMP_DS = {js_soc_imp_ds};
const SOC_ER_DS = {js_soc_er_ds};

const gc = 'rgba(20,30,55,.06)', tc = '#8a93a6';
const nn = a => a.map(v => v === null ? NaN : v);

function CW() {{ return Math.max(M.length * 46, 500); }}

// Toggle between 12-month and full history — rebuilds all charts
// ── History drawer ──────────────────────────────────────────────
// Each chart has an ↗ button that opens a full-width drawer below
// the page content showing the full 22-month history.
let _historyChart = null;

const HISTORY_CONFIGS = {{
  ov: {{
    label: 'YouTube views by content type',
    type: 'bar',
    datasets: () => [
      {{ label: 'Videos', data: nn(VIDS_F), backgroundColor: '#2F6DDE', borderRadius: 2, stack: 's' }},
      {{ label: 'Shorts', data: nn(SH_F),   backgroundColor: '#1B9B96', borderRadius: 2, stack: 's' }},
      {{ label: 'Lives',  data: nn(LV_F),   backgroundColor: '#E08C2A', borderRadius: 2, stack: 's' }},
    ],
    stacked: true,
  }},
  subs: {{
    label: 'YouTube subscriber growth',
    type: 'line',
    datasets: () => [{{ data: nn(SUBS_F), borderColor: '#2F6DDE', backgroundColor: 'rgba(47,109,222,.08)', fill: true, tension: .3, pointRadius: 2 }}],
  }},
  audio: {{
    label: 'Total downloads — full history',
    type: 'bar',
    datasets: () => [{{ data: nn(LT_F), backgroundColor: '#1B7A3A', borderRadius: 2 }}],
  }},
  streams: {{
    label: 'Streams — full history',
    type: 'bar',
    datasets: () => [{{ data: nn(LS_F), backgroundColor: '#1B9B96', borderRadius: 2 }}],
  }},
  perep: {{
    label: 'Per-episode listens — full history',
    type: 'line',
    datasets: () => [{{ data: nn(PE_F), borderColor: '#1B7A3A', backgroundColor: 'rgba(27,122,58,.08)', fill: true, tension: .3, pointRadius: 2 }}],
  }},
}};

function openHistory(key, title) {{
  const drawer = document.getElementById('history-drawer');
  const titleEl = document.getElementById('history-title');
  const cfg = HISTORY_CONFIGS[key];
  if (!cfg) return;

  titleEl.textContent = cfg.label || title;
  drawer.style.display = 'block';
  drawer.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});

  // Destroy previous chart
  if (_historyChart) {{ _historyChart.destroy(); _historyChart = null; }}

  const canvas = document.getElementById('history-canvas');
  const wrap = canvas.parentElement;
  wrap.style.width = Math.max(M_FULL.length * 46, 700) + 'px';
  wrap.style.height = '100%';

  const o = opts(false);
  if (cfg.stacked) {{ o.scales.x.stacked = true; o.scales.y.stacked = true; }}
  o.plugins.legend = {{ display: true, position: 'top',
    labels: {{ color: tc, font: {{ size: 11 }}, boxWidth: 12 }} }};

  _historyChart = new Chart(canvas, {{
    type: cfg.type,
    data: {{ labels: M_FULL, datasets: cfg.datasets() }},
    options: o,
  }});
}}

function closeHistory() {{
  const drawer = document.getElementById('history-drawer');
  drawer.style.display = 'none';
  if (_historyChart) {{ _historyChart.destroy(); _historyChart = null; }}
}}

// Set inner wrapper to explicit px width so Chart.js measures correctly
// chart-outer is fixed height and scrolls on x
function prep(id) {{
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  const wrap = canvas.parentElement;
  wrap.style.position = 'relative';
  wrap.style.width = CW() + 'px';
  wrap.style.height = '100%';
  return canvas;
}}

function opts(pct) {{
  return {{
    responsive: true,
    maintainAspectRatio: false,
    animation: {{ duration: 300 }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: c => {{
        const v = c.parsed.y;
        if (isNaN(v)) return ' No data';
        if (pct) return ' ' + (v*100).toFixed(1) + '%';
        return ' ' + (v>=1e6 ? (v/1e6).toFixed(2)+'M' : v>=1e3 ? (v/1e3).toFixed(0)+'K' : v.toLocaleString());
      }} }} }}
    }},
    scales: {{
      x: {{ grid: {{ color: gc }}, ticks: {{ color: tc, font: {{ size: 10 }}, maxRotation: 45, autoSkip: false }} }},
      y: {{ grid: {{ color: gc }}, ticks: {{ color: tc, font: {{ size: 10 }},
        callback: v => pct ? (v*100).toFixed(0)+'%' : v>=1e6 ? (v/1e6).toFixed(1)+'M' : v>=1e3 ? (v/1e3).toFixed(0)+'K' : v
      }} }}
    }}
  }};
}}

function mkBar(id, data, color) {{
  const c = prep(id); if (!c) return;
  new Chart(c, {{ type:'bar', data:{{ labels:M, datasets:[{{ data:nn(data), backgroundColor:color, borderRadius:2, label:'' }}] }}, options:opts(false) }});
}}

function mkLine(id, data, color, fill, pct) {{
  const c = prep(id); if (!c) return;
  new Chart(c, {{ type:'line', data:{{ labels:M, datasets:[{{ data:nn(data), borderColor:color, backgroundColor:fill, fill:true, tension:.3, pointRadius:2, pointBackgroundColor:color, label:'' }}] }}, options:opts(pct||false) }});
}}

function mkStacked(id) {{
  const c = prep(id); if (!c) return;
  const o = opts(false); o.scales.x.stacked = true; o.scales.y.stacked = true;
  new Chart(c, {{ type:'bar', data:{{ labels:M, datasets:[
    {{ label:'Videos', data:nn(VIDS), backgroundColor:'#2F6DDE', borderRadius:2, stack:'s' }},
    {{ label:'Shorts', data:nn(SHORTS), backgroundColor:'#1B9B96', borderRadius:2, stack:'s' }},
    {{ label:'Lives',  data:nn(LIVES),  backgroundColor:'#E08C2A', borderRadius:2, stack:'s' }},
  ]}}, options:o }});
}}

function initCharts() {{
  mkStacked('ovStacked');
  const totals = M.map((_,i) => (VIDS[i]||0)+(SHORTS[i]||0)+(LIVES[i]||0)||NaN);
  mkLine('ovLine', totals, '#2F6DDE', 'rgba(47,109,222,.08)');
  mkLine('ovSubs', SUBS, '#2F6DDE', 'rgba(47,109,222,.08)');
  mkBar('ytVids', VIDS, '#2F6DDE');
  mkBar('ytShorts', SHORTS, '#1B9B96');
  mkBar('ytLives', LIVES, '#E08C2A');
  mkLine('ytSubsLine', SUBS, '#2F6DDE', 'rgba(47,109,222,.08)');
  mkLine('ytPct', PCTSHT, '#E08C2A', 'rgba(224,140,42,.08)', true);
  mkBar('ytNSht', NSHT, '#6B7280');
  mkBar('audioTotal', LTOTAL, '#1B7A3A');
  mkBar('audioStrm', LSTRM, '#1B9B96');
  mkLine('audioPerEp', PEREP, '#1B7A3A', 'rgba(27,122,58,.08)');

  // Revenue charts
  if (typeof REV_M !== 'undefined' && REV_M.length > 0) {{
    // Total revenue line
    const rTotalC = document.getElementById('revTotal');
    if (rTotalC) {{
      const wrap = rTotalC.parentElement;
      wrap.style.cssText = 'position:relative;width:' + Math.max(REV_M.length * 46, 500) + 'px;height:100%';
      new Chart(rTotalC, {{
        type: 'line',
        data: {{ labels: REV_M, datasets: [{{ data: nn(REV_TOTALS), borderColor: '#1B7A3A',
          backgroundColor: 'rgba(27,122,58,.08)', fill: true, tension: .3,
          pointRadius: 2, pointBackgroundColor: '#1B7A3A', label: 'Total' }}] }},
        options: revOpts()
      }});
    }}

    // Stacked by source
    const rStackedC = document.getElementById('revStacked');
    if (rStackedC) {{
      const wrap = rStackedC.parentElement;
      wrap.style.cssText = 'position:relative;width:' + Math.max(REV_M.length * 46, 500) + 'px;height:100%';
      const so = revOpts(); so.scales.x.stacked = true; so.scales.y.stacked = true;
      new Chart(rStackedC, {{
        type: 'bar', data: {{ labels: REV_M, datasets: REV_STACKED_DS }}, options: so
      }});
    }}

    // Source mix doughnut
    const rMixC = document.getElementById('revMix');
    if (rMixC && REV_MIX_LABELS.length > 0) {{
      new Chart(rMixC, {{
        type: 'doughnut',
        data: {{ labels: REV_MIX_LABELS, datasets: [{{ data: REV_MIX_VALUES, backgroundColor: REV_MIX_COLORS, borderWidth: 0 }}] }},
        options: {{
          responsive: true, maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: true, position: 'right', labels: {{ font: {{ size: 11 }}, color: tc, boxWidth: 10 }} }},
            tooltip: {{ callbacks: {{ label: c => ' ' + c.label + ': $' + c.parsed.toLocaleString() }} }}
          }}
        }}
      }});
    }}

    // YouTube AdSense (V+S+L)
    const rYTC = document.getElementById('revYT');
    if (rYTC) {{
      const wrap = rYTC.parentElement;
      wrap.style.cssText = 'position:relative;width:' + Math.max(REV_M.length * 46, 500) + 'px;height:100%';
      new Chart(rYTC, {{
        type: 'bar', data: {{ labels: REV_M, datasets: [
          {{ label: 'Videos', data: nn(REV_YT_VIDEOS), backgroundColor: '#2F6DDE', borderRadius: 2, stack: 's' }},
          {{ label: 'Shorts', data: nn(REV_YT_SHORTS), backgroundColor: '#1B9B96', borderRadius: 2, stack: 's' }},
          {{ label: 'Lives',  data: nn(REV_YT_LIVES),  backgroundColor: '#E08C2A', borderRadius: 2, stack: 's' }},
        ]}}, options: (() => {{ const o = revOpts(); o.scales.x.stacked = true; o.scales.y.stacked = true; return o; }})()
      }});
    }}
  }}

  // Socials charts
  if (typeof SOC_M !== 'undefined' && SOC_M.length > 0) {{
    const SOC_W = Math.max(SOC_M.length * 46, 500);

    function socPrep(id) {{
      const c = document.getElementById(id);
      if (!c) return null;
      const wrap = c.parentElement;
      wrap.style.cssText = 'position:relative;width:' + SOC_W + 'px;height:100%';
      return c;
    }}

    function socOpts(pct) {{
      return {{
        responsive: true, maintainAspectRatio: false, animation: {{ duration: 300 }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            backgroundColor: '#0f1729', titleColor: '#fff', bodyColor: '#cbd5e1',
            padding: 10, cornerRadius: 6, boxPadding: 4,
            titleFont: {{ size: 11, weight: '600' }}, bodyFont: {{ size: 12 }},
            callbacks: {{ label: c => {{
              const v = c.parsed.y;
              if (isNaN(v)) return ' No data';
              const lbl = c.dataset.label ? c.dataset.label + ': ' : '';
              if (pct) return ' ' + lbl + (v*100).toFixed(2) + '%';
              return ' ' + lbl + (v >= 1e6 ? (v/1e6).toFixed(2)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v.toLocaleString());
            }} }}
          }}
        }},
        scales: {{
          x: {{ grid: {{ color: gc }}, ticks: {{ color: tc, font: {{ size: 10 }}, maxRotation: 45, autoSkip: false }} }},
          y: {{ grid: {{ color: gc }}, ticks: {{ color: tc, font: {{ size: 10 }},
            callback: v => pct ? (v*100).toFixed(1)+'%' : v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v
          }} }}
        }}
      }};
    }}

    // Followers line chart (multi-series)
    const fc = socPrep('socFollowers');
    if (fc) new Chart(fc, {{
      type: 'line', data: {{ labels: SOC_M, datasets: SOC_FOLLOWERS_DS }}, options: socOpts(false)
    }});

    // Impressions stacked bar
    const ic = socPrep('socImpressions');
    if (ic) {{
      const o = socOpts(false); o.scales.x.stacked = true; o.scales.y.stacked = true;
      new Chart(ic, {{ type: 'bar', data: {{ labels: SOC_M, datasets: SOC_IMP_DS }}, options: o }});
    }}

    // ER line chart (multi-series)
    const ec = socPrep('socER');
    if (ec) new Chart(ec, {{
      type: 'line', data: {{ labels: SOC_M, datasets: SOC_ER_DS }}, options: socOpts(true)
    }});
  }}
}}

function revOpts() {{
  return {{
    responsive: true, maintainAspectRatio: false, animation: {{ duration: 300 }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: '#0f1729',
        titleColor: '#fff',
        bodyColor: '#cbd5e1',
        padding: 10,
        cornerRadius: 6,
        titleFont: {{ size: 11, weight: '600' }},
        bodyFont: {{ size: 12 }},
        boxPadding: 4,
        callbacks: {{ label: c => {{
          const v = c.parsed.y;
          if (isNaN(v)) return ' No data';
          return ' ' + (c.dataset.label ? c.dataset.label + ': ' : '') + '$' + v.toLocaleString(undefined, {{minimumFractionDigits:2, maximumFractionDigits:2}});
        }} }}
      }}
    }},
    scales: {{
      x: {{ grid: {{ color: gc }}, ticks: {{ color: tc, font: {{ size: 10 }}, maxRotation: 45, autoSkip: false }} }},
      y: {{ grid: {{ color: gc }}, ticks: {{ color: tc, font: {{ size: 10 }},
        callback: v => v >= 1000 ? '$' + (v/1000).toFixed(0) + 'K' : '$' + v
      }} }}
    }}
  }};
}}

function switchRev(type, btn) {{
  const tot = document.getElementById('rev-total-outer');
  const stk = document.getElementById('rev-stacked-outer');
  const leg = document.getElementById('rev-legend');
  tot.style.display = type === 'total'   ? 'block' : 'none';
  stk.style.display = type === 'stacked' ? 'block' : 'none';
  leg.style.display = type === 'stacked' ? 'flex'  : 'none';
  document.querySelectorAll('#page-revenue .tab-btn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
}}

// Wait for full paint before initializing
if (document.readyState === 'complete') {{ initCharts(); }}
else {{ window.addEventListener('load', initCharts); }}

function showPage(id, el) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('page-'+id).classList.add('active');
  el.classList.add('active');
}}

function switchOv(type, btn) {{
  document.getElementById('ov-stacked-outer').style.display = type==='stacked' ? 'block' : 'none';
  document.getElementById('ov-line-outer').style.display   = type==='line'    ? 'block' : 'none';
  document.querySelectorAll('#page-overview .tab-btn').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
}}

function openReport(path) {{
  document.getElementById('pdf-frame').src = path;
  document.getElementById('pdf-label').textContent = path.split('/').pop().replace(/_/g,' ').replace('.pdf','');
  const v = document.getElementById('pdf-viewer');
  v.style.display = 'block';
  v.scrollIntoView({{ behavior:'smooth' }});
}}

function closePdf() {{
  document.getElementById('pdf-viewer').style.display = 'none';
  document.getElementById('pdf-frame').src = '';
}}

/* ─── Top Content: filter + render ─── */
const TC_MONTHLY = {js_top_content_monthly};
const TC_MONTHS = Object.keys(TC_MONTHLY).sort();   // ascending YYYY-MM

function tcMonthInRange(m, start, end) {{ return m >= start && m <= end; }}

function tcFilter(start, end, topN) {{
  const buckets = {{long: [], mid: [], short: []}};
  for (const m of TC_MONTHS) {{
    if (!tcMonthInRange(m, start, end)) continue;
    const data = TC_MONTHLY[m] || {{}};
    for (const t of ['long','mid','short']) {{
      (data[t] || []).forEach(v => buckets[t].push(v));
    }}
  }}
  for (const t of ['long','mid','short']) {{
    buckets[t].sort((a,b) => (b.views||0) - (a.views||0));
    buckets[t] = buckets[t].slice(0, topN);
  }}
  return buckets;
}}

function tcFmtViews(n) {{ return (n||0).toLocaleString(); }}
function tcFmtDate(iso) {{
  if (!iso) return '';
  const d = new Date(iso + 'T00:00:00');
  return d.toLocaleDateString('en-US', {{month:'short', day:'numeric', year:'numeric'}});
}}

function tcCard(v, rank) {{
  const safeTitle = (v.title || '').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  return '<a class="tc-card" href="' + (v.url || '#') + '" target="_blank" rel="noopener">' +
    '<img class="tc-thumb" src="' + (v.thumbnail || '') + '" alt="" loading="lazy">' +
    '<div class="tc-body">' +
      '<div class="tc-rank-row"><span class="tc-rank">#' + rank + '</span>' +
        '<span class="tc-views">' + tcFmtViews(v.views) + ' views</span></div>' +
      '<div class="tc-date">' + tcFmtDate(v.published) + '</div>' +
      '<div class="tc-title">' + safeTitle + '</div>' +
    '</div></a>';
}}

function tcRender(start, end) {{
  const b = tcFilter(start, end, 10);
  for (const t of ['long','mid','short']) {{
    const el = document.getElementById('tc-' + t);
    if (!el) continue;
    el.innerHTML = b[t].length
      ? b[t].map((v, i) => tcCard(v, i + 1)).join('')
      : '<div class="tc-empty">No content published in this range</div>';
  }}
  const total = b.long.length + b.mid.length + b.short.length;
  const sum = document.getElementById('tc-summary');
  if (sum) sum.textContent = start + ' → ' + end + ' · ' + total + ' shown';
}}

function tcMonthsBack(n) {{
  const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - n);
  return d.toISOString().slice(0, 7);
}}

function tcApplyPreset(preset) {{
  if (!TC_MONTHS.length) return;
  const last = TC_MONTHS[TC_MONTHS.length - 1];
  const first = TC_MONTHS[0];
  let start = first;
  if      (preset === '30')  start = tcMonthsBack(0);    // current month only
  else if (preset === '90')  start = tcMonthsBack(2);    // current + 2 prior
  else if (preset === 'ytd') start = last.slice(0,4) + '-01';
  else                       start = first;
  // Clamp to available range
  if (start < first) start = first;
  document.getElementById('tc-start').value = start;
  document.getElementById('tc-end').value = last;
  tcRender(start, last);
}}

(function tcInit() {{
  const startSel = document.getElementById('tc-start');
  const endSel   = document.getElementById('tc-end');
  if (!startSel || !endSel) return;
  if (!TC_MONTHS.length) {{
    document.querySelectorAll('.tc-grid').forEach(g =>
      g.innerHTML = '<div class="tc-empty">No top-content data yet — run the tracker to populate.</div>');
    return;
  }}
  for (const m of TC_MONTHS) {{
    const o1 = document.createElement('option'); o1.value = m; o1.textContent = m;
    const o2 = o1.cloneNode(true);
    startSel.appendChild(o1); endSel.appendChild(o2);
  }}
  startSel.value = TC_MONTHS[0];
  endSel.value   = TC_MONTHS[TC_MONTHS.length - 1];
  tcRender(startSel.value, endSel.value);

  function clearPresetActive() {{
    document.querySelectorAll('.tc-preset').forEach(b => b.classList.remove('active'));
  }}
  startSel.addEventListener('change', () => {{ clearPresetActive(); tcRender(startSel.value, endSel.value); }});
  endSel  .addEventListener('change', () => {{ clearPresetActive(); tcRender(startSel.value, endSel.value); }});
  document.querySelectorAll('.tc-preset').forEach(btn => {{
    btn.addEventListener('click', () => {{
      clearPresetActive();
      btn.classList.add('active');
      tcApplyPreset(btn.dataset.range);
    }});
  }});
}})();
</script>
<!-- ── History Drawer ── -->
<div id="history-drawer" style="display:none;position:fixed;bottom:0;left:0;right:0;z-index:100;background:var(--surface);border-top:2px solid var(--brand);box-shadow:0 -4px 24px rgba(15,23,41,.12);">
  <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 24px 10px;">
    <div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--brand);font-weight:600;margin-bottom:2px">Full History</div>
      <div id="history-title" style="font-size:15px;font-weight:600;color:var(--text)"></div>
    </div>
    <button onclick="closeHistory()" style="font-family:'DM Sans',sans-serif;font-size:12px;padding:6px 14px;border-radius:var(--rsm);border:1px solid var(--border2);background:var(--surface2);cursor:pointer;color:var(--text2);">✕ Close</button>
  </div>
  <div style="overflow-x:auto;height:260px;padding:0 24px 16px;scrollbar-width:thin;">
    <div style="height:100%;position:relative;">
      <canvas id="history-canvas"></canvas>
    </div>
  </div>
</div>

</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Road Trippin' Dashboard Generator v3")
    parser.add_argument("--tracker", default=None, help="Path to tracker_data.json")
    parser.add_argument("--revenue", default=None)
    parser.add_argument("--socials", default=None)
    parser.add_argument("--output",  default="road_trippin.html")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")

    if not args.tracker:
        default_json = os.path.join(data_dir, "tracker_data.json")
        if os.path.exists(default_json):
            args.tracker = default_json

    if not args.tracker or not os.path.exists(args.tracker):
        print("ERROR: tracker_data.json not found in data/. Run build_tracker.py first.")
        return

    out = os.path.join(script_dir, args.output)

    print("=" * 55)
    print("ROAD TRIPPIN' — DASHBOARD GENERATOR v3")
    print("=" * 55)
    print(f"Tracker: {args.tracker}")

    d = extract(args.tracker)
    reports = scan_reports(data_dir)
    revenue_path = args.revenue or os.path.join(data_dir, "revenue.csv")
    revenue = load_revenue(revenue_path)
    socials_path = args.socials or os.path.join(data_dir, "socials.csv")
    socials = load_socials(socials_path)
    generated_at = datetime.now().strftime("%b %d, %Y")

    print(f"  Months:  {len(d['months'])}  ({d['months'][-1]} → {d['months'][0]})")
    print(f"  YT data: {'yes' if any(v for v in d['vids'] if v) else 'no'}")
    print(f"  Audio:   {'yes' if any(v for v in d['l_total'] if v) else 'no'}")
    print(f"  Subs:    {d['current_subs']:,}")
    print(f"  Reports: {sum(len(v) for v in reports.values())} found")
    print(f"  Revenue: {len(revenue['months'])} months loaded from {revenue_path}")
    print(f"  Socials: {len(socials['months'])} months × {len(socials['platforms'])} platforms loaded from {socials_path}")

    html = build_html(d, reports, revenue, socials, generated_at)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nSaved: {out}")
    print("=" * 55)


if __name__ == "__main__":
    main()