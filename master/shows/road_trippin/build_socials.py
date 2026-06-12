"""
Road Trippin' — Socials Tracker
Interactive script that pulls data from Mondo Metrics CSV exports
and prompts for any missing fields, appending to data/socials.csv.

Mondo CSV format expected:
    Platform,Impressions,% Δ,Views,% Δ,Engagements,% Δ,Post Count,% Δ
    Instagram,6317325,...,5472215,...,361866,...,81,...

Output (long format) appended to data/socials.csv:
    period,platform,metric,value
    2026-04,INSTAGRAM,IMPRESSIONS,6317325
    2026-04,INSTAGRAM,VIEWS,5472215323526
    2026-04,INSTAGRAM,ENGAGEMENTS,361866
    2026-04,INSTAGRAM,POSTS,81
    2026-04,INSTAGRAM,FOLLOWERS,112471      (manual prompt)
    2026-04,INSTAGRAM,TOP_POST_VIEWS,586346  (manual prompt)
    ...

Usage:
    python build_socials.py
    python build_socials.py --mondo data/mondo_2026-04.csv
"""

import argparse
import csv
import os
from datetime import datetime


PLATFORMS = ["INSTAGRAM", "TIKTOK", "X", "YOUTUBE", "FACEBOOK"]

# Map Mondo's platform names to canonical keys
MONDO_PLATFORM_MAP = {
    "instagram": "INSTAGRAM", "tiktok": "TIKTOK", "x": "X", "twitter": "X",
    "twitter/x": "X", "youtube": "YOUTUBE", "facebook": "FACEBOOK",
}

# Mondo CSV columns we extract (case-insensitive header match)
MONDO_METRICS = {
    "impressions": "IMPRESSIONS",
    "views": "VIEWS",
    "engagements": "ENGAGEMENTS",
    "post count": "POSTS",
}

# Metrics that need manual entry (not in Mondo's basic export)
MANUAL_METRICS = ["FOLLOWERS", "TOP_POST_VIEWS"]

MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN",
          "JUL","AUG","SEP","OCT","NOV","DEC"]


def parse_value(raw):
    s = raw.strip()
    if not s: return ""
    s_lower = s.lower()
    if s_lower in ("na", "n/a"): return "N/A"
    if s_lower == "tbd": return "TBD"
    try:
        f = float(s.replace(",", "").replace("$", "").rstrip("%"))
        if s.rstrip().endswith("%"):
            return f"{f/100:.4f}"
        return f"{f:.0f}" if f == int(f) else f"{f:.4f}"
    except ValueError:
        return s


def prompt_period():
    today = datetime.now()
    default_month = today.strftime("%b").upper()
    default_year = today.year
    month_in = input(f"Month [{default_month}]: ").strip().upper() or default_month
    year_in = input(f"Year [{default_year}]: ").strip()
    year = int(year_in) if year_in else default_year
    if month_in not in MONTHS:
        match = next((m for m in MONTHS if m.startswith(month_in[:3])), None)
        if not match:
            raise ValueError(f"Unknown month: {month_in}")
        month_in = match
    month_num = MONTHS.index(month_in) + 1
    return f"{year}-{month_num:02d}"


def mondo_path_for(data_dir, period):
    """Build the expected Mondo filename for a given period (YYYY-MM).
    Format: RoadTrippinSocialsMM_YY.csv (e.g. RoadTrippinSocials04_26.csv)"""
    year, month = period.split("-")
    yy = year[-2:]
    return os.path.join(data_dir, f"RoadTrippinSocials{month}_{yy}.csv")


def load_mondo(path):
    """Parse a Mondo CSV into {platform: {metric: value}}."""
    if not path or not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Build a metric → column-name map (case-insensitive)
        # Mondo headers like "Impressions", "Views", "Engagements", "Post Count"
        col_map = {}
        for header in reader.fieldnames or []:
            key = header.strip().lower()
            if key in MONDO_METRICS:
                col_map[MONDO_METRICS[key]] = header

        for row in reader:
            plat_raw = row.get("Platform", "").strip().lower()
            plat = MONDO_PLATFORM_MAP.get(plat_raw)
            if not plat:
                continue
            out[plat] = {}
            for metric_key, header in col_map.items():
                val = parse_value(row.get(header, ""))
                if val:
                    out[plat][metric_key] = val
    return out


def load_existing(csv_path):
    """Load existing socials.csv into {(period, platform, metric): value}."""
    if not os.path.exists(csv_path): return {}
    rows = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Validate header
        expected = {"period", "platform", "metric", "value"}
        actual = set(reader.fieldnames or [])
        if not expected.issubset(actual):
            print(f"⚠ socials.csv has unexpected columns: {actual}")
            print(f"  Expected: {expected}")
            print(f"  → Skipping existing data load. Will write fresh on save.")
            return {}
        for r in reader:
            try:
                rows[(r["period"], r["platform"], r["metric"])] = r["value"]
            except KeyError:
                continue
    return rows


def write_csv(csv_path, data):
    metric_order = ["FOLLOWERS","FOLLOWER_GAIN","POSTS","VIEWS","IMPRESSIONS","ENGAGEMENTS","TOP_POST_VIEWS","ENGAGEMENT_RATE","AVG_VIEW_DURATION"]
    def sort_key(item):
        (p, plat, met), _ = item
        return (-int(p.replace("-","")),
                PLATFORMS.index(plat) if plat in PLATFORMS else 99,
                metric_order.index(met) if met in metric_order else 99)
    rows = sorted(data.items(), key=sort_key)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["period", "platform", "metric", "value"])
        for (p, plat, met), val in rows:
            w.writerow([p, plat, met, val])


def get_prev_month(period):
    y, m = map(int, period.split("-"))
    if m == 1: return f"{y-1}-12"
    return f"{y}-{m-1:02d}"


def calc_engagement_rate(impressions, engagements):
    try:
        i = float(impressions); e = float(engagements)
        if i > 0: return f"{e/i:.4f}"
    except (ValueError, TypeError): pass
    return None


def calc_follower_gain(period, platform, current_followers, existing):
    prev = get_prev_month(period)
    prev_val = existing.get((prev, platform, "FOLLOWERS"))
    try:
        cur = float(current_followers); pv = float(prev_val) if prev_val else None
        if pv is not None: return f"{cur - pv:.0f}"
    except (ValueError, TypeError): pass
    return None


def main():
    parser = argparse.ArgumentParser(description="Road Trippin' Socials Tracker")
    parser.add_argument("--mondo", default=None, help="Path to Mondo CSV export")
    parser.add_argument("--csv", default=None, help="Path to socials.csv")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    csv_path = args.csv or os.path.join(data_dir, "socials.csv")

    print("=" * 55)
    print("ROAD TRIPPIN' — SOCIALS TRACKER")
    print("=" * 55)
    print(f"Output: {csv_path}\n")

    existing = load_existing(csv_path)
    if existing:
        periods = sorted(set(p for (p, _, _) in existing.keys()), reverse=True)
        print(f"Existing data: {len(existing)} rows across {len(periods)} months")
        print(f"Most recent: {periods[0]}\n")

    period = prompt_period()

    # Resolve Mondo CSV path: explicit --mondo wins, else convention RoadTrippinSocials_YYYY-MM.csv
    mondo_path = args.mondo or mondo_path_for(data_dir, period)
    print(f"\nLooking for Mondo CSV: {mondo_path}")
    if not os.path.exists(mondo_path):
        print(f"  Not found — falling back to all-manual entry")
        year, month = period.split("-")
        yy = year[-2:]
        print(f"  (To use Mondo data, name file: RoadTrippinSocials{month}_{yy}.csv)")
        mondo_path = None
    else:
        print(f"  ✓ Found")

    print(f"\nEntering socials for {period}\n")

    # Load Mondo for this period
    mondo_data = load_mondo(mondo_path) if mondo_path else {}
    if mondo_data:
        print(f"✓ Mondo data found for: {', '.join(mondo_data.keys())}\n")

    new_data = {}  # (period, platform, metric) -> value

    # For each platform, pull from Mondo + prompt for gaps
    detected_platforms = list(mondo_data.keys()) if mondo_data else []
    if not detected_platforms:
        # Fallback: prompt user which platforms to enter
        print("No Mondo data — which platforms do you want to enter?")
        ans = input("Platforms (comma-separated, e.g. INSTAGRAM,TIKTOK,X) [INSTAGRAM,TIKTOK,X]: ").strip()
        if not ans: ans = "INSTAGRAM,TIKTOK,X"
        detected_platforms = [p.strip().upper() for p in ans.split(",")]

    for platform in detected_platforms:
        print(f"\n─── {platform} ───")
        plat_mondo = mondo_data.get(platform, {})

        # Show what came from Mondo
        if plat_mondo:
            print("  From Mondo:")
            for metric, val in plat_mondo.items():
                print(f"    {metric:<18} {val}")
                new_data[(period, platform, metric)] = val

        # Prompt for the missing fields
        print("  Manual entry (blank = skip):")
        for metric in MANUAL_METRICS:
            existing_val = existing.get((period, platform, metric), "")
            prompt = f"    {metric:<18} "
            if existing_val:
                prompt = f"    {metric:<18} [{existing_val}] "
            raw = input(prompt)
            if not raw.strip() and existing_val:
                new_data[(period, platform, metric)] = existing_val
            else:
                val = parse_value(raw)
                if val:
                    new_data[(period, platform, metric)] = val

        # Auto-calculate engagement rate
        imp = new_data.get((period, platform, "IMPRESSIONS"))
        eng = new_data.get((period, platform, "ENGAGEMENTS"))
        if imp and eng:
            er = calc_engagement_rate(imp, eng)
            if er:
                new_data[(period, platform, "ENGAGEMENT_RATE")] = er
                print(f"    {'ENGAGEMENT_RATE':<18} {float(er)*100:.2f}% (auto-calculated)")

        # Auto-calculate follower gain
        followers = new_data.get((period, platform, "FOLLOWERS"))
        if followers:
            gain = calc_follower_gain(period, platform, followers, existing)
            if gain is not None:
                new_data[(period, platform, "FOLLOWER_GAIN")] = gain
                print(f"    {'FOLLOWER_GAIN':<18} {gain} (auto vs prev month)")

    # Preview
    print(f"\n─── Preview for {period} ───")
    by_platform = {}
    for (p, plat, met), val in new_data.items():
        by_platform.setdefault(plat, {})[met] = val
    for plat in detected_platforms:
        print(f"  {plat}:")
        for met, val in sorted(by_platform.get(plat, {}).items()):
            print(f"    {met:<18} {val}")

    # Missing values report — what's NOT populated for each platform
    EXPECTED_METRICS = ["IMPRESSIONS", "VIEWS", "ENGAGEMENTS", "POSTS",
                        "FOLLOWERS", "TOP_POST_VIEWS",
                        "ENGAGEMENT_RATE", "FOLLOWER_GAIN"]
    missing_by_platform = {}
    for plat in detected_platforms:
        plat_data = by_platform.get(plat, {})
        gaps = [m for m in EXPECTED_METRICS if m not in plat_data]
        if gaps:
            missing_by_platform[plat] = gaps

    if missing_by_platform:
        print(f"\n⚠ MISSING VALUES — go hunt these down:")
        for plat, gaps in missing_by_platform.items():
            print(f"  {plat}:")
            for m in gaps:
                # Hint where to find each one
                if m in ("IMPRESSIONS", "VIEWS", "ENGAGEMENTS", "POSTS"):
                    hint = "(should come from Mondo CSV)"
                elif m == "FOLLOWERS":
                    hint = "(Mondo dashboard → Account → Followers)"
                elif m == "TOP_POST_VIEWS":
                    hint = "(Mondo dashboard → Top performing posts)"
                elif m == "ENGAGEMENT_RATE":
                    hint = "(auto-calc requires both IMPRESSIONS and ENGAGEMENTS)"
                elif m == "FOLLOWER_GAIN":
                    hint = "(auto-calc requires FOLLOWERS + previous month data)"
                else:
                    hint = ""
                print(f"    • {m:<18} {hint}")
    else:
        print(f"\n✓ All expected metrics populated.")

    confirm = input("\nSave? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        print("Cancelled.")
        return

    # Merge: replace any existing rows for this period+platform
    for (p, plat, met) in list(existing.keys()):
        if p == period and plat in detected_platforms:
            del existing[(p, plat, met)]
    existing.update(new_data)

    write_csv(csv_path, existing)
    print(f"\n✓ Saved {len(new_data)} rows for {period}")
    print(f"  CSV: {csv_path}")
    print("=" * 55)


if __name__ == "__main__":
    main()