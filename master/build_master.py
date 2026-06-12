"""
build_master.py — Rain Delay Media network dashboard orchestrator.

Walks the shows/ registry, reads each show's standard data files (revenue.csv,
tracker_data.json, socials.csv), computes network-level aggregates and the
RDM revenue-split tracker, and renders master/index.html via master_template.

Usage (from the master/ dir):
    python build_master.py

Add a new show by dropping its folder under shows/<key>/data/ and registering
it in the SHOWS list below.
"""

import os, csv, json, argparse
from datetime import date, datetime
from collections import defaultdict

from master_template import build_master_html

# ─────────────────────────────────────────────────────────────────────────
# Registry — one entry per show in the network.
# `launch` is YYYY-MM (used for lifetime cumulative anchor).
# `data_dir` is relative to this script's location.
# ─────────────────────────────────────────────────────────────────────────
SHOWS = [
    {
        "key":           "road_trippin",
        "name":          "Road Trippin'",
        "tag":           "RT",
        "launch":        "2024-06",        # earliest revenue period in CSV
        "data_dir":      "shows/road_trippin/data",
        "dashboard_url": "master/shows/road_trippin/road_trippin.html",
        "color":         "#0EA5E9",         # show accent color
    },
    # Future shows: just add another dict here.
]

# Revenue-split tiers per RT × RDM contract §5.1
# Progressive: each tier rate applies only to the slice of cumulative gross
# that falls in that band.
SPLIT_TIERS = [
    (0,           500_000,        0.00),
    (500_000,     1_000_000,      0.20),
    (1_000_000,   float("inf"),   0.25),
]


# ─── Math ────────────────────────────────────────────────────────────────
def split_at(cum_gross):
    """Total RDM cut owed at a given cumulative-gross level (lifetime)."""
    total = 0.0
    for low, high, rate in SPLIT_TIERS:
        if cum_gross > low:
            total += (min(cum_gross, high) - low) * rate
    return total


def cut_during(cum_start, cum_end):
    """RDM cut earned on revenue accrued between two cumulative checkpoints."""
    return split_at(cum_end) - split_at(cum_start)


def current_tier(cum_gross):
    """Return (tier_index, low, high, rate) for the band cum_gross sits in."""
    for i, (low, high, rate) in enumerate(SPLIT_TIERS):
        if cum_gross <= high:
            return i, low, high, rate
    return len(SPLIT_TIERS) - 1, *SPLIT_TIERS[-1]


def current_fiscal_quarter(today=None):
    """
    RDM fiscal year starts October 1.
    Q1 = Oct–Dec, Q2 = Jan–Mar, Q3 = Apr–Jun, Q4 = Jul–Sep.
    Returns (label, start_date, end_date, fy_year).
    """
    if today is None:
        today = date.today()
    y, m = today.year, today.month
    if m in (10, 11, 12):
        return (f"Q1 FY{y+1}", date(y,   10, 1), date(y,   12, 31), y + 1)
    if m in (1, 2, 3):
        return (f"Q2 FY{y}",   date(y,    1, 1), date(y,    3, 31), y)
    if m in (4, 5, 6):
        return (f"Q3 FY{y}",   date(y,    4, 1), date(y,    6, 30), y)
    return     (f"Q4 FY{y}",   date(y,    7, 1), date(y,    9, 30), y)


# ─── Data loading ────────────────────────────────────────────────────────
def load_revenue(csv_path):
    """Load revenue.csv → list of {period, source, amount(float)}. Skips TBD/N/A/blank."""
    out = []
    if not os.path.exists(csv_path):
        return out
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                amt = float(r["amount"])
            except (ValueError, TypeError, KeyError):
                continue
            out.append({"period": r["period"], "source": r["source"], "amount": amt})
    return out


def load_tracker(json_path):
    if not os.path.exists(json_path):
        return {}
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


# ─── Per-show summary ────────────────────────────────────────────────────
def compute_show_summary(show, today=None, script_dir=None):
    today      = today or date.today()
    script_dir = script_dir or os.path.dirname(os.path.abspath(__file__))
    data_dir   = os.path.join(script_dir, show["data_dir"])

    revenue = load_revenue(os.path.join(data_dir, "revenue.csv"))
    tracker = load_tracker(os.path.join(data_dir, "tracker_data.json"))

    # ── Revenue aggregates ──
    cur_month  = today.strftime("%Y-%m")
    by_month   = defaultdict(float)
    for r in revenue:
        by_month[r["period"]] += r["amount"]
    cum_total  = sum(by_month.values())
    mtd_gross  = by_month.get(cur_month, 0.0)

    # ── Fiscal quarter cut ──
    q_label, q_start, q_end, fy = current_fiscal_quarter(today)
    q_start_key = q_start.strftime("%Y-%m")
    cum_before_q = sum(v for m, v in by_month.items() if m < q_start_key)
    cum_thru_now = cum_total                                # mid-quarter live total
    q_revenue    = cum_thru_now - cum_before_q
    rdm_q_cut    = cut_during(cum_before_q, cum_thru_now)

    # ── Threshold context (for the UI) ──
    tier_idx, tier_low, tier_high, tier_rate = current_tier(cum_total)
    to_500k  = max(0.0, 500_000   - cum_total)
    past_500k = max(0.0, cum_total - 500_000)
    to_1m    = max(0.0, 1_000_000 - cum_total)
    past_1m  = max(0.0, cum_total - 1_000_000)
    crossed_500k_month = next(
        (m for m in sorted(by_month) if _cum_through(by_month, m) >= 500_000),
        None,
    )
    crossed_1m_month = next(
        (m for m in sorted(by_month) if _cum_through(by_month, m) >= 1_000_000),
        None,
    )

    # ── Audience / content ──
    subs       = tracker.get("current_subs", 0) or 0
    eps_30d    = _episodes_last_n_days(tracker, today, days=30)
    last_pub   = _latest_episode_month(tracker)

    return {
        "key":             show["key"],
        "name":            show["name"],
        "tag":             show.get("tag", ""),
        "color":           show.get("color", "#475569"),
        "dashboard_url":   show["dashboard_url"],
        "launch":          show["launch"],
        # revenue
        "cum_gross":          cum_total,
        "mtd_gross":          mtd_gross,
        "quarter_label":      q_label,
        "quarter_start":      q_start.strftime("%b %d, %Y"),
        "quarter_end":        q_end.strftime("%b %d, %Y"),
        "quarter_revenue":    q_revenue,
        "cum_before_quarter": cum_before_q,
        "cum_through_now":    cum_thru_now,
        "rdm_cut_quarter":    rdm_q_cut,
        "rdm_cut_lifetime":   split_at(cum_total),
        # threshold context
        "tier_index":         tier_idx,
        "tier_rate":          tier_rate,
        "to_500k":            to_500k,
        "past_500k":          past_500k,
        "to_1m":              to_1m,
        "past_1m":            past_1m,
        "crossed_500k_month": crossed_500k_month,
        "crossed_1m_month":   crossed_1m_month,
        # audience
        "subs":               subs,
        "eps_30d":            eps_30d,
        "last_pub_month":     last_pub,
        # quarter-vs-prior-quarter delta for the UI
        "by_month":           dict(by_month),
    }


def _cum_through(by_month, m):
    return sum(v for k, v in by_month.items() if k <= m)


def _episodes_last_n_days(tracker, today, days=30):
    """Count episodes published in the last `days` days using Megaphone monthly counts."""
    # tracker.audio.episodes is {YYYY-MM: count}. Approximate last-30d by summing
    # the current month + (if today is < day 15) the prior month, weighted.
    # For V1, just take current month + prior month and call it "last 30d" approx.
    eps_map = tracker.get("audio", {}).get("episodes", {}) or {}
    cur = today.strftime("%Y-%m")
    prev_dt = date(today.year, today.month, 1) - __import__("datetime").timedelta(days=1)
    prev = prev_dt.strftime("%Y-%m")
    return int((eps_map.get(cur) or 0) + (eps_map.get(prev) or 0))


def _latest_episode_month(tracker):
    eps_map = tracker.get("audio", {}).get("episodes", {}) or {}
    months = [m for m, v in eps_map.items() if v]
    return max(months) if months else None


# ─── Network rollup ──────────────────────────────────────────────────────
def compute_rdm_summary(show_summaries):
    return {
        "active_shows":         len(show_summaries),
        "network_mtd_gross":    sum(s["mtd_gross"]       for s in show_summaries),
        "network_cum_gross":    sum(s["cum_gross"]       for s in show_summaries),
        "network_eps_30d":      sum(s["eps_30d"]         for s in show_summaries),
        "network_subs":         sum(s["subs"]            for s in show_summaries),
        "network_q_cut":        sum(s["rdm_cut_quarter"] for s in show_summaries),
        "network_lifetime_cut": sum(s["rdm_cut_lifetime"] for s in show_summaries),
    }


# ─── Date formatting (portable, no %-d which crashes on Windows) ────────
_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
def _md(d):  return f"{_MONTH_ABBR[d.month]} {d.day}"
def _mdy(d): return f"{_MONTH_ABBR[d.month]} {d.day}, {d.year}"


# ─── Main ────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Build the RDM master dashboard.")
    ap.add_argument("--output", default="../index.html",
                    help="Output path (default: ../index.html → lands at repo root)")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    today      = date.today()

    print("=" * 60)
    print("RAIN DELAY MEDIA — Master Dashboard Builder")
    print("=" * 60)
    print(f"Generated:    {today.strftime('%B %d, %Y')}")
    print(f"Shows:        {len(SHOWS)}")
    print()

    show_summaries = []
    for show in SHOWS:
        print(f"[{show['name']}]")
        s = compute_show_summary(show, today=today, script_dir=script_dir)
        show_summaries.append(s)
        print(f"  Lifetime gross:   ${s['cum_gross']:>15,.2f}")
        print(f"  {s['quarter_label']:<10} revenue: ${s['quarter_revenue']:>15,.2f}")
        print(f"  RDM Q cut:        ${s['rdm_cut_quarter']:>15,.2f}")
        print(f"  Subs:             {s['subs']:>16,}")
        print()

    rdm = compute_rdm_summary(show_summaries)
    print(f"Network MTD gross:   ${rdm['network_mtd_gross']:,.2f}")
    print(f"Network RDM Q cut:   ${rdm['network_q_cut']:,.2f}")
    print()

    out_path = args.output
    if not os.path.isabs(out_path):
        out_path = os.path.join(script_dir, out_path)

    q_label, q_start, q_end, _ = current_fiscal_quarter(today)
    html = build_master_html(
        rdm_summary    = rdm,
        show_summaries = show_summaries,
        quarter_label  = q_label,
        quarter_window = f"{_md(q_start)} – {_mdy(q_end)}",
        generated_at   = today.strftime("%B %d, %Y"),
    )

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✓ Saved: {out_path}")


if __name__ == "__main__":
    main()