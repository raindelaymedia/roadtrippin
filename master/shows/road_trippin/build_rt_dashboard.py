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




def _load_all_videos(j):
    """Get the full per-video list for the Performance Cube. Prefers tracker's
    new `all_videos` field; falls back to flattening `top_content_monthly` so
    the cube still works before the new tracker has been run."""
    av = j.get('all_videos')
    if av:
        return av
    seen, out = set(), []
    for m, buckets in (j.get('top_content_monthly') or {}).items():
        for t in ('long', 'mid', 'short'):
            for v in buckets.get(t, []) or []:
                vid = v.get('id')
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                out.append(v)
    return out


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
        'all_videos':   _load_all_videos(j),
        'subs_gained':  subs_gained,
        'subs_lost':    subs_lost,
        'current_subs': current_subs,
        'daily_yt':     j.get('daily_yt', {}),
        # Audience tab — Episodes/VODs from the Full Episodes playlist.
        # None for any month until build_tracker.py has been rerun with the
        # playlist wired in (older tracker_data.json won't have this key).
        'audience_eps':  series(['audience', 'eps']),
        'audience_vods': series(['audience', 'vods']),
        'audience_lives': series(['audience', 'lives']),
    }

def empty_state(message, sub=""):
    """Standard empty-state block for tabs with no data."""
    sub_html = f'<div style="font-size:12px;color:var(--text3);margin-top:6px;max-width:420px;margin-left:auto;margin-right:auto">{sub}</div>' if sub else ''
    return (f'<div style="background:var(--surface);border:1px dashed var(--border2);border-radius:var(--r);padding:48px 24px;text-align:center;margin:16px 0">'
            f'<div style="font-size:32px;margin-bottom:12px">📭</div>'
            f'<div style="font-size:14px;font-weight:500;color:var(--text2)">{message}</div>'
            f'{sub_html}</div>')


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
    """Scan for Fanatics report files (HTML or PDF). Looks in both:
        data/reports/             (flat layout)
        data/reports/fanatics/    (original scaffold layout)
    Files found in either location are merged into one list, newest first.
    Filename pattern for dated reports: Road_Trippin_Fanatics_MMDD_MMDD_YY.html
    → labeled with the parsed date range."""
    import re as _re
    months = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

    data_rel = os.path.basename(data_dir.rstrip('/\\')) or 'data'   # 'data' (or whatever leaf folder is named)
    candidates = []
    for sub in ('', 'fanatics'):
        folder = os.path.join(data_dir, 'reports', sub) if sub else os.path.join(data_dir, 'reports')
        if not os.path.isdir(folder):
            continue
        # Path relative to the dashboard HTML (which lives one level up from data/):
        rel_prefix = os.path.join(data_rel, 'reports', sub) if sub else os.path.join(data_rel, 'reports')
        for f in os.listdir(folder):
            if not f.lower().endswith(('.html', '.htm', '.pdf')):
                continue
            # Skip non-files (in case there's another subfolder)
            full = os.path.join(folder, f)
            if not os.path.isfile(full):
                continue
            # Parse Road_Trippin_..._MMDD_MMDD_YY.* into a clean label
            m = _re.search(r'_(\d{2})(\d{2})_(\d{2})(\d{2})_(\d{2})\.', f)
            if m:
                m1, d1, m2, d2, yy = m.groups()
                label = f"Fanatics · {months[int(m1)]} {int(d1)} – {months[int(m2)]} {int(d2)}, 20{yy}"
            else:
                label = f.replace('_', ' ').rsplit('.', 1)[0]
            candidates.append({
                'filename': f,
                'label':    label,
                'path':     os.path.join(rel_prefix, f).replace('\\', '/'),
                'mtime':    os.path.getmtime(full),
            })

    # Sort newest-first by modification time; drop the mtime field from output
    candidates.sort(key=lambda x: x['mtime'], reverse=True)
    for c in candidates:
        del c['mtime']
    return {'fanatics': candidates}


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


def delta_pp_str(lst):
    """Delta for percentage values (lst of decimals 0–1) — formatted in percentage points."""
    a, b = latest(lst), prev_val(lst)
    if a is None or b is None: return '—'
    d = (a - b) * 100
    cls = 'up' if d >= 0 else 'down'
    return f'<span class="{cls}">{"+" if d>=0 else ""}{d:.1f} pp vs prev</span>'


def compute_rolling_kpis(daily_yt):
    """Compute rolling 30-day KPI totals from daily YT data.

    Returns dict with:
      curr:      last 30 days totals (dict of metric -> value)
      prev:      preceding 30 days totals (or None if insufficient data)
      curr_range: (start_date, end_date) strings
      prev_range: (start_date, end_date) strings or None

    Returns None if daily_yt has < 30 days of data.
    """
    if not daily_yt or len(daily_yt) < 30:
        return None
    days = sorted(daily_yt.keys(), reverse=True)  # newest first
    last_30 = days[:30]
    prev_30 = days[30:60] if len(days) >= 60 else []

    def sum_range(days_list, key):
        return sum((daily_yt.get(d) or {}).get(key, 0) or 0 for d in days_list)

    def build(days_list):
        subs_gained = sum_range(days_list, "subs_gained")
        subs_lost   = sum_range(days_list, "subs_lost")
        return {
            "total_views":  sum_range(days_list, "total_views"),
            "vod_views":    sum_range(days_list, "vod_views"),
            "shorts_views": sum_range(days_list, "shorts_views"),
            "live_views":   sum_range(days_list, "live_views"),
            "subs_gained":  subs_gained,
            "subs_lost":    subs_lost,
            "net_subs":     subs_gained - subs_lost,
        }

    return {
        "curr": build(last_30),
        "prev": build(prev_30) if prev_30 else None,
        "curr_range": (last_30[-1], last_30[0]),
        "prev_range": (prev_30[-1], prev_30[0]) if prev_30 else None,
    }


def delta_rolling(curr_val, prev_val_):
    """Format a delta between two rolling-window totals as '±X vs prev 30d'."""
    if curr_val is None or prev_val_ is None or prev_val_ == 0:
        return '—'
    d = curr_val - prev_val_
    cls = 'up' if d >= 0 else 'down'
    pct = (d / prev_val_) * 100 if prev_val_ else 0
    return f'<span class="{cls}">{"+" if d>=0 else ""}{fmt(d)} · {"+" if pct>=0 else ""}{pct:.1f}% vs prev 30d</span>'


def bar_html(v, color, name, val_str=None, baseline=1):
    pct = min(100, round((v or 0) / max(baseline, 1) * 100))
    display = val_str if val_str else (fmt(v) if v else '—')
    return (f'<div class="plat-row"><span class="plat-name">{name}</span>'
            f'<div class="plat-bar-bg"><div class="plat-bar" style="width:{pct}%;background:{color}"></div></div>'
            f'<span class="plat-val">{display}</span></div>')


def social_post_series(socials, target_months):
    """Avg views/post across IG+TikTok+X+Facebook for each month in
    target_months (YYYY-MM, any order). Excludes YouTube — that's already
    captured separately in the YT VOD/Live/Short rows above it on the
    Audience tab."""
    sm = socials.get('months', [])
    idx = {m: i for i, m in enumerate(sm)}
    platforms = ['INSTAGRAM', 'TIKTOK', 'X', 'FACEBOOK']
    out = []
    for m in target_months:
        i = idx.get(m)
        if i is None:
            out.append(None)
            continue
        total_views, total_posts = 0, 0
        for p in platforms:
            v = socials['data'].get((p, 'VIEWS'), [None] * len(sm))[i]
            pc = socials['data'].get((p, 'POSTS'), [None] * len(sm))[i]
            if isinstance(v, (int, float)):
                total_views += v
            if isinstance(pc, (int, float)):
                total_posts += pc
        out.append(round(total_views / total_posts) if total_posts else None)
    return out


def audience_table_html(d, socials, M_raw, M_display):
    """Recreates Jon's manual 'Audience' breakdown as a dashboard table:
    per-piece average audience across every content type, full history,
    newest-first (matches the Tracker tab convention).

    Rightmost column is '% of Audience' — each content type's share of the
    LIFETIME sum of all monthly per-piece averages (not a single-month
    snapshot, for stability). This is a judgment call in the absence of a
    preserved spec from Jon's original sheet — flag if a different window
    (e.g. trailing 12mo) is wanted instead.
    """
    eps      = d['audience_eps']
    vods     = d['audience_vods']
    lives    = d['audience_lives']
    shorts_n = d['n_sht']

    def safe_div(numer, denom):
        out = []
        for n_, dn in zip(numer, denom):
            out.append(round(n_ / dn) if (n_ is not None and dn) else None)
        return out

    yt_vod_pp   = safe_div(d['vids'],   vods)
    yt_live_pp  = safe_div(d['lives'],  lives)
    yt_short_pp = safe_div(d['shorts'], shorts_n)
    social_pp   = social_post_series(socials, M_raw)
    spotify_pp  = [None] * len(M_raw)   # pending Spotify for Podcasters export
    audio_pp    = d['l_perep']

    pp_rows = [
        ('YT VOD',      yt_vod_pp),
        ('YT Live',     yt_live_pp),
        ('YT Short',    yt_short_pp),
        ('Social Post', social_pp),
        ('Spotify Ep',  spotify_pp),
        ('Audio Ep',    audio_pp),
    ]

    # Total / Avg per month across whichever of the 6 per-piece rows have data
    total_row, avg_row = [], []
    for i in range(len(M_raw)):
        vals = [series[i] for _, series in pp_rows if series[i] is not None]
        if vals:
            total_row.append(round(sum(vals)))
            avg_row.append(round(sum(vals) / len(vals)))
        else:
            total_row.append(None)
            avg_row.append(None)

    # % of Audience — each content type's share of its lifetime sum
    lifetime_sums = {label: sum(v for v in series if v) for label, series in pp_rows}
    grand_total = sum(lifetime_sums.values()) or 1
    pct_of_aud = {label: (lifetime_sums[label] / grand_total * 100) for label, _ in pp_rows}

    def fmt_cell(v):
        return f'<td>{int(v):,}</td>' if v is not None else '<td><span class="na">—</span></td>'

    def row_html(label, series, pct_val=None, css_class=None):
        cells = ''.join(fmt_cell(v) for v in series)
        pct_cell = (f'<td class="lifetime-col">{pct_val:.1f}%</td>' if pct_val is not None
                    else '<td class="lifetime-col">—</td>')
        cls = f' class="{css_class}"' if css_class else ''
        return f'<tr{cls}><td>{label}</td>{cells}{pct_cell}</tr>'

    header = ('<tr><th>📊 Audience</th>' +
              ''.join(f'<th>{m}</th>' for m in M_display) +
              '<th class="lifetime-col">% of Aud.</th></tr>')

    body = ''
    body += row_html('# of Episodes', eps)
    body += row_html('# of VODs', vods)
    body += row_html('# of Lives', lives)
    body += row_html('# of Shorts', shorts_n)
    for label, series in pp_rows:
        body += row_html(label, series, pct_of_aud[label])
    body += row_html('Total', total_row, css_class='total-row')
    body += row_html('Avg', avg_row, css_class='total-row')

    note = ''
    if all(v is None for v in spotify_pp):
        note = ('<div class="tracker-note">Spotify Ep is pending a Spotify for Podcasters export — '
                'Total/Avg/% of Audience will be understated until that\'s wired in.</div>')

    return (f'<div class="tracker-section"><div class="tracker-section-title">📊 Audience</div>'
            f'<div class="table-scroll"><table class="data-table"><thead>{header}</thead>'
            f'<tbody>{body}</tbody></table></div>{note}</div>')


def table_html(title, icon, rows, months, total_labels=None):
    """Render a full-width data table with a section title above it.

    `months` and every row's data list must already be in the SAME order
    (this dashboard displays newest-first: JUN, MAY, APR, ... on the Tracker tab).

    Every row gets a Lifetime column (sum of that row's full history).
    If `total_labels` is given (a list/set of row labels), an extra "Total"
    row is appended summing just those rows, per month + lifetime.
    """
    header = ('<tr><th>' + icon + ' ' + title + '</th>' +
               ''.join(f'<th>{m}</th>' for m in months) +
               '<th class="lifetime-col">Lifetime</th></tr>')
    body = ''
    total_by_month = [0] * len(months) if total_labels else None
    total_lifetime = 0
    for label, data, fmt_type in rows:
        cells = ''
        lifetime_sum = 0
        is_pct = fmt_type == 'pct'
        for i, v in enumerate(data):
            if v is None:
                cells += '<td><span class="na">—</span></td>'
            elif is_pct or (isinstance(v, float) and 0 < v < 1):
                cells += f'<td>{v*100:.1f}%</td>'
            elif isinstance(v, (int, float)):
                cells += f'<td>{int(v):,}</td>'
                lifetime_sum += v
                if total_labels and label in total_labels and total_by_month is not None and i < len(total_by_month):
                    total_by_month[i] += v
            else:
                cells += f'<td>{v}</td>'
        lifetime_cell = (f'<td class="lifetime-col">{int(lifetime_sum):,}</td>'
                          if not is_pct else '<td class="lifetime-col">—</td>')
        body += f'<tr><td>{label}</td>{cells}{lifetime_cell}</tr>'
        if total_labels and label in total_labels:
            total_lifetime += lifetime_sum
    if total_labels and total_by_month is not None:
        total_cells = ''.join(f'<td>{int(v):,}</td>' for v in total_by_month)
        body += f'<tr class="total-row"><td>Total</td>{total_cells}<td class="lifetime-col">{int(total_lifetime):,}</td></tr>'
    return (f'<div class="tracker-section"><div class="tracker-section-title">{icon} {title}</div>'
            f'<div class="table-scroll"><table class="data-table"><thead>{header}</thead><tbody>{body}</tbody></table></div></div>')


def reports_html(reports):
    """Render the Reports tab content."""
    def section(title, icon, items):
        if not items:
            return (f'<div class="reports-section"><div class="reports-section-title">{icon} {title}</div>'
                    f'<div class="reports-empty">No reports yet — generate one with <code>build_fanatics_report.py</code></div></div>')
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
    return fanatics + embed


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

    # ── Monthly KPIs: prefer the most recent COMPLETE month.
    # Rationale: YT/Megaphone data lags a few days into a new month, so the current
    # partial month looks artificially low. Use last complete month as "current" unless
    # we're far enough into a new month for data to have caught up.
    from datetime import datetime as _dt
    _today = _dt.now()
    def latest_complete(lst):
        """Get the last complete-month value: skip current month if we're early in it."""
        if not lst: return 0
        # If we're in the first ~5 days of a month, current month = latest[-1] is likely partial
        # Prefer latest[-2] (last complete month) when latest[-1] looks incomplete
        if _today.day <= 5 and len(lst) >= 2 and (lst[-1] or 0) < (lst[-2] or 0) * 0.3:
            return lst[-2] or 0
        for v in reversed(lst):
            if v: return v
        return 0

    listens_now = latest_complete(ltotal_full)
    eps_now     = latest_complete(rev(d['eps']))
    pct_sht_now = next((v for v in reversed(pctsht_full) if v is not None), None)
    streams_now = latest_complete(lstrm_full)

    # ── Rolling 30-day YT KPIs (from daily_yt in tracker JSON)
    rolling = compute_rolling_kpis(d.get('daily_yt', {}))

    # Which month label to show on non-YT cards — pick the month `latest_complete` picked
    _complete_idx = -2 if (_today.day <= 5 and len(ltotal_full) >= 2 and (ltotal_full[-1] or 0) < (ltotal_full[-2] or 0) * 0.3) else -1
    complete_mo = M[_complete_idx] if M and abs(_complete_idx) <= len(M) else latest_mo

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

    # Tracker tab displays newest-first (JUN, MAY, APR ...). d[...] values are
    # already newest-first as-loaded, so pair them with M_display (also
    # newest-first) rather than M (which was reversed to oldest-first for the
    # left-to-right charts elsewhere).
    tracker_tables = (
        table_html('Views', '📺', [
            ('# of Episodes', d['eps'], 'int'),
            ('YT Videos', d['vids'], 'int'),
            ('YT Shorts', d['shorts'], 'int'),
            ('YT Lives', d['lives'], 'int'),
            ('Spotify Streams', d['spotify'], 'int'),
        ], M_display, total_labels=['YT Videos', 'YT Shorts', 'YT Lives']) +
        table_html('Listens', '🎧', [
            ('# of Episodes', d['l_eps'], 'int'),
            ('Per-ep Listens', d['l_perep'], 'int'),
            ('Total Listens', d['l_total'], 'int'),
        ], M_display) +
        table_html('Subscribers', '👥', [
            ('YouTube', d['yt_subs'], 'int'),
            ('Apple Podcasts', d['apple_subs'], 'int'),
            ('Spotify', d['spotify_subs'], 'int'),
        ], M_display) +
        table_html('KPIs', '🔑', [
            ('CTR – Videos', d['ctr_vid'], 'pct'),
            ('CTR – Shorts', d['ctr_sht'], 'pct'),
            ('# of Shorts', d['n_sht'], 'int'),
            ('Shorts % of Views', d['pct_sht'], 'pct'),
            ('Search % of Views', d['srch_pct'], 'pct'),
            ('CTR in Search', d['srch_ctr'], 'pct'),
        ], M_display)
    )

    # ─── Audience ──────────────────────────────────────────────
    audience_table = audience_table_html(d, socials, M_raw, M_display)
    audience_subtitle = f'Full data export · {latest_mo} – {M[0] if M else ""} · newest left, oldest right'

    reports_content = reports_html(reports)

    # ─── Revenue ───────────────────────────────────────────────
    rev_M_raw = revenue.get('months', [])
    rev_sources = revenue.get('sources', {})
    rev_totals_raw = revenue.get('totals', [])
    rev_order = revenue.get('order', [])

    # Editable-grid data: raw cell values (numbers OR 'TBD'/'N/A'/'') keyed by
    # SOURCE|PERIOD, so the in-dashboard editor round-trips the exact CSV. Newest
    # period first for display. Sources follow the same display order as the table.
    rev_edit_periods = list(reversed(rev_M_raw))            # newest first
    rev_edit_sources = rev_order or sorted(rev_sources.keys())
    rev_edit_cells = {}
    for src in rev_edit_sources:
        series = rev_sources.get(src, [])
        for i, period in enumerate(rev_M_raw):
            val = series[i] if i < len(series) else ''
            if isinstance(val, (int, float)):
                cell = f'{val:.2f}' if val != int(val) else str(int(val))
            elif val in ('TBD', 'N/A'):
                cell = val
            else:
                cell = ''
            rev_edit_cells[f'{src}|{period}'] = cell
    js_rev_edit = json.dumps({
        'periods': rev_edit_periods,
        'sources': rev_edit_sources,
        'cells': rev_edit_cells,
    })

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

    # ── Editable socials grid data ──
    # One row per platform+metric pair, columns = months (newest first). Values
    # round-trip the CSV exactly (numbers, 'TBD'/'N/A', or ''). ER stored as a
    # fraction in the CSV but shown/edited as a percent for readability.
    SOC_EDIT_METRICS = ['FOLLOWERS', 'FOLLOWER_GAIN', 'POSTS', 'VIEWS',
                        'ENGAGEMENTS', 'ENGAGEMENT_RATE', 'TOP_POST_VIEWS']
    SOC_EDIT_METRIC_LABELS = {
        'FOLLOWERS': 'Followers', 'FOLLOWER_GAIN': 'Net Gain', 'POSTS': 'Posts',
        'VIEWS': 'Views', 'ENGAGEMENTS': 'Engagements',
        'ENGAGEMENT_RATE': 'ER %', 'TOP_POST_VIEWS': 'Top Post',
    }
    soc_edit_periods = list(reversed(soc_M_raw))          # newest first
    soc_edit_rows = []      # [{platform, metric, label}] in display order
    soc_edit_cells = {}     # "PLATFORM|METRIC|PERIOD" -> string
    for platform in soc_platforms:
        for metric in SOC_EDIT_METRICS:
            series = soc_series(platform, metric)
            if not any(v not in (None, '', 'TBD', 'N/A') for v in series):
                # skip metric rows that are entirely empty for this platform
                # (e.g. YouTube has no ENGAGEMENTS) — keeps the grid tight
                if not any(v is not None for v in series):
                    continue
            soc_edit_rows.append({
                'platform': platform, 'metric': metric,
                'label': SOC_EDIT_METRIC_LABELS.get(metric, metric),
            })
            for i, period in enumerate(soc_M_raw):
                val = series[i] if i < len(series) else None
                if isinstance(val, (int, float)):
                    if metric == 'ENGAGEMENT_RATE':
                        cell = f'{val*100:.2f}'          # show as percent number
                    elif val == int(val):
                        cell = str(int(val))
                    else:
                        cell = f'{val:.2f}'
                elif val in ('TBD', 'N/A'):
                    cell = val
                else:
                    cell = ''
                soc_edit_cells[f'{platform}|{metric}|{period}'] = cell
    js_soc_edit = json.dumps({
        'periods': soc_edit_periods,
        'rows': soc_edit_rows,
        'cells': soc_edit_cells,
        'platformDisplay': PLATFORM_DISPLAY,
    })

    # Latest month metrics — totals across platforms
    soc_latest_label = soc_M_display[-1] if soc_M_display else '—'
    total_followers = sum(filter(None, [soc_latest_for(p, 'FOLLOWERS') for p in soc_platforms]))
    total_impressions = sum(filter(None, [soc_latest_for(p, 'VIEWS') for p in soc_platforms]))
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

        f'<div class="metric"><div class="metric-label">Views ({soc_latest_label})</div>'
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
        views = soc_latest_for(platform, 'VIEWS')
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
            f'<div class="soc-stat"><div class="soc-stat-label">Views</div><div class="soc-stat-val">{fmt(views)}</div></div>'
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

    # Views per platform (stacked bar)
    soc_imp_ds = []
    for p in soc_platforms:
        vals = [v if isinstance(v, (int, float)) else None for v in soc_series(p, 'VIEWS')]
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
    js_all_videos = json.dumps(d.get('all_videos', []))

    # Fanatics partnership — Season 2 starts Oct 1, 2025 → Sep 30, 2026
    # (Season 3: Oct 1, 2026 → Sep 30, 2027). The annotation marks S2 start.
    js_fanatics_label = json.dumps(fmt_period("2025-10"))

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
<link rel="icon" type="image/png" href="data:image/png;base64,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">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600&family=DM+Mono:wght@400;500&family=Oswald:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ─────────────────────────────────────────────────────────────
   ROAD TRIPPIN' DASHBOARD — Rain Delay Media brand styling
   Brand color: #2F6DDE (logo blue)
   Aesthetic:   Clean, modern, professional — bright accents on
                a soft neutral background, plenty of whitespace.
   ───────────────────────────────────────────────────────────── */
:root{{
  /* Brand — RT Gold */
  --brand:        #C9A84C;
  --brand-deep:   #A8873A;
  --brand-soft:   rgba(201,168,76,.10);
  --brand-tint:   rgba(201,168,76,.18);

  /* Surfaces — Dark */
  --bg:           #0D0D0D;
  --surface:      rgba(255,255,255,.04);
  --surface2:     rgba(255,255,255,.07);
  --surface3:     rgba(255,255,255,.10);

  /* Borders */
  --border:       rgba(255,255,255,.08);
  --border2:      rgba(255,255,255,.14);

  /* Text */
  --text:         #F5F5F0;
  --text2:        #A0A09A;
  --text3:        #5A5A55;

  /* Functional accents */
  --green:        #34D058;
  --green-soft:   rgba(52,208,88,.12);
  --red:          #F85149;
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
  --shadow-sm:    0 1px 2px rgba(0,0,0,.3);
  --shadow:       0 1px 3px rgba(0,0,0,.4), 0 1px 2px rgba(0,0,0,.2);
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'DM Sans',sans-serif;background:var(--bg);color:var(--text);line-height:1.5;font-size:14px;position:relative}}
body::before{{content:'';position:fixed;top:0;left:0;width:100%;height:100%;z-index:0;pointer-events:none;background:url("data:image/jpeg;base64,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") center/cover fixed;opacity:.6;mix-blend-mode:screen}}
body > *{{position:relative;z-index:1}}

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
  color:#0D0D0D; font-family:'Oswald',sans-serif; font-weight:700; font-size:12px;
  letter-spacing:-.02em;
  box-shadow:0 2px 4px rgba(201,168,76,.3);
}}
.logo-text{{display:flex;flex-direction:column;line-height:1.15}}
.logo-main{{font-size:14px;font-weight:600;letter-spacing:-.3px;color:var(--text)}}
.logo-sub{{font-size:11px;color:var(--text3);margin-top:1px;font-weight:400}}

.nav{{padding:14px 10px 10px;flex:1}}
.nav-section{{font-family:'Oswald',sans-serif;font-size:10px;text-transform:uppercase;letter-spacing:.12em;color:var(--text3);padding:8px 12px 6px;font-weight:500}}
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
.page-title{{font-family:'Oswald',sans-serif;font-size:22px;font-weight:600;letter-spacing:-.3px;color:var(--text);text-transform:uppercase}}
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
  font-family:'Oswald',sans-serif;
  font-size:26px; font-weight:600;
  letter-spacing:-.4px; line-height:1;
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
/* ─── Revenue editor ─── */
.rev-edit-toggle{{font-size:11px;font-family:'DM Sans',sans-serif;font-weight:600;padding:4px 12px;border-radius:var(--rsm);border:.5px solid var(--brand);background:var(--brand-soft);color:var(--brand);cursor:pointer}}
.rev-edit-toggle.on{{background:var(--brand);color:#0D0D0D}}
.rev-edit-btn{{font-size:11px;font-family:'DM Sans',sans-serif;font-weight:600;padding:4px 12px;border-radius:var(--rsm);border:.5px solid var(--border2);background:var(--surface);color:var(--text);cursor:pointer}}
.rev-edit-btn:hover{{border-color:var(--text2)}}
.rev-edit-btn.rev-save{{background:#1B9B54;border-color:#1B9B54;color:#fff}}
.rev-edit-btn.rev-save:hover{{background:#137a41}}
.rev-edit-btn:disabled{{opacity:.4;cursor:not-allowed}}
.rev-edit-status{{font-size:11px;font-family:'DM Sans',sans-serif;color:var(--gold);font-weight:500}}
.rev-grid{{border-collapse:separate;border-spacing:0;font-size:12px;font-family:'DM Mono',monospace;white-space:nowrap}}
.rev-grid th,.rev-grid td{{padding:6px 11px;text-align:right;border:.5px solid var(--border)}}
.rev-grid thead th{{position:sticky;top:0;z-index:3;background:var(--surface2);color:var(--text2);font-family:'DM Sans',sans-serif;font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}}
.rev-grid th.rev-src,.rev-grid td.rev-src{{position:sticky;left:0;z-index:2;text-align:left;background:var(--surface);color:var(--text);font-family:'DM Sans',sans-serif;font-weight:500;min-width:150px;border-right:1px solid var(--border2)}}
.rev-grid thead th.rev-src{{z-index:4}}
.rev-grid td.rev-tbd{{color:var(--gold);font-style:italic}}
.rev-grid td.rev-empty{{color:var(--text3,#b8bfca)}}
.rev-grid tr.rev-total td{{position:sticky;bottom:0;background:var(--surface2);font-weight:700;color:var(--text);border-top:1.5px solid var(--border2)}}
.rev-grid td.rev-cell{{cursor:cell}}
.rev-grid td.rev-cell:hover{{outline:1.5px solid #7c4dff;outline-offset:-1.5px;background:#f3effe}}
.rev-grid td.rev-changed{{background:#efe9fe;position:relative}}
.rev-grid td.rev-changed::after{{content:'';position:absolute;top:3px;right:3px;width:4px;height:4px;border-radius:50%;background:#7c4dff}}
.rev-grid td.rev-editing{{padding:0}}
.rev-grid td.rev-editing input{{width:100%;border:none;background:#f3effe;color:var(--text);font:inherit;font-family:'DM Mono',monospace;text-align:right;padding:6px 11px;outline:2px solid #7c4dff;outline-offset:-2px}}
.rev-modal-bg{{display:none;position:fixed;inset:0;background:rgba(15,23,41,.55);z-index:100;align-items:center;justify-content:center}}
.rev-modal-bg.show{{display:flex}}
.rev-modal{{background:#1A1A1A;border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:22px;width:440px;max-width:92vw;color:var(--text)}}
.rev-modal h2{{font-size:15px;margin:0 0 4px;color:var(--text);font-family:'DM Sans',sans-serif}}
.rev-modal p{{font-size:12px;color:var(--text2);margin:0 0 14px}}
.rev-field{{margin-bottom:11px}}
.rev-field label{{display:block;font-size:10px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px;font-family:'DM Sans',sans-serif}}
.rev-field .mut{{color:var(--text3,#b8bfca);text-transform:none;font-weight:400}}
.rev-field input{{width:100%;font:inherit;font-size:12px;font-family:'DM Mono',monospace;padding:8px 10px;border-radius:6px;border:1px solid var(--border);background:rgba(255,255,255,.06);color:var(--text)}}
.rev-field input:focus{{outline:none;border-color:#7c4dff}}
.rev-modal-actions{{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}}
.rev-warn{{font-size:11px;color:#C9A84C;background:rgba(201,168,76,.1);border:1px solid rgba(201,168,76,.2);border-radius:6px;padding:8px 10px;margin-top:4px}}
.rev-commit-log{{font-size:11px;font-family:'DM Mono',monospace;color:var(--text2);margin-top:10px;max-height:110px;overflow:auto}}
.rev-commit-log div{{padding:2px 0;border-bottom:.5px solid var(--border)}}

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
.data-table td{{padding:6px 12px;text-align:right;border:.5px solid var(--border);background:transparent}}
.data-table td:first-child{{text-align:left;font-family:'DM Sans',sans-serif;font-size:12px;font-weight:500;color:var(--text2);position:sticky;left:0;background:var(--bg);z-index:1;min-width:150px}}
.data-table tr:nth-child(even) td{{background:rgba(255,255,255,.03)}}
.data-table tr:nth-child(even) td:first-child{{background:#151515}}
.data-table tr:nth-child(even) td:first-child{{background:#f8f9fc}}
.data-table th.lifetime-col{{background:var(--surface3);border-left:1px solid var(--border2)}}
.data-table td.lifetime-col{{
  font-weight:600; color:var(--text); background:var(--surface3)!important;
  border-left:1px solid var(--border2);
}}
.data-table tr.total-row td{{
  background:var(--surface2)!important; border-top:1px solid var(--border2);
  font-weight:600; color:var(--text);
}}
.data-table tr.total-row td:first-child{{background:var(--surface2)!important}}
.na{{color:var(--text3)}}
.tracker-note{{
  margin-top:8px; padding:8px 12px; font-size:12px; color:var(--text3);
  background:var(--surface2); border-radius:6px; border:1px solid var(--border2);
}}
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

/* ─── Performance Cube ─── */
.cube-controls {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap;
  margin:0 0 14px; padding:10px 14px; background:var(--surface2);
  border:1px solid var(--border); border-radius:8px; }}
.cube-legend {{ display:flex; align-items:center; gap:18px; flex-wrap:wrap;
  margin:0 0 14px; padding:10px 14px; background:var(--surface);
  border:1px solid var(--border); border-radius:8px; font-size:12px; color:var(--text2); }}
.cube-legend-item {{ display:inline-flex; align-items:center; gap:6px; }}
.cube-legend-item .dot {{ width:11px; height:11px; border-radius:50%; display:inline-block; }}
.cube-axes {{ margin-left:auto; font-size:11px; color:var(--text3); letter-spacing:.04em; }}
#cube-plot {{ background:var(--surface); border:1px solid var(--border); border-radius:8px; }}
</style>
</head>
<body>
<div class="shell">

<nav class="sidebar">
  <div class="sidebar-logo">
    <div class="logo-mark">RT</div>
    <div class="logo-text">
      <div class="logo-main">Road Trippin'</div>
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
    <div class="nav-item" onclick="showPage('audio',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.5"/><circle cx="8" cy="8" r="2.5" fill="currentColor"/></svg>
      <span>Audio</span>
    </div>
    <div class="nav-item" onclick="showPage('socials',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M5 7a2 2 0 100-4 2 2 0 000 4zm6 6a2 2 0 100-4 2 2 0 000 4zm0-10a2 2 0 100 4 2 2 0 000-4zM6.6 8.5l3 2.5M9.4 5l-3 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
      <span>Socials</span>
    </div>
    <div class="nav-item" onclick="showPage('audience',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><circle cx="5.5" cy="5.5" r="2.2" stroke="currentColor" stroke-width="1.4"/><circle cx="11" cy="7" r="1.6" stroke="currentColor" stroke-width="1.3" opacity=".6"/><path d="M1.5 13c.4-2.6 2.1-4 4-4s3.6 1.4 4 4M9.3 9.7c1.4.1 2.7 1.2 3 3.3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
      <span>Audience</span>
    </div>
    <div class="nav-item" onclick="showPage('revenue',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M5 5h4.5a1.5 1.5 0 010 3h-3a1.5 1.5 0 000 3H11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
      <span>Revenue</span>
    </div>
    <div class="nav-item" onclick="showPage('top-content',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M2 4h12M2 8h12M2 12h8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="14" cy="12" r="1.5" stroke="currentColor" stroke-width="1.3"/></svg>
      <span>Top Content</span>
    </div>
    <div class="nav-item" onclick="showPage('cube',this)">
      <svg class="nav-icon" viewBox="0 0 16 16" fill="none"><path d="M8 1.5L14 4.5V11.5L8 14.5L2 11.5V4.5L8 1.5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M2 4.5L8 7.5L14 4.5M8 7.5V14.5" stroke="currentColor" stroke-width="1.3"/></svg>
      <span>Performance Cube</span>
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
      <div class="metric-delta">{
        (delta_rolling(rolling['curr']['net_subs'], rolling['prev']['net_subs'])
          if rolling and rolling['prev'] else delta_str(d['yt_subs']))
      }</div>
    </div>
    <div class="metric">
      <div class="metric-label">YT Views {'(last 30d)' if rolling else f'({latest_mo})'}</div>
      <div class="metric-value">{
        fmt(rolling['curr']['total_views']) if rolling
        else fmt(sum(filter(None,[latest(d['vids']),latest(d['shorts']),latest(d['lives'])])))
      }</div>
      <div class="metric-delta">{
        (delta_rolling(rolling['curr']['total_views'], rolling['prev']['total_views'])
          if rolling and rolling['prev']
          else delta_str([sum(x or 0 for x in t) for t in zip(d['vids'],d['shorts'],d['lives'])]))
      }</div>
    </div>
    <div class="metric">
      <div class="metric-label">Audio ({complete_mo})</div>
      <div class="metric-value">{fmt(listens_now)}</div>
      <div class="metric-delta">{delta_str(ltotal_full[:_complete_idx+len(ltotal_full)+1] if _complete_idx < -1 else ltotal_full)}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Episodes ({complete_mo})</div>
      <div class="metric-value">{eps_now}</div>
      <div class="metric-delta">{delta_str(rev(d['eps'])[:_complete_idx+len(rev(d['eps']))+1] if _complete_idx < -1 else rev(d['eps']))}</div>
    </div>
    <div class="metric">
      <div class="metric-label">Shorts % ({complete_mo})</div>
      <div class="metric-value">{fmt(pct_sht_now, pct=True)}</div>
      <div class="metric-delta">{delta_pp_str(pctsht_full)}</div>
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
      <div class="card-header"><span class="card-title">Videos (VOD)</span><span class="card-sub">Monthly views</span><button class="expand-btn" onclick="openHistory('ytVids','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytVids"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Shorts</span><span class="card-sub">Monthly views</span><button class="expand-btn" onclick="openHistory('ytShorts','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytShorts"></canvas></div></div>
    </div>
  </div>
  <div class="grid-2 mb12">
    <div class="card">
      <div class="card-header"><span class="card-title">Lives</span><span class="card-sub">Monthly views</span><button class="expand-btn" onclick="openHistory('ytLives','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytLives"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Subscribers</span><span class="card-sub">Running total</span><button class="expand-btn" onclick="openHistory('subs','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytSubsLine"></canvas></div></div>
    </div>
  </div>
  <div class="grid-2">
    <div class="card">
      <div class="card-header"><span class="card-title">Shorts % of views</span><button class="expand-btn" onclick="openHistory('ytPct','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{chart_px}px;height:100%"><canvas id="ytPct"></canvas></div></div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title"># of Shorts published</span><button class="expand-btn" onclick="openHistory('ytNSht','')" title="Full history">↗</button></div>
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
      <div class="metric-delta">{delta_str(ltotal_full)}</div>
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
    <button class="expand-btn" onclick="openHistory('socFollowers','')" title="Full history">↗</button></div>
    <div class="legend">{soc_legend}</div>
    <div class="chart-outer-lg" style="height:260px">
      <div style="position:relative;width:{soc_chart_px}px;height:100%"><canvas id="socFollowers"></canvas></div>
    </div>
  </div>

  <div class="grid-2 mb12">
    <div class="card">
      <div class="card-header"><span class="card-title">Views by platform</span><span class="card-sub">stacked monthly</span><button class="expand-btn" onclick="openHistory('socImpressions','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px">
        <div style="position:relative;width:{soc_chart_px}px;height:100%"><canvas id="socImpressions"></canvas></div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Engagement rate</span><span class="card-sub">per platform</span><button class="expand-btn" onclick="openHistory('socER','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px">
        <div style="position:relative;width:{soc_chart_px}px;height:100%"><canvas id="socER"></canvas></div>
      </div>
    </div>
  </div>

  <div class="tracker-section">
    <div class="tracker-section-title" style="display:flex;align-items:center;gap:12px">
      <span>📱 Per-platform breakdown</span>
      <button class="rev-edit-toggle" id="socEditToggle" onclick="socToggleEdit()">✎ Edit</button>
      <button class="rev-edit-btn" id="socAddMonthBtn" onclick="socAddMonth()" style="display:none">+ Add month</button>
      <span class="rev-edit-status" id="socEditStatus"></span>
      <span style="flex:1"></span>
      <button class="rev-edit-btn" id="socGhBtn" onclick="socOpenGh()" style="display:none">⚙ GitHub</button>
      <button class="rev-edit-btn rev-save" id="socSaveBtn" onclick="socSave()" style="display:none" disabled>Save to repo</button>
    </div>
    <div id="soc-readonly">{socials_table}</div>
    <div id="soc-editable" style="display:none"></div>
  </div>
</div>

<!-- Socials editor GitHub modal -->
<div class="rev-modal-bg" id="socGhModal" onclick="if(event.target===this)socCloseGh()">
  <div class="rev-modal">
    <h2>GitHub connection</h2>
    <p>Commits <code>socials.csv</code> to the repo. Use a <b>fine-grained token</b> scoped to this repo with <b>Contents: Read and write</b>.</p>
    <div class="rev-field"><label>Repository</label><input id="socGhRepo" value="raindelaymedia/roadtrippin" spellcheck="false"></div>
    <div class="rev-field"><label>Branch <span class="mut">(blank = auto-detect)</span></label><input id="socGhBranch" placeholder="auto-detect…" spellcheck="false"></div>
    <div class="rev-field"><label>File path</label><input id="socGhPath" value="master/shows/road_trippin/data/socials.csv" spellcheck="false"></div>
    <div class="rev-field"><label>Access token</label><input id="socGhToken" type="password" placeholder="github_pat_…" spellcheck="false"></div>
    <div class="rev-warn">⚠ Token is stored in this browser only. Use a fine-grained token limited to this one repo.</div>
    <div class="rev-modal-actions">
      <button class="rev-edit-btn" onclick="socCloseGh()">Cancel</button>
      <button class="rev-edit-btn rev-save" onclick="socSaveConn()">Save connection</button>
    </div>
    <div class="rev-commit-log" id="socCommitLog"></div>
  </div>
</div>

<!-- ═══ AUDIENCE ═══ -->
<div class="page" id="page-audience">
  <div class="page-header">
    <div class="page-title">Audience</div>
    <div class="page-sub">{audience_subtitle}</div>
  </div>
  {audience_table}
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
      <button class="expand-btn" onclick="openHistory('revTotal','')" title="Full history">↗</button></div>
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
      <div class="card-header"><span class="card-title">YouTube AdSense</span><span class="card-sub">Videos + Shorts + Lives</span><button class="expand-btn" onclick="openHistory('revYT','')" title="Full history">↗</button></div>
      <div class="chart-outer" style="height:220px"><div style="position:relative;width:{rev_chart_px}px;height:100%"><canvas id="revYT"></canvas></div></div>
    </div>
  </div>

  <div class="tracker-section">
    <div class="tracker-section-title" style="display:flex;align-items:center;gap:12px">
      <span>💲 Revenue Breakdown</span>
      <button class="rev-edit-toggle" id="revEditToggle" onclick="revToggleEdit()">✎ Edit</button>
      <button class="rev-edit-btn" id="revAddMonthBtn" onclick="revAddMonth()" style="display:none">+ Add month</button>
      <span class="rev-edit-status" id="revEditStatus"></span>
      <span style="flex:1"></span>
      <button class="rev-edit-btn" id="revGhBtn" onclick="revOpenGh()" style="display:none">⚙ GitHub</button>
      <button class="rev-edit-btn rev-save" id="revSaveBtn" onclick="revSave()" style="display:none" disabled>Save to repo</button>
    </div>
    <div id="rev-readonly">{revenue_table}</div>
    <div id="rev-editable" style="display:none"></div>
  </div>
</div>

<!-- Revenue editor GitHub modal -->
<div class="rev-modal-bg" id="revGhModal" onclick="if(event.target===this)revCloseGh()">
  <div class="rev-modal">
    <h2>GitHub connection</h2>
    <p>Commits <code>revenue.csv</code> to the repo. Use a <b>fine-grained token</b> scoped to this repo with <b>Contents: Read and write</b>.</p>
    <div class="rev-field"><label>Repository</label><input id="revGhRepo" value="raindelaymedia/roadtrippin" spellcheck="false"></div>
    <div class="rev-field"><label>Branch <span class="mut">(blank = auto-detect)</span></label><input id="revGhBranch" placeholder="auto-detect…" spellcheck="false"></div>
    <div class="rev-field"><label>File path</label><input id="revGhPath" value="master/shows/road_trippin/data/revenue.csv" spellcheck="false"></div>
    <div class="rev-field"><label>Access token</label><input id="revGhToken" type="password" placeholder="github_pat_…" spellcheck="false"></div>
    <div class="rev-warn">⚠ Token is stored in this browser only. Use a fine-grained token limited to this one repo.</div>
    <div class="rev-modal-actions">
      <button class="rev-edit-btn" onclick="revCloseGh()">Cancel</button>
      <button class="rev-edit-btn rev-save" onclick="revSaveConn()">Save connection</button>
    </div>
    <div class="rev-commit-log" id="revCommitLog"></div>
  </div>
</div>

<!-- ═══ TRACKER ═══ -->
<div class="page" id="page-tracker">
  <div class="page-header">
    <div class="page-title">Tracker</div>
    <div class="page-sub">Full data export · {latest_mo} – {M[0] if M else ''} · newest left, oldest right</div>
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

<!-- ═══ PERFORMANCE CUBE ═══ -->
<div class="page" id="page-cube">
  <div class="page-header">
    <div class="page-title">Performance Cube</div>
    <div class="page-sub">3-axis distribution of every video on the channel · drag to rotate · scroll to zoom · click a point to open the video</div>
  </div>

  <div class="cube-controls">
    <button class="tc-preset" data-range="30">Last 30d</button>
    <button class="tc-preset" data-range="90">Last 90d</button>
    <button class="tc-preset" data-range="ytd">YTD</button>
    <button class="tc-preset active" data-range="all">All time</button>
    <span class="tc-sep"></span>
    <label class="tc-label">From <select id="cube-start"></select></label>
    <label class="tc-label">To <select id="cube-end"></select></label>
    <span class="tc-summary" id="cube-summary"></span>
  </div>

  <div class="cube-legend">
    <div class="cube-legend-item"><span class="dot" style="background:#C9A84C"></span>Full episodes (&gt;30 min)</div>
    <div class="cube-legend-item"><span class="dot" style="background:#2F6DDE"></span>Clips (3–30 min)</div>
    <div class="cube-legend-item"><span class="dot" style="background:#1B9B96"></span>Shorts (≤3 min)</div>
    <span class="cube-axes">Axes — X: Views (log scale) · Y: Engagement Rate · Z: Duration (min)</span>
  </div>

  <div id="cube-plot" style="width:100%;height:640px"></div>
  <div id="cube-empty" class="tc-empty" style="display:none">
    No video data available yet — run the latest tracker to populate.
  </div>
</div>

<!-- ═══ REPORTS ═══ -->
<div class="page" id="page-reports">
  <div class="page-header">
    <div class="page-title">Reports</div>
    <div class="page-sub">Monthly Fanatics delivery reports — click any card to view in line</div>
  </div>
  {reports_content}
</div>


</div><!-- /main -->
</div><!-- /shell -->

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
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

// Revenue data — full history (used by the ↗ full-history drawer)
const REV_M = {js_rev_m};
const REV_TOTALS = {js_rev_totals};
const REV_YT_VIDEOS = {js_rev_yt_videos};
const REV_YT_SHORTS = {js_rev_yt_shorts};
const REV_YT_LIVES = {js_rev_yt_lives};
const REV_STACKED_DS = {js_rev_stacked_ds};
const REV_MIX_LABELS = {js_rev_mix_labels};
const REV_MIX_VALUES = {js_rev_mix_values};
const REV_MIX_COLORS = {js_rev_mix_colors};

// Revenue data — last 12 months (default on-page view)
const REV_M12 = REV_M.slice(-12);
const REV_TOTALS12 = REV_TOTALS.slice(-12);
const REV_YT_VIDEOS12 = REV_YT_VIDEOS.slice(-12);
const REV_YT_SHORTS12 = REV_YT_SHORTS.slice(-12);
const REV_YT_LIVES12 = REV_YT_LIVES.slice(-12);
const REV_STACKED_DS12 = REV_STACKED_DS.map(ds => ({{ ...ds, data: ds.data.slice(-12) }}));

// Socials data — full history (used by the ↗ full-history drawer)
const SOC_M = {js_soc_m};
const REV_EDIT_DATA = {js_rev_edit};
const SOC_EDIT_DATA = {js_soc_edit};
const SOC_FOLLOWERS_DS = {js_soc_followers_ds};
const SOC_IMP_DS = {js_soc_imp_ds};
const SOC_ER_DS = {js_soc_er_ds};

// Socials data — last 12 months (default on-page view)
const SOC_M12 = SOC_M.slice(-12);
const SOC_FOLLOWERS_DS12 = SOC_FOLLOWERS_DS.map(ds => ({{ ...ds, data: ds.data.slice(-12) }}));
const SOC_IMP_DS12 = SOC_IMP_DS.map(ds => ({{ ...ds, data: ds.data.slice(-12) }}));
const SOC_ER_DS12 = SOC_ER_DS.map(ds => ({{ ...ds, data: ds.data.slice(-12) }}));

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
  // ── YouTube page charts ──
  ytVids: {{
    label: 'Videos — full history',
    type: 'bar',
    datasets: () => [{{ data: nn(VIDS_F), backgroundColor: '#2F6DDE', borderRadius: 2 }}],
  }},
  ytShorts: {{
    label: 'Shorts — full history',
    type: 'bar',
    datasets: () => [{{ data: nn(SH_F), backgroundColor: '#1B9B96', borderRadius: 2 }}],
  }},
  ytLives: {{
    label: 'Lives — full history',
    type: 'bar',
    datasets: () => [{{ data: nn(LV_F), backgroundColor: '#E08C2A', borderRadius: 2 }}],
  }},
  ytPct: {{
    label: 'Shorts share of views — full history',
    type: 'line',
    datasets: () => [{{ data: nn(PS_F), borderColor: '#1B9B96', backgroundColor: 'rgba(27,155,150,.08)', fill: true, tension: .3, pointRadius: 2 }}],
    pct: true,
  }},
  ytNSht: {{
    label: 'Shorts published — full history',
    type: 'bar',
    datasets: () => [{{ data: nn(NS_F), backgroundColor: '#1B9B96', borderRadius: 2 }}],
  }},
  // ── Revenue page charts ──
  revTotal: {{
    label: 'Monthly revenue — full history',
    type: 'bar',
    datasets: () => [{{ data: nn(REV_TOTALS), backgroundColor: '#C9A84C', borderRadius: 2 }}],
  }},
  revStacked: {{
    label: 'Revenue by source — full history',
    type: 'bar',
    datasets: () => REV_STACKED_DS.map(ds => ({{ ...ds, stack: 's' }})),
    stacked: true,
  }},
  revYT: {{
    label: 'YouTube revenue by content type — full history',
    type: 'bar',
    datasets: () => [
      {{ label: 'Videos', data: nn(REV_YT_VIDEOS), backgroundColor: '#2F6DDE', borderRadius: 2, stack: 'y' }},
      {{ label: 'Shorts', data: nn(REV_YT_SHORTS), backgroundColor: '#1B9B96', borderRadius: 2, stack: 'y' }},
      {{ label: 'Lives',  data: nn(REV_YT_LIVES),  backgroundColor: '#E08C2A', borderRadius: 2, stack: 'y' }},
    ],
    stacked: true,
  }},
  // ── Socials page charts ──
  socFollowers: {{
    label: 'Followers — full history',
    type: 'line',
    datasets: () => SOC_FOLLOWERS_DS,
    socials: true,
  }},
  socImpressions: {{
    label: 'Views — full history',
    type: 'bar',
    datasets: () => SOC_IMP_DS,
    socials: true,
  }},
  socER: {{
    label: 'Engagement rate — full history',
    type: 'line',
    datasets: () => SOC_ER_DS,
    pct: true,
    socials: true,
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
  const labels = cfg.socials ? SOC_M : M_FULL;
  wrap.style.width = Math.max(labels.length * 46, 700) + 'px';
  wrap.style.height = '100%';

  const o = opts(cfg.pct || false);
  if (cfg.stacked) {{ o.scales.x.stacked = true; o.scales.y.stacked = true; }}
  o.plugins.legend = {{ display: true, position: 'top',
    labels: {{ color: tc, font: {{ size: 11 }}, boxWidth: 12 }} }};

  _historyChart = new Chart(canvas, {{
    type: cfg.type,
    data: {{ labels: labels, datasets: cfg.datasets() }},
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
      y: {{ min: 0, grid: {{ color: gc }}, ticks: {{ color: tc, font: {{ size: 10 }},
        callback: v => pct ? (v*100).toFixed(0)+'%' : v>=1e6 ? (v/1e6).toFixed(1)+'M' : v>=1e3 ? (v/1e3).toFixed(0)+'K' : v
      }} }}
    }}
  }};
}}

/* ─── Linear regression trendline ─── */
function trendline(values) {{
  // Ignore null/NaN entries when fitting; output is full-length, with nulls preserved at gaps
  const pts = [];
  for (let i = 0; i < values.length; i++) {{
    const v = values[i];
    if (v != null && !isNaN(v)) pts.push([i, v]);
  }}
  if (pts.length < 3) return values.map(() => null);
  const n = pts.length;
  const sx  = pts.reduce((a, p) => a + p[0], 0);
  const sy  = pts.reduce((a, p) => a + p[1], 0);
  const sxy = pts.reduce((a, p) => a + p[0]*p[1], 0);
  const sxx = pts.reduce((a, p) => a + p[0]*p[0], 0);
  const denom = n*sxx - sx*sx;
  if (denom === 0) return values.map(() => null);
  const slope = (n*sxy - sx*sy) / denom;
  const intercept = (sy - slope*sx) / n;
  return values.map((_, i) => slope*i + intercept);
}}
function trendDS(values, baseColor) {{
  return {{
    data: trendline(values),
    borderColor: 'rgba(120, 120, 120, 0.55)',
    borderDash: [4, 4],
    borderWidth: 1.4,
    pointRadius: 0,
    pointHoverRadius: 0,
    fill: false,
    tension: 0,
    label: 'Trend',
    order: 99,
  }};
}}

/* ─── Fanatics partnership start marker (Feb 13, 2026) ─── */
const FANATICS_START_LABEL = {js_fanatics_label};
const fanaticsAnnotationPlugin = {{
  id: 'fanaticsAnnotation',
  afterDraw(chart) {{
    const labels = chart.data && chart.data.labels;
    if (!labels) return;
    const idx = labels.indexOf(FANATICS_START_LABEL);
    if (idx < 0) return;
    const {{ ctx, chartArea, scales }} = chart;
    if (!chartArea || !scales || !scales.x) return;
    const x = scales.x.getPixelForValue(idx);
    if (x < chartArea.left || x > chartArea.right) return;
    ctx.save();
    ctx.strokeStyle = 'rgba(201, 168, 76, 0.55)';
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, chartArea.top);
    ctx.lineTo(x, chartArea.bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(201, 168, 76, 0.95)';
    ctx.font = '600 9px Inter, system-ui, sans-serif';
    ctx.fillText('★ Fanatics S2 start', x + 4, chartArea.top + 11);
    ctx.restore();
  }}
}};
if (typeof Chart !== 'undefined') Chart.register(fanaticsAnnotationPlugin);

function mkBar(id, data, color) {{
  const c = prep(id); if (!c) return;
  const vals = nn(data);
  new Chart(c, {{ type:'bar', data:{{ labels:M, datasets:[
    {{ data:vals, backgroundColor:color, borderRadius:2, label:'' }},
    {{ ...trendDS(vals, color), type:'line' }}
  ] }}, options:opts(false) }});
}}

function mkLine(id, data, color, fill, pct) {{
  const c = prep(id); if (!c) return;
  const vals = nn(data);
  new Chart(c, {{ type:'line', data:{{ labels:M, datasets:[
    {{ data:vals, borderColor:color, backgroundColor:fill, fill:true, tension:.3, pointRadius:2, pointBackgroundColor:color, label:'' }},
    trendDS(vals, color)
  ] }}, options:opts(pct||false) }});
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

  // Revenue charts — 12-month default on-page, full history via ↗ drawer
  if (typeof REV_M12 !== 'undefined' && REV_M12.length > 0) {{
    // Total revenue line
    const rTotalC = document.getElementById('revTotal');
    if (rTotalC) {{
      const wrap = rTotalC.parentElement;
      wrap.style.cssText = 'position:relative;width:' + Math.max(REV_M12.length * 46, 500) + 'px;height:100%';
      new Chart(rTotalC, {{
        type: 'line',
        data: {{ labels: REV_M12, datasets: [{{ data: nn(REV_TOTALS12), borderColor: '#1B7A3A',
          backgroundColor: 'rgba(27,122,58,.08)', fill: true, tension: .3,
          pointRadius: 2, pointBackgroundColor: '#1B7A3A', label: 'Total' }}] }},
        options: revOpts()
      }});
    }}

    // Stacked by source
    const rStackedC = document.getElementById('revStacked');
    if (rStackedC) {{
      const wrap = rStackedC.parentElement;
      wrap.style.cssText = 'position:relative;width:' + Math.max(REV_M12.length * 46, 500) + 'px;height:100%';
      const so = revOpts(); so.scales.x.stacked = true; so.scales.y.stacked = true;
      new Chart(rStackedC, {{
        type: 'bar', data: {{ labels: REV_M12, datasets: REV_STACKED_DS12 }}, options: so
      }});
    }}

    // Source mix doughnut (already last-12-months by design — unchanged)
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
      wrap.style.cssText = 'position:relative;width:' + Math.max(REV_M12.length * 46, 500) + 'px;height:100%';
      new Chart(rYTC, {{
        type: 'bar', data: {{ labels: REV_M12, datasets: [
          {{ label: 'Videos', data: nn(REV_YT_VIDEOS12), backgroundColor: '#2F6DDE', borderRadius: 2, stack: 's' }},
          {{ label: 'Shorts', data: nn(REV_YT_SHORTS12), backgroundColor: '#1B9B96', borderRadius: 2, stack: 's' }},
          {{ label: 'Lives',  data: nn(REV_YT_LIVES12),  backgroundColor: '#E08C2A', borderRadius: 2, stack: 's' }},
        ]}}, options: (() => {{ const o = revOpts(); o.scales.x.stacked = true; o.scales.y.stacked = true; return o; }})()
      }});
    }}
  }}

  // Socials charts — 12-month default on-page, full history via ↗ drawer
  if (typeof SOC_M12 !== 'undefined' && SOC_M12.length > 0) {{
    const SOC_W = Math.max(SOC_M12.length * 46, 500);

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
      type: 'line', data: {{ labels: SOC_M12, datasets: SOC_FOLLOWERS_DS12 }}, options: socOpts(false)
    }});

    // Impressions stacked bar
    const ic = socPrep('socImpressions');
    if (ic) {{
      const o = socOpts(false); o.scales.x.stacked = true; o.scales.y.stacked = true;
      new Chart(ic, {{ type: 'bar', data: {{ labels: SOC_M12, datasets: SOC_IMP_DS12 }}, options: o }});
    }}

    // ER line chart (multi-series)
    const ec = socPrep('socER');
    if (ec) new Chart(ec, {{
      type: 'line', data: {{ labels: SOC_M12, datasets: SOC_ER_DS12 }}, options: socOpts(true)
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

/* ─── Performance Cube (Plotly 3D scatter) ─── */
const CUBE_VIDEOS = {js_all_videos};
const CUBE_TYPE_COLORS = {{ long: '#C9A84C', mid: '#2F6DDE', short: '#1B9B96' }};
const CUBE_TYPE_LABELS = {{ long: 'Full episode', mid: 'Clip', short: 'Short' }};
// Months present in the data, ascending — used to populate filter dropdowns
const CUBE_MONTHS = Array.from(new Set(
  (CUBE_VIDEOS || []).map(v => (v.published || '').slice(0, 7)).filter(Boolean)
)).sort();

function cubeFilter(start, end) {{
  // Keep only videos with usable data and published-month within range
  return CUBE_VIDEOS.filter(v => {{
    const m = (v.published || '').slice(0, 7);
    if (!m || m < start || m > end) return false;
    if (!v.views || v.views < 1) return false;           // log scale needs positive
    if (!v.duration_sec || v.duration_sec < 1) return false;
    return true;
  }});
}}

function cubeRender(start, end) {{
  const empty = document.getElementById('cube-empty');
  const plotEl = document.getElementById('cube-plot');
  if (!plotEl || typeof Plotly === 'undefined') return;

  const videos = cubeFilter(start, end);
  const sum = document.getElementById('cube-summary');
  if (sum) sum.textContent = start + ' → ' + end + ' · ' + videos.length + ' videos';

  if (!videos.length) {{
    plotEl.style.display = 'none';
    if (empty) empty.style.display = 'block';
    return;
  }}
  plotEl.style.display = 'block';
  if (empty) empty.style.display = 'none';

  // Group into 3 traces by content type so the Plotly legend toggles work
  const groups = {{ long: [], mid: [], short: [] }};
  for (const v of videos) {{
    const t = v.type in groups ? v.type : 'mid';
    groups[t].push(v);
  }}

  const traces = ['long', 'mid', 'short'].map(t => {{
    const arr = groups[t];
    const er  = arr.map(v => v.views ? ((v.likes || 0) + (v.comments || 0)) / v.views * 100 : 0);
    const dur = arr.map(v => (v.duration_sec || 0) / 60);
    const hov = arr.map((v, i) =>
      '<b>' + (v.title || '').replace(/</g, '&lt;') + '</b><br>' +
      CUBE_TYPE_LABELS[t] + ' · ' + v.published + '<br>' +
      'Views: ' + (v.views || 0).toLocaleString() + '<br>' +
      'Engagement: ' + er[i].toFixed(2) + '%<br>' +
      'Duration: ' + (dur[i] < 1 ? Math.round(dur[i]*60) + 's' : dur[i].toFixed(1) + ' min') +
      '<extra></extra>'
    );
    return {{
      name: CUBE_TYPE_LABELS[t] + ' (' + arr.length + ')',
      type: 'scatter3d',
      mode: 'markers',
      x: arr.map(v => v.views),
      y: er,
      z: dur,
      text: arr.map(v => v.url),  // stash url for click handler
      hovertemplate: hov,
      marker: {{
        size: 5,
        color: CUBE_TYPE_COLORS[t],
        opacity: 0.78,
        line: {{ width: 0.5, color: '#ffffff' }},
      }},
    }};
  }});

  const layout = {{
    margin: {{ l: 0, r: 0, b: 0, t: 0 }},
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor:  'rgba(0,0,0,0)',
    font: {{ family: 'Inter, system-ui, sans-serif', size: 11, color: '#475569' }},
    legend: {{ orientation: 'h', x: 0, y: -0.05, bgcolor: 'rgba(0,0,0,0)' }},
    scene: {{
      xaxis: {{ title: 'Views', type: 'log', gridcolor: '#E2E5EA', zerolinecolor: '#E2E5EA', backgroundcolor: 'rgba(0,0,0,0)' }},
      yaxis: {{ title: 'Engagement %', gridcolor: '#E2E5EA', zerolinecolor: '#E2E5EA', backgroundcolor: 'rgba(0,0,0,0)' }},
      zaxis: {{ title: 'Duration (min)', gridcolor: '#E2E5EA', zerolinecolor: '#E2E5EA', backgroundcolor: 'rgba(0,0,0,0)' }},
      camera: {{ eye: {{ x: 1.5, y: 1.5, z: 1.0 }} }},
    }},
  }};

  Plotly.react(plotEl, traces, layout, {{ displaylogo: false, responsive: true,
    modeBarButtonsToRemove: ['lasso2d', 'select2d'] }});

  // Open the video on click
  plotEl.on('plotly_click', evt => {{
    const url = evt.points && evt.points[0] && evt.points[0].text;
    if (url) window.open(url, '_blank', 'noopener');
  }});
}}

function cubeMonthsBack(n) {{
  const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - n);
  return d.toISOString().slice(0, 7);
}}
function cubeApplyPreset(preset) {{
  if (!CUBE_MONTHS.length) return;
  const last = CUBE_MONTHS[CUBE_MONTHS.length - 1];
  const first = CUBE_MONTHS[0];
  let start = first;
  if      (preset === '30')  start = cubeMonthsBack(0);
  else if (preset === '90')  start = cubeMonthsBack(2);
  else if (preset === 'ytd') start = last.slice(0, 4) + '-01';
  if (start < first) start = first;
  document.getElementById('cube-start').value = start;
  document.getElementById('cube-end').value   = last;
  cubeRender(start, last);
}}

(function cubeInit() {{
  const startSel = document.getElementById('cube-start');
  const endSel   = document.getElementById('cube-end');
  if (!startSel || !endSel) return;

  if (!CUBE_VIDEOS.length || !CUBE_MONTHS.length) {{
    const plotEl = document.getElementById('cube-plot');
    if (plotEl) plotEl.style.display = 'none';
    const empty = document.getElementById('cube-empty');
    if (empty) empty.style.display = 'block';
    return;
  }}

  for (const m of CUBE_MONTHS) {{
    const o1 = document.createElement('option'); o1.value = m; o1.textContent = m;
    const o2 = o1.cloneNode(true);
    startSel.appendChild(o1); endSel.appendChild(o2);
  }}
  startSel.value = CUBE_MONTHS[0];
  endSel.value   = CUBE_MONTHS[CUBE_MONTHS.length - 1];

  // Render once when the cube page becomes visible (Plotly needs the container to have width)
  const pageEl = document.getElementById('page-cube');
  let rendered = false;
  function maybeRender() {{
    if (rendered || !pageEl) return;
    const visible = pageEl.classList.contains('active');
    if (!visible) return;
    rendered = true;
    cubeRender(startSel.value, endSel.value);
  }}
  // Patch showPage so it triggers a render on first visit
  const origShowPage = window.showPage;
  if (origShowPage) {{
    window.showPage = function(name, el) {{
      origShowPage(name, el);
      if (name === 'cube') setTimeout(maybeRender, 30);
    }};
  }}
  maybeRender();   // also handle case where Cube is loaded as the active page

  function clearPresetActive() {{
    document.querySelectorAll('#page-cube .tc-preset').forEach(b => b.classList.remove('active'));
  }}
  startSel.addEventListener('change', () => {{ clearPresetActive(); cubeRender(startSel.value, endSel.value); }});
  endSel  .addEventListener('change', () => {{ clearPresetActive(); cubeRender(startSel.value, endSel.value); }});
  document.querySelectorAll('#page-cube .tc-preset').forEach(btn => {{
    btn.addEventListener('click', () => {{
      clearPresetActive();
      btn.classList.add('active');
      cubeApplyPreset(btn.dataset.range);
    }});
  }});
}})();

// ═══ Revenue Editor ═══
(function(){{
  const D = REV_EDIT_DATA;
  if (!D || !D.sources) return;
  let PERIODS = D.periods.slice();
  const SOURCES = D.sources.slice();
  let CELLS = Object.assign({{}}, D.cells);
  let ORIGINAL = Object.assign({{}}, D.cells);
  let editing = false;
  const changed = new Set();
  const LS = 'rt_rev_editor_gh';
  const $ = id => document.getElementById(id);
  const key = (s,p) => s+'|'+p;

  const fmtMoney = v => {{
    if (v==='' || v==null) return '';
    if (v==='TBD'||v==='N/A') return v;
    const n = parseFloat(v); if (isNaN(n)) return v;
    return n.toLocaleString('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}});
  }};
  const cellCls = v => v==='' ? 'rev-empty' : (v==='TBD'||v==='N/A' ? 'rev-tbd' : '');

  function render(){{
    const host = $('rev-editable');
    let h = '<div class="table-scroll"><table class="rev-grid"><thead><tr><th class="rev-src">Source</th>';
    for (const p of PERIODS) h += '<th>'+p+'</th>';
    h += '</tr></thead><tbody>';
    for (const s of SOURCES){{
      h += '<tr><td class="rev-src">'+s+'</td>';
      for (const p of PERIODS){{
        const v = CELLS[key(s,p)] ?? '';
        const ch = changed.has(key(s,p)) ? ' rev-changed' : '';
        const ec = editing ? ' rev-cell' : '';
        h += '<td class="'+cellCls(v)+ch+ec+'" data-s="'+s+'" data-p="'+p+'">'+fmtMoney(v)+'</td>';
      }}
      h += '</tr>';
    }}
    h += '</tbody><tfoot><tr class="rev-total"><td class="rev-src">TOTAL</td>';
    for (const p of PERIODS){{
      let sum=0; for (const s of SOURCES){{ const n=parseFloat(CELLS[key(s,p)]); if(!isNaN(n)) sum+=n; }}
      h += '<td>'+sum.toLocaleString('en-US',{{maximumFractionDigits:0}})+'</td>';
    }}
    h += '</tr></tfoot></table></div>';
    host.innerHTML = h;
    if (editing) host.querySelectorAll('td.rev-cell').forEach(td => td.onclick = () => startEdit(td));
  }}

  function startEdit(td){{
    if (!editing || td.querySelector('input')) return;
    const s=td.dataset.s, p=td.dataset.p, raw = CELLS[key(s,p)] ?? '';
    td.classList.add('rev-editing');
    td.innerHTML = '<input value="'+raw+'">';
    const inp = td.querySelector('input'); inp.focus(); inp.select();
    const commit = next => {{ setCell(s,p,inp.value.trim()); td.classList.remove('rev-editing'); renderCell(td,s,p); if(next) focusNext(s,p); }};
    inp.onblur = () => commit(false);
    inp.onkeydown = e => {{
      if(e.key==='Enter'){{e.preventDefault();commit(false);}}
      else if(e.key==='Tab'){{e.preventDefault();commit(true);}}
      else if(e.key==='Escape'){{td.classList.remove('rev-editing');renderCell(td,s,p);}}
    }};
  }}
  function renderCell(td,s,p){{
    const v = CELLS[key(s,p)] ?? '';
    td.className = cellCls(v)+(changed.has(key(s,p))?' rev-changed':'')+(editing?' rev-cell':'');
    td.textContent = fmtMoney(v);
    if (editing) td.onclick = () => startEdit(td);
  }}
  function focusNext(s,p){{
    const si = SOURCES.indexOf(s);
    if (si < SOURCES.length-1){{
      const nt = $('rev-editable').querySelector('td[data-s="'+SOURCES[si+1]+'"][data-p="'+p+'"]');
      if (nt) startEdit(nt);
    }}
  }}
  function setCell(s,p,val){{
    let norm = val.replace(/,/g,'').trim();
    if (/^tbd$/i.test(norm)) norm='TBD'; else if (/^n\/?a$/i.test(norm)) norm='N/A';
    CELLS[key(s,p)] = norm;
    if ((ORIGINAL[key(s,p)]??'') !== norm) changed.add(key(s,p)); else changed.delete(key(s,p));
    updateStatus(); refreshFooter(p);
  }}
  function refreshFooter(p){{
    const idx = PERIODS.indexOf(p);
    const foot = $('rev-editable').querySelector('tfoot tr');
    if (!foot) return;
    let sum=0; for (const s of SOURCES){{ const n=parseFloat(CELLS[key(s,p)]); if(!isNaN(n)) sum+=n; }}
    foot.children[idx+1].textContent = sum.toLocaleString('en-US',{{maximumFractionDigits:0}});
  }}
  function updateStatus(){{
    const n = changed.size;
    $('revSaveBtn').disabled = n===0;
    $('revEditStatus').textContent = n>0 ? (n+' unsaved change'+(n>1?'s':'')) : (editing?'Editing':'');
  }}

  window.revToggleEdit = function(){{
    editing = !editing;
    $('revEditToggle').classList.toggle('on', editing);
    $('revEditToggle').textContent = editing ? '✓ Editing' : '✎ Edit';
    $('rev-readonly').style.display = editing ? 'none' : '';
    $('rev-editable').style.display = editing ? '' : 'none';
    $('revGhBtn').style.display = editing ? '' : 'none';
    $('revSaveBtn').style.display = editing ? '' : 'none';
    $('revAddMonthBtn').style.display = editing ? '' : 'none';
    updateStatus();
    if (editing) render();
  }};

  window.revAddMonth = function(){{
    // Next month after the current newest period (periods are newest-first).
    const latest = PERIODS[0];
    let [y,m] = latest.split('-').map(Number);
    m++; if (m>12){{ m=1; y++; }}
    const np = y + '-' + String(m).padStart(2,'0');
    if (PERIODS.includes(np)){{ return; }}
    PERIODS.unshift(np);                       // add as new newest column
    for (const s of SOURCES) CELLS[key(s,np)] = '';
    render();
    // scroll the grid to reveal the new leftmost column
    const sc = $('rev-editable').querySelector('.table-scroll');
    if (sc) sc.scrollLeft = 0;
  }};

  // CSV: period-desc, source in canonical order, skip empty cells
  function toCSV(){{
    const rows=[['period','source','amount']];
    const periodsDesc = PERIODS.slice().sort().reverse();
    for (const p of periodsDesc) for (const s of SOURCES){{
      const v = CELLS[key(s,p)] ?? ''; if (v==='') continue;
      rows.push([p,s,v]);
    }}
    return rows.map(r=>r.join(',')).join('\\r\\n')+'\\r\\n';
  }}

  // GitHub
  const loadConn = () => {{ try {{ return JSON.parse(localStorage.getItem(LS))||{{}}; }} catch {{ return {{}}; }} }};
  const saveConn = c => localStorage.setItem(LS, JSON.stringify(c));
  function log(m){{ const l=$('revCommitLog'); const d=document.createElement('div'); d.textContent = new Date().toLocaleTimeString()+' — '+m; l.prepend(d); }}
  window.revOpenGh = function(){{
    const c=loadConn();
    $('revGhRepo').value=c.repo||'raindelaymedia/roadtrippin';
    $('revGhBranch').value=c.branch||'';
    $('revGhPath').value=c.path||'master/shows/road_trippin/data/revenue.csv';
    $('revGhToken').value=c.token||'';
    $('revGhModal').classList.add('show');
  }};
  window.revCloseGh = () => $('revGhModal').classList.remove('show');
  window.revSaveConn = function(){{
    saveConn({{repo:$('revGhRepo').value.trim(),branch:$('revGhBranch').value.trim(),path:$('revGhPath').value.trim(),token:$('revGhToken').value.trim()}});
    revCloseGh(); log('Connection saved.');
  }};
  async function gh(url,opts,token){{
    const r = await fetch('https://api.github.com'+url,{{...opts,headers:{{'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',...(opts.headers||{{}})}}}});
    if(!r.ok){{const e=await r.json().catch(()=>({{}}));throw new Error(r.status+' '+(e.message||r.statusText));}}
    return r.json();
  }}
  window.revSave = async function(){{
    const c = loadConn();
    if (!c.token || !c.repo){{ alert('Set up your GitHub connection first (⚙ GitHub).'); revOpenGh(); return; }}
    const st=$('revEditStatus');
    try {{
      st.textContent='Saving…'; $('revSaveBtn').disabled=true;
      let branch=c.branch;
      if(!branch){{ const info=await gh('/repos/'+c.repo,{{}},c.token); branch=info.default_branch||'main'; log('Branch: '+branch); }}
      let sha=null;
      try {{ const cur=await gh('/repos/'+c.repo+'/contents/'+c.path+'?ref='+branch,{{}},c.token); sha=cur.sha; }}
      catch(e){{ if(!String(e).includes('404')) throw e; }}
      const b64 = btoa(unescape(encodeURIComponent(toCSV())));
      const body = {{message:'Update revenue.csv via dashboard editor ('+changed.size+' change'+(changed.size>1?'s':'')+')',content:b64,branch}};
      if(sha) body.sha=sha;
      const res = await gh('/repos/'+c.repo+'/contents/'+c.path,{{method:'PUT',body:JSON.stringify(body)}},c.token);
      ORIGINAL = Object.assign({{}},CELLS); changed.clear();
      st.textContent='Saved ✓'; log('Committed '+(res.commit?.sha?.slice(0,7)||'ok')+' → '+branch);
      render(); setTimeout(updateStatus,2500);
    }} catch(e){{
      st.textContent='Save failed'; log('ERROR: '+e.message);
      alert('Save failed: '+e.message+'\\n\\nCheck token scope (Contents: read/write), repo, and path.');
      $('revSaveBtn').disabled=false;
    }}
  }};
}})();

// ═══ Socials Editor ═══
(function(){{
  const D = SOC_EDIT_DATA;
  if (!D || !D.rows) return;
  let PERIODS = D.periods.slice();
  const ROWS = D.rows.slice();                 // platform / metric / label rows
  const PDISP = D.platformDisplay || {{}};
  let CELLS = Object.assign({{}}, D.cells);
  let ORIGINAL = Object.assign({{}}, D.cells);
  let editing = false;
  const changed = new Set();
  const LS = 'rt_soc_editor_gh';
  const $ = id => document.getElementById(id);
  const key = (pl,mt,pe) => pl+'|'+mt+'|'+pe;

  const isPct = mt => mt==='ENGAGEMENT_RATE';
  function fmtCell(mt, v){{
    if (v==='' || v==null) return '';
    if (v==='TBD'||v==='N/A') return v;
    const n = parseFloat(v); if (isNaN(n)) return v;
    if (isPct(mt)) return n.toFixed(2)+'%';
    return n.toLocaleString('en-US');
  }}
  const cellCls = v => v==='' ? 'rev-empty' : (v==='TBD'||v==='N/A' ? 'rev-tbd' : '');

  function render(){{
    const host = $('soc-editable');
    let h = '<div class="table-scroll"><table class="rev-grid"><thead><tr>'
          + '<th class="rev-src" style="min-width:200px">Platform · Metric</th>';
    for (const p of PERIODS) h += '<th>'+p+'</th>';
    h += '</tr></thead><tbody>';
    let lastPlat = null;
    for (const row of ROWS){{
      const {{platform, metric, label}} = row;
      // platform divider row
      if (platform !== lastPlat){{
        const disp = PDISP[platform] || platform;
        h += '<tr><td class="rev-src" style="background:var(--surface2);font-weight:700;color:var(--text)">'
           + disp + '</td>';
        for (let i=0;i<PERIODS.length;i++) h += '<td style="background:var(--surface2)"></td>';
        h += '</tr>';
        lastPlat = platform;
      }}
      h += '<tr><td class="rev-src" style="padding-left:22px;color:var(--text2)">'+label+'</td>';
      for (const pe of PERIODS){{
        const k = key(platform,metric,pe);
        const v = CELLS[k] ?? '';
        const ch = changed.has(k) ? ' rev-changed' : '';
        const ec = editing ? ' rev-cell' : '';
        h += '<td class="'+cellCls(v)+ch+ec+'" data-pl="'+platform+'" data-mt="'+metric+'" data-pe="'+pe+'">'+fmtCell(metric,v)+'</td>';
      }}
      h += '</tr>';
    }}
    h += '</tbody></table></div>';
    host.innerHTML = h;
    if (editing) host.querySelectorAll('td.rev-cell').forEach(td => td.onclick = () => startEdit(td));
  }}

  function startEdit(td){{
    if (!editing || td.querySelector('input')) return;
    const pl=td.dataset.pl, mt=td.dataset.mt, pe=td.dataset.pe;
    const raw = CELLS[key(pl,mt,pe)] ?? '';
    td.classList.add('rev-editing');
    td.innerHTML = '<input value="'+raw+'">';
    const inp = td.querySelector('input'); inp.focus(); inp.select();
    const commit = next => {{ setCell(pl,mt,pe,inp.value.trim()); td.classList.remove('rev-editing'); renderCell(td,pl,mt,pe); if(next) focusNext(pl,mt,pe); }};
    inp.onblur = () => commit(false);
    inp.onkeydown = e => {{
      if(e.key==='Enter'){{e.preventDefault();commit(false);}}
      else if(e.key==='Tab'){{e.preventDefault();commit(true);}}
      else if(e.key==='Escape'){{td.classList.remove('rev-editing');renderCell(td,pl,mt,pe);}}
    }};
  }}
  function renderCell(td,pl,mt,pe){{
    const v = CELLS[key(pl,mt,pe)] ?? '';
    td.className = cellCls(v)+(changed.has(key(pl,mt,pe))?' rev-changed':'')+(editing?' rev-cell':'');
    td.textContent = fmtCell(mt,v);
    if (editing) td.onclick = () => startEdit(td);
  }}
  function focusNext(pl,mt,pe){{
    const idx = ROWS.findIndex(r => r.platform===pl && r.metric===mt);
    if (idx < ROWS.length-1){{
      const nr = ROWS[idx+1];
      const nt = $('soc-editable').querySelector('td[data-pl="'+nr.platform+'"][data-mt="'+nr.metric+'"][data-pe="'+pe+'"]');
      if (nt) startEdit(nt);
    }}
  }}
  function setCell(pl,mt,pe,val){{
    let norm = val.replace(/,/g,'').replace(/%/g,'').trim();
    if (/^tbd$/i.test(norm)) norm='TBD'; else if (/^n[/]?a$/i.test(norm)) norm='N/A';
    CELLS[key(pl,mt,pe)] = norm;
    if ((ORIGINAL[key(pl,mt,pe)]??'') !== norm) changed.add(key(pl,mt,pe)); else changed.delete(key(pl,mt,pe));
    updateStatus();
  }}
  function updateStatus(){{
    const n = changed.size;
    $('socSaveBtn').disabled = n===0;
    $('socEditStatus').textContent = n>0 ? (n+' unsaved change'+(n>1?'s':'')) : (editing?'Editing':'');
  }}

  window.socToggleEdit = function(){{
    editing = !editing;
    $('socEditToggle').classList.toggle('on', editing);
    $('socEditToggle').textContent = editing ? '✓ Editing' : '✎ Edit';
    $('soc-readonly').style.display = editing ? 'none' : '';
    $('soc-editable').style.display = editing ? '' : 'none';
    $('socGhBtn').style.display = editing ? '' : 'none';
    $('socSaveBtn').style.display = editing ? '' : 'none';
    $('socAddMonthBtn').style.display = editing ? '' : 'none';
    updateStatus();
    if (editing) render();
  }};

  window.socAddMonth = function(){{
    const latest = PERIODS[0];
    let [y,m] = latest.split('-').map(Number);
    m++; if (m>12){{ m=1; y++; }}
    const np = y + '-' + String(m).padStart(2,'0');
    if (PERIODS.includes(np)) return;
    PERIODS.unshift(np);
    for (const r of ROWS) CELLS[key(r.platform,r.metric,np)] = '';
    render();
    const sc = $('soc-editable').querySelector('.table-scroll');
    if (sc) sc.scrollLeft = 0;
  }};

  // CSV: long format period,platform,metric,value — period-desc. ER back to fraction.
  function toCSV(){{
    const rows=[['period','platform','metric','value']];
    const periodsDesc = PERIODS.slice().sort().reverse();
    // group by period, then platform order as in ROWS, then metric
    const seen = new Set();
    for (const pe of periodsDesc){{
      for (const r of ROWS){{
        const k = key(r.platform,r.metric,pe);
        if (seen.has(k)) continue; seen.add(k);
        let v = CELLS[k] ?? '';
        if (v==='') continue;
        if (isPct(r.metric) && v!=='TBD' && v!=='N/A'){{
          const n = parseFloat(v); if(!isNaN(n)) v = (n/100).toFixed(4);   // percent -> fraction
        }}
        rows.push([pe, r.platform, r.metric, v]);
      }}
    }}
    return rows.map(r=>r.join(',')).join('\\r\\n')+'\\r\\n';
  }}

  const loadConn = () => {{ try {{ return JSON.parse(localStorage.getItem(LS))||{{}}; }} catch {{ return {{}}; }} }};
  const saveConn = c => localStorage.setItem(LS, JSON.stringify(c));
  function log(m){{ const l=$('socCommitLog'); const d=document.createElement('div'); d.textContent = new Date().toLocaleTimeString()+' — '+m; l.prepend(d); }}
  window.socOpenGh = function(){{
    const c=loadConn();
    $('socGhRepo').value=c.repo||'raindelaymedia/roadtrippin';
    $('socGhBranch').value=c.branch||'';
    $('socGhPath').value=c.path||'master/shows/road_trippin/data/socials.csv';
    $('socGhToken').value=c.token||'';
    $('socGhModal').classList.add('show');
  }};
  window.socCloseGh = () => $('socGhModal').classList.remove('show');
  window.socSaveConn = function(){{
    saveConn({{repo:$('socGhRepo').value.trim(),branch:$('socGhBranch').value.trim(),path:$('socGhPath').value.trim(),token:$('socGhToken').value.trim()}});
    socCloseGh(); log('Connection saved.');
  }};
  async function gh(url,opts,token){{
    const r = await fetch('https://api.github.com'+url,{{...opts,headers:{{'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',...(opts.headers||{{}})}}}});
    if(!r.ok){{const e=await r.json().catch(()=>({{}}));throw new Error(r.status+' '+(e.message||r.statusText));}}
    return r.json();
  }}
  window.socSave = async function(){{
    const c = loadConn();
    if (!c.token || !c.repo){{ alert('Set up your GitHub connection first (⚙ GitHub).'); socOpenGh(); return; }}
    const st=$('socEditStatus');
    try {{
      st.textContent='Saving…'; $('socSaveBtn').disabled=true;
      let branch=c.branch;
      if(!branch){{ const info=await gh('/repos/'+c.repo,{{}},c.token); branch=info.default_branch||'main'; log('Branch: '+branch); }}
      let sha=null;
      try {{ const cur=await gh('/repos/'+c.repo+'/contents/'+c.path+'?ref='+branch,{{}},c.token); sha=cur.sha; }}
      catch(e){{ if(!String(e).includes('404')) throw e; }}
      const b64 = btoa(unescape(encodeURIComponent(toCSV())));
      const body = {{message:'Update socials.csv via dashboard editor ('+changed.size+' change'+(changed.size>1?'s':'')+')',content:b64,branch}};
      if(sha) body.sha=sha;
      const res = await gh('/repos/'+c.repo+'/contents/'+c.path,{{method:'PUT',body:JSON.stringify(body)}},c.token);
      ORIGINAL = Object.assign({{}},CELLS); changed.clear();
      st.textContent='Saved ✓'; log('Committed '+(res.commit?.sha?.slice(0,7)||'ok')+' → '+branch);
      render(); setTimeout(updateStatus,2500);
    }} catch(e){{
      st.textContent='Save failed'; log('ERROR: '+e.message);
      alert('Save failed: '+e.message+'\\n\\nCheck token scope (Contents: read/write), repo, and path.');
      $('socSaveBtn').disabled=false;
    }}
  }};
}})();
</script>
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