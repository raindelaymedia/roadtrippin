"""
master_template.py — renders the Rain Delay Media network dashboard HTML.

Single-purpose: build_master_html(...) takes the orchestrator's computed data
and returns a complete standalone index.html string. No external dependencies
on the per-show templates — keeps CSS scopes clean.
"""

import json


def _fmt_money(n, places=0):
    if n is None: return "—"
    return f"${n:,.{places}f}"

def _fmt_money_short(n):
    """Compact money: $1.5M, $502K, $522, etc."""
    n = float(n or 0)
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:,.0f}"

def _fmt_num(n):
    if n is None: return "—"
    return f"{n:,.0f}"

def _fmt_num_short(n):
    n = float(n or 0)
    if abs(n) >= 1_000_000: return f"{n/1_000_000:.2f}M"
    if abs(n) >= 1_000:     return f"{n/1_000:.1f}K"
    return f"{n:,.0f}"

def _fmt_month_label(ym):
    """'2026-05' → 'May 2026'."""
    if not ym: return "—"
    try:
        y, m = ym.split("-")
        months = ["", "January","February","March","April","May","June",
                  "July","August","September","October","November","December"]
        return f"{months[int(m)]} {y}"
    except Exception:
        return ym


def _render_split_tier_bar(cum_gross):
    """HTML progress bar visualizing tier position. Shows $0/$500k/$1M with
    fill colored by tier."""
    upper = max(1_500_000, cum_gross * 1.15)
    pct = lambda v: max(0, min(100, (v / upper) * 100))

    fill_pct  = pct(cum_gross)
    p500      = pct(500_000)
    p1m       = pct(1_000_000)

    # Segment ranges (in % units): each tier contributes only the portion
    # of the fill that falls within its band.
    s1_lo, s1_hi = 0,    min(p500, fill_pct)
    s2_lo, s2_hi = (p500, min(p1m, fill_pct)) if fill_pct > p500 else (p500, p500)
    s3_lo, s3_hi = (p1m,  fill_pct)            if fill_pct > p1m  else (p1m,  p1m)

    def seg(lo, hi, color):
        w = hi - lo
        if w <= 0: return ""
        return f'<div class="tier-seg" style="left:{lo}%;width:{w}%;background:{color}"></div>'

    return f"""
    <div class="tier-bar-wrap">
      <div class="tier-bar-bg"></div>
      {seg(s1_lo, s1_hi, "#94A3B8")}
      {seg(s2_lo, s2_hi, "#F59E0B")}
      {seg(s3_lo, s3_hi, "#16A34A")}
      <div class="tier-marker" style="left:{p500}%"><div class="tier-marker-line"></div>
        <div class="tier-marker-label">$500K<br><span>20% tier</span></div></div>
      <div class="tier-marker" style="left:{p1m}%"><div class="tier-marker-line"></div>
        <div class="tier-marker-label">$1M<br><span>25% tier</span></div></div>
      <div class="tier-current" style="left:{fill_pct}%">
        <div class="tier-current-dot"></div>
        <div class="tier-current-label">{_fmt_money_short(cum_gross)}</div>
      </div>
    </div>"""


def _render_split_panel(s):
    """One full Revenue Split Tracker block for a single show."""
    cum = s["cum_gross"]
    rate_pct = int(s["tier_rate"] * 100)
    tier_index = s["tier_index"]

    # Status badge: where are we relative to thresholds
    if cum < 500_000:
        status_color = "#94A3B8"
        status_text  = f"{_fmt_money_short(s['to_500k'])} to reach $500K threshold"
    elif cum < 1_000_000:
        crossed = s.get("crossed_500k_month")
        status_color = "#F59E0B"
        when = f" in {_fmt_month_label(crossed)}" if crossed else ""
        status_text  = f"Past $500K{when} — earning 20% on the next "f"{_fmt_money_short(s['to_1m'])} to $1M"
    else:
        status_color = "#16A34A"
        status_text  = f"Past $1M — earning 25% on every dollar over $1M ({_fmt_money_short(s['past_1m'])} past so far)"

    # Quarter-cut math breakdown
    cum_start = s["cum_before_quarter"]
    cum_end   = s["cum_through_now"]
    q_rev     = s["quarter_revenue"]
    q_cut     = s["rdm_cut_quarter"]

    # Build a tier-by-tier breakdown for the quarter
    def tier_slice(low, high, rate):
        applied_low  = max(cum_start, low)
        applied_high = min(cum_end,   high)
        slice_amt    = max(0.0, applied_high - applied_low)
        return slice_amt, slice_amt * rate

    t1_amt, t1_cut = tier_slice(0,         500_000,        0.00)
    t2_amt, t2_cut = tier_slice(500_000,   1_000_000,      0.20)
    t3_amt, t3_cut = tier_slice(1_000_000, float("inf"),   0.25)

    breakdown_rows = []
    if t1_amt > 0.01:
        breakdown_rows.append(
            f"<tr><td>Below $500K (0%)</td><td>{_fmt_money(t1_amt, 2)}</td>"
            f"<td>0%</td><td class='td-cut'>$0.00</td></tr>"
        )
    if t2_amt > 0.01:
        breakdown_rows.append(
            f"<tr><td>$500K – $1M tier (20%)</td><td>{_fmt_money(t2_amt, 2)}</td>"
            f"<td>20%</td><td class='td-cut'>{_fmt_money(t2_cut, 2)}</td></tr>"
        )
    if t3_amt > 0.01:
        breakdown_rows.append(
            f"<tr><td>Above $1M tier (25%)</td><td>{_fmt_money(t3_amt, 2)}</td>"
            f"<td>25%</td><td class='td-cut'>{_fmt_money(t3_cut, 2)}</td></tr>"
        )

    breakdown_html = "".join(breakdown_rows) or (
        "<tr><td colspan='4' style='color:var(--mut);text-align:center;padding:14px'>"
        "No revenue accrued in this quarter yet.</td></tr>"
    )

    return f"""
<section class="split-panel">
  <div class="split-head">
    <div class="split-show-tag" style="background:{s['color']}">{s.get('tag','')}</div>
    <div>
      <h3 class="split-show-name">{s['name']}</h3>
      <div class="split-show-sub">Revenue Split Tracker · since {_fmt_month_label(s['launch'])}</div>
    </div>
    <div class="split-rate-pill" style="background:{status_color}">
      Current rate: {rate_pct}%
    </div>
  </div>

  <div class="split-headline">
    <div class="split-headline-l">
      <div class="lbl">Lifetime gross revenue</div>
      <div class="val">{_fmt_money(cum, 2)}</div>
      <div class="status" style="color:{status_color}">{status_text}</div>
    </div>
    <div class="split-headline-r">
      <div class="lbl">RDM lifetime cut</div>
      <div class="val val-rdm">{_fmt_money(s['rdm_cut_lifetime'], 2)}</div>
      <div class="status">Total earned to date</div>
    </div>
  </div>

  {_render_split_tier_bar(cum)}

  <div class="split-quarter">
    <div class="split-quarter-head">
      <div>
        <div class="lbl">{s['quarter_label']} <span class="mut">({s['quarter_start']} – {s['quarter_end']})</span></div>
        <div class="quarter-title">RDM Cut for Current Quarter</div>
      </div>
      <div class="quarter-cut-box">
        <div class="lbl">Owed to RDM</div>
        <div class="quarter-cut-val">{_fmt_money(q_cut, 2)}</div>
      </div>
    </div>

    <div class="quarter-stats">
      <div><span class="lbl">Cum. entering quarter</span><span class="v">{_fmt_money(cum_start, 2)}</span></div>
      <div><span class="lbl">Revenue this quarter</span><span class="v">{_fmt_money(q_rev, 2)}</span></div>
      <div><span class="lbl">Cum. through today</span><span class="v">{_fmt_money(cum_end, 2)}</span></div>
    </div>

    <div class="quarter-breakdown">
      <div class="lbl bd-lbl">Tier-by-tier breakdown (auditable math for invoicing)</div>
      <table class="bd-table">
        <thead><tr><th>Tier</th><th>Revenue in tier (this quarter)</th><th>Rate</th><th class="th-cut">RDM cut</th></tr></thead>
        <tbody>{breakdown_html}</tbody>
        <tfoot><tr>
          <td colspan="3" style="text-align:right;font-weight:600">Total Q3 RDM cut:</td>
          <td class="td-cut" style="font-weight:700;font-size:15px">{_fmt_money(q_cut, 2)}</td>
        </tr></tfoot>
      </table>
    </div>
  </div>
</section>
"""


def _render_show_card(s):
    return f"""
<a class="show-card" href="{s['dashboard_url']}" target="_blank" rel="noopener">
  <div class="show-card-head">
    <div class="show-card-tag" style="background:{s['color']}">{s.get('tag','')}</div>
    <div>
      <div class="show-card-name">{s['name']}</div>
    </div>
    <div class="show-card-arrow">↗</div>
  </div>
  <div class="show-card-stats">
    <div><div class="lbl">YT Subs</div><div class="v">{_fmt_num_short(s['subs'])}</div></div>
    <div><div class="lbl">MTD Gross</div><div class="v">{_fmt_money_short(s['mtd_gross'])}</div></div>
    <div><div class="lbl">Eps 30d</div><div class="v">{_fmt_num(s['eps_30d'])}</div></div>
    <div><div class="lbl">Lifetime</div><div class="v">{_fmt_money_short(s['cum_gross'])}</div></div>
  </div>
  <div class="show-card-cta">Open full dashboard →</div>
</a>"""


def build_master_html(rdm_summary, show_summaries, quarter_label,
                       quarter_window, generated_at):
    rdm = rdm_summary

    kpi_cards = f"""
<div class="kpi-row">
  <div class="kpi">
    <div class="kpi-lbl">Active Shows</div>
    <div class="kpi-val">{rdm['active_shows']}</div>
    <div class="kpi-sub">In the RDM network</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">Network Revenue (MTD)</div>
    <div class="kpi-val">{_fmt_money_short(rdm['network_mtd_gross'])}</div>
    <div class="kpi-sub">Gross, current month</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">{quarter_label} RDM Cut</div>
    <div class="kpi-val kpi-val-accent">{_fmt_money_short(rdm['network_q_cut'])}</div>
    <div class="kpi-sub">Owed to RDM this quarter</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">Episodes (Last 30d)</div>
    <div class="kpi-val">{_fmt_num(rdm['network_eps_30d'])}</div>
    <div class="kpi-sub">Across {rdm['active_shows']} show{'s' if rdm['active_shows']!=1 else ''}</div>
  </div>
  <div class="kpi">
    <div class="kpi-lbl">YT Subscribers</div>
    <div class="kpi-val">{_fmt_num_short(rdm['network_subs'])}</div>
    <div class="kpi-sub">Network total</div>
  </div>
</div>
"""

    split_panels = "\n".join(_render_split_panel(s) for s in show_summaries)
    show_cards   = "\n".join(_render_show_card(s)   for s in show_summaries)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Rain Delay Media — Network Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg:        #F6F7F9;
    --surface:   #FFFFFF;
    --surface2:  #F1F3F6;
    --border:    #E2E5EA;
    --ink:       #0F172A;
    --text:      #1E293B;
    --text2:     #475569;
    --mut:       #94A3B8;
    --brand:     #1E3A5F;
    --brand2:    #3B82F6;
    --gold:      #C9A84C;
    --green:     #16A34A;
    --amber:     #F59E0B;
    --rose:      #DC2626;
    --radius:    10px;
    --shadow:    0 1px 2px rgba(15,23,41,.04), 0 2px 8px rgba(15,23,41,.04);
  }}
  *  {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 0;
    font-family: 'Inter', -apple-system, system-ui, sans-serif;
    color: var(--text); background: var(--bg);
    font-size: 14px; line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }}

  /* ─── Top header bar ─── */
  .topbar {{
    background: var(--ink);
    color: #fff;
    padding: 18px 32px;
    display: flex; align-items: center; justify-content: space-between;
  }}
  .brand {{ display: flex; align-items: center; gap: 12px; }}
  .brand-logo {{
    width: 38px; height: 38px; border-radius: 8px;
    background: linear-gradient(135deg, var(--brand2) 0%, var(--gold) 100%);
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; color: #fff; font-size: 15px; letter-spacing: -.5px;
  }}
  .brand-name {{ font-size: 18px; font-weight: 700; letter-spacing: -.3px; }}
  .brand-sub  {{ font-size: 11px; color: #94A3B8; letter-spacing: .15em; text-transform: uppercase; margin-top: 2px; }}
  .topbar-r   {{ display: flex; gap: 18px; align-items: center; font-size: 12px; color: #94A3B8; }}
  .topbar-r .updated {{ letter-spacing: .08em; text-transform: uppercase; font-size: 10px; }}
  .topbar-r .date {{ color: #fff; font-weight: 500; font-size: 13px; }}

  /* ─── Page ─── */
  .page {{
    max-width: 1280px;
    margin: 0 auto;
    padding: 36px 32px 80px;
  }}
  .page-h {{
    display: flex; justify-content: space-between; align-items: flex-end;
    margin-bottom: 28px;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--border);
  }}
  .page-h h1 {{
    font-size: 28px; font-weight: 700; letter-spacing: -.6px;
    margin: 0; color: var(--ink);
  }}
  .page-h .sub {{ color: var(--text2); font-size: 14px; margin-top: 4px; }}
  .page-h .quarter-pill {{
    background: var(--surface); border: 1px solid var(--border);
    padding: 6px 14px; border-radius: 100px;
    font-size: 12px; font-weight: 600; color: var(--text2);
    letter-spacing: .04em;
  }}
  .page-h .quarter-pill strong {{ color: var(--ink); }}
  .page-h-pills {{
    display: flex; flex-direction: column; gap: 6px; align-items: flex-end;
  }}
  .page-h .fanatics-pill {{
    background: rgba(201, 168, 76, 0.10);
    border: 1px solid rgba(201, 168, 76, 0.4);
    color: var(--ink);
    padding: 6px 14px; border-radius: 100px;
    font-size: 11px; font-weight: 600;
    letter-spacing: .03em;
  }}

  /* ─── KPI cards ─── */
  .kpi-row {{
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 14px;
    margin-bottom: 28px;
  }}
  .kpi {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px 18px;
    box-shadow: var(--shadow);
  }}
  .kpi-lbl {{
    font-size: 10px; font-weight: 600;
    color: var(--text2); letter-spacing: .12em;
    text-transform: uppercase; margin-bottom: 8px;
  }}
  .kpi-val {{ font-size: 26px; font-weight: 700; color: var(--ink); letter-spacing: -.6px; line-height: 1.1; }}
  .kpi-val-accent {{ color: var(--gold); }}
  .kpi-sub {{ font-size: 11px; color: var(--mut); margin-top: 4px; }}

  /* ─── Section heading ─── */
  .sec-h {{
    display: flex; justify-content: space-between; align-items: baseline;
    margin: 32px 0 14px;
  }}
  .sec-h h2 {{
    font-size: 13px; font-weight: 700; color: var(--text);
    text-transform: uppercase; letter-spacing: .12em; margin: 0;
  }}
  .sec-h .r {{ font-size: 11px; color: var(--mut); letter-spacing: .04em; }}

  /* ─── Revenue Split Panel ─── */
  .split-panel {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px 26px;
    margin-bottom: 18px;
    box-shadow: var(--shadow);
  }}
  .split-head {{
    display: flex; align-items: center; gap: 14px;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 18px;
  }}
  .split-show-tag {{
    width: 38px; height: 38px;
    color: #fff; font-weight: 700; font-size: 13px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 8px; letter-spacing: .04em;
  }}
  .split-show-name {{ margin: 0; font-size: 18px; font-weight: 700; color: var(--ink); letter-spacing: -.3px; }}
  .split-show-sub  {{ font-size: 12px; color: var(--text2); margin-top: 2px; }}
  .split-rate-pill {{
    margin-left: auto;
    color: #fff; font-size: 12px; font-weight: 600;
    padding: 6px 14px; border-radius: 100px;
    letter-spacing: .04em;
  }}

  .split-headline {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 24px;
    padding: 14px 0 20px;
  }}
  .split-headline .lbl {{
    font-size: 10px; font-weight: 600; color: var(--mut);
    text-transform: uppercase; letter-spacing: .12em; margin-bottom: 6px;
  }}
  .split-headline .val {{
    font-size: 32px; font-weight: 800; color: var(--ink);
    letter-spacing: -.8px; line-height: 1.1;
    font-family: 'JetBrains Mono', monospace;
  }}
  .split-headline .val-rdm {{ color: var(--gold); }}
  .split-headline .status {{ font-size: 12px; color: var(--text2); margin-top: 8px; }}
  .split-headline-r {{ text-align: right; }}
  .split-headline-r .lbl {{ text-align: right; }}

  /* tier progress bar */
  .tier-bar-wrap {{
    position: relative; height: 84px;
    margin: 22px 0 32px;
  }}
  .tier-bar-bg {{
    position: absolute; top: 0; left: 0; right: 0; height: 36px;
    background: #EEF1F5; border-radius: 4px;
  }}
  .tier-seg {{
    position: absolute; top: 0; height: 36px;
    border-radius: 0;
  }}
  .tier-seg:first-of-type {{ border-radius: 4px 0 0 4px; }}
  .tier-marker {{
    position: absolute; top: 0; height: 100%;
    transform: translateX(-50%);
  }}
  .tier-marker-line {{
    width: 2px; height: 44px; background: var(--ink); opacity: .4;
    margin: 0 auto;
  }}
  .tier-marker-label {{
    font-size: 10px; font-weight: 700; color: var(--ink);
    text-align: center; white-space: nowrap; margin-top: 4px;
    letter-spacing: .04em;
  }}
  .tier-marker-label span {{ color: var(--text2); font-weight: 500; font-size: 9px; letter-spacing: .08em; }}
  .tier-current {{
    position: absolute; top: 0; transform: translateX(-50%);
  }}
  .tier-current-dot {{
    width: 14px; height: 14px; background: var(--ink); border: 3px solid #fff;
    border-radius: 50%; margin: 11px auto 0;
    box-shadow: 0 0 0 1px var(--ink);
  }}
  .tier-current-label {{
    font-size: 11px; font-weight: 700; color: var(--ink);
    background: var(--ink); color: #fff; padding: 3px 7px;
    border-radius: 4px; margin-top: 6px;
    white-space: nowrap; text-align: center;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: -.02em;
  }}

  /* ─── Quarter cut block ─── */
  .split-quarter {{
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 18px 22px;
  }}
  .split-quarter-head {{
    display: flex; justify-content: space-between; align-items: flex-start;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }}
  .split-quarter-head .lbl {{
    font-size: 11px; font-weight: 600; color: var(--text2);
    letter-spacing: .08em; text-transform: uppercase;
  }}
  .split-quarter-head .lbl .mut {{ color: var(--mut); font-weight: 500; text-transform: none; letter-spacing: .02em; }}
  .quarter-title {{ font-size: 17px; font-weight: 700; color: var(--ink); margin-top: 6px; letter-spacing: -.3px; }}
  .quarter-cut-box {{ text-align: right; }}
  .quarter-cut-val {{
    font-size: 30px; font-weight: 800; color: var(--gold);
    font-family: 'JetBrains Mono', monospace; letter-spacing: -.6px;
    margin-top: 4px;
  }}

  .quarter-stats {{
    display: grid; grid-template-columns: repeat(3, 1fr);
    gap: 14px;
    padding: 16px 0;
    border-bottom: 1px solid var(--border);
  }}
  .quarter-stats > div {{ display: flex; flex-direction: column; gap: 4px; }}
  .quarter-stats .lbl {{
    font-size: 10px; font-weight: 600; color: var(--mut);
    text-transform: uppercase; letter-spacing: .1em;
  }}
  .quarter-stats .v {{
    font-size: 16px; font-weight: 700; color: var(--ink);
    font-family: 'JetBrains Mono', monospace; letter-spacing: -.3px;
  }}

  .quarter-breakdown {{ padding-top: 14px; }}
  .bd-lbl {{
    font-size: 10px; font-weight: 600; color: var(--text2);
    text-transform: uppercase; letter-spacing: .12em; margin-bottom: 10px;
  }}
  .bd-table {{
    width: 100%; border-collapse: collapse; font-size: 12px;
  }}
  .bd-table th, .bd-table td {{
    padding: 10px 12px; text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  .bd-table th {{
    font-weight: 600; color: var(--text2); font-size: 10px;
    text-transform: uppercase; letter-spacing: .08em;
    background: var(--surface); border-radius: 4px 4px 0 0;
  }}
  .bd-table .th-cut, .bd-table .td-cut {{ text-align: right; font-family: 'JetBrains Mono', monospace; }}
  .bd-table .td-cut {{ color: var(--gold); font-weight: 600; }}
  .bd-table td:nth-child(2), .bd-table td:nth-child(3) {{ font-family: 'JetBrains Mono', monospace; color: var(--text); }}
  .bd-table tfoot td {{ border-bottom: none; padding-top: 14px; color: var(--ink); }}

  /* ─── Show cards ─── */
  .show-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 14px;
  }}
  .show-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
    text-decoration: none;
    color: var(--text);
    transition: transform .12s, box-shadow .12s, border-color .12s;
    box-shadow: var(--shadow);
    display: block;
  }}
  .show-card:hover {{
    transform: translateY(-2px);
    border-color: var(--brand2);
    box-shadow: 0 4px 14px rgba(15,23,41,.08);
  }}
  .show-card-head {{
    display: flex; align-items: center; gap: 12px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 14px;
  }}
  .show-card-tag {{
    width: 32px; height: 32px;
    color: #fff; font-weight: 700; font-size: 11px;
    display: flex; align-items: center; justify-content: center;
    border-radius: 6px;
  }}
  .show-card-name {{ font-weight: 700; font-size: 15px; color: var(--ink); letter-spacing: -.2px; }}
  .show-card-launch {{ font-size: 11px; color: var(--mut); margin-top: 2px; }}
  .show-card-arrow {{
    margin-left: auto; color: var(--mut); font-size: 18px;
    transition: color .12s, transform .12s;
  }}
  .show-card:hover .show-card-arrow {{ color: var(--brand2); transform: translate(2px, -2px); }}

  .show-card-stats {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 8px;
  }}
  .show-card-stats > div {{ display: flex; flex-direction: column; gap: 2px; }}
  .show-card-stats .lbl {{
    font-size: 9px; font-weight: 600; color: var(--mut);
    text-transform: uppercase; letter-spacing: .1em;
  }}
  .show-card-stats .v {{
    font-size: 15px; font-weight: 700; color: var(--ink);
    font-family: 'JetBrains Mono', monospace; letter-spacing: -.2px;
  }}

  .show-card-cta {{
    margin-top: 14px; padding-top: 12px;
    border-top: 1px solid var(--border);
    font-size: 11px; font-weight: 600; color: var(--brand2);
    letter-spacing: .04em;
  }}

  /* ─── Coming soon block ─── */
  .coming-soon {{
    background: var(--surface);
    border: 1px dashed var(--border);
    border-radius: var(--radius);
    padding: 30px;
    text-align: center;
    color: var(--mut);
    font-size: 13px;
    line-height: 1.6;
  }}
  .coming-soon strong {{ color: var(--text2); font-weight: 600; }}

  /* ─── Footer ─── */
  .footer {{
    margin-top: 60px; padding: 20px 0;
    border-top: 1px solid var(--border);
    text-align: center;
    color: var(--mut); font-size: 11px;
    letter-spacing: .04em;
  }}

  /* ─── Mobile ─── */
  @media (max-width: 900px) {{
    .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
    .split-headline {{ grid-template-columns: 1fr; gap: 18px; }}
    .split-headline-r {{ text-align: left; }}
    .split-headline-r .lbl {{ text-align: left; }}
    .quarter-stats {{ grid-template-columns: 1fr; }}
    .split-quarter-head {{ flex-direction: column; gap: 12px; }}
    .quarter-cut-box {{ text-align: left; }}
  }}
</style>
</head>
<body>

<div class="topbar">
  <div class="brand">
    <div class="brand-logo">RDM</div>
    <div>
      <div class="brand-name">Rain Delay Media</div>
      <div class="brand-sub">Network Operations</div>
    </div>
  </div>
  <div class="topbar-r">
    <div>
      <div class="updated">Last Updated</div>
      <div class="date">{generated_at}</div>
    </div>
  </div>
</div>

<div class="page">
  <div class="page-h">
    <div>
      <h1>Network Dashboard</h1>
      <div class="sub">Cross-show performance, revenue, and RDM participation tracking</div>
    </div>
    <div class="page-h-pills">
      <div class="quarter-pill">Current quarter: <strong>{quarter_label}</strong> · {quarter_window}</div>
      <div class="fanatics-pill">★ Fanatics S2 · Oct 1, 2025 → Sep 30, 2026</div>
    </div>
  </div>

  {kpi_cards}

  <div class="sec-h">
    <h2>★ Revenue Split Tracker</h2>
    <span class="r">Lifetime cumulative · auditable math for invoicing</span>
  </div>
  {split_panels}

  <div class="sec-h">
    <h2>Shows</h2>
    <span class="r">{rdm['active_shows']} active · click any card to open the full dashboard</span>
  </div>
  <div class="show-grid">{show_cards}</div>

  <div class="sec-h">
    <h2>Network Top Content &amp; Recent Episodes</h2>
    <span class="r">v1.5</span>
  </div>
  <div class="coming-soon">
    <strong>Coming next iteration.</strong><br>
    Once we have a second show on the network, this section will surface top-performing
    videos and recent episodes across all shows, with cross-show ranking and filters.
    Until then, the per-show breakdowns live in each show's own dashboard.
  </div>

  <div class="footer">
    Rain Delay Media · Network Dashboard · Built {generated_at}
  </div>
</div>

</body></html>
"""