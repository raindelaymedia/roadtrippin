"""
Road Trippin' — Socials Tracker (Native Platform Edition)

Ingests monthly social metrics sourced from each platform's native analytics
tool (Instagram Insights, TikTok Analytics, X Analytics, YouTube Studio,
Facebook Business Suite). Jon owns native access and sends a monthly summary
which we drop into data/ and this script ingests.

Data source priority:
  1. Native summary CSV  →  data/RoadTrippinSocialsMM_YY.csv
       (new format — see NATIVE_FORMAT below)
  2. Legacy Mondo CSV   →  same filename, old column headers
       (still parsed for backward compat, Mondo is deprecated and unreliable)
  3. Interactive prompt for anything missing.

Output (long format) appended to data/socials.csv:
    period,platform,metric,value
    2026-06,INSTAGRAM,FOLLOWERS,125432
    2026-06,INSTAGRAM,FOLLOWER_GAIN,9128
    2026-06,INSTAGRAM,POSTS,86
    2026-06,INSTAGRAM,VIEWS,18789712
    2026-06,INSTAGRAM,TOP_POST_VIEWS,693922
    2026-06,INSTAGRAM,IMPRESSIONS,   (if available)
    2026-06,INSTAGRAM,ENGAGEMENTS,   (if available)

Native monthly summary format (data/RoadTrippinSocialsMM_YY.csv):
    platform,followers,follower_gain,posts,views,top_post_views,impressions,engagements
    INSTAGRAM,125432,9128,86,18789712,693922,,
    TIKTOK,37644,1417,34,2021531,353532,,
    X,25336,449,66,1421383,140251,,
    YOUTUBE,163805,,116,4502031,,,
    FACEBOOK,,,,,,,

Blank values are skipped (not written, not prompted). "N/A" preserved as-is.

Usage:
    python build_socials.py                              # normal monthly run
    python build_socials.py --input data/mysummary.csv   # non-standard filename
    python build_socials.py --interactive                # skip CSV, prompt everything
    python build_socials.py --period 2026-06             # skip period prompt
"""

import argparse
import csv
import os
from datetime import datetime


# Platforms we track. Order determines display order in socials.csv.
PLATFORMS = ["INSTAGRAM", "TIKTOK", "X", "YOUTUBE", "FACEBOOK"]

# Column-header → canonical metric.
# Handles both new native-summary headers and legacy Mondo headers.
NATIVE_COLUMNS = {
    # New native-summary headers
    "followers":       "FOLLOWERS",
    "follower_gain":   "FOLLOWER_GAIN",
    "follower gain":   "FOLLOWER_GAIN",
    "posts":           "POSTS",
    "views":           "VIEWS",
    "top_post_views":  "TOP_POST_VIEWS",
    "top post views":  "TOP_POST_VIEWS",
    "top post":        "TOP_POST_VIEWS",
    "impressions":     "IMPRESSIONS",
    "engagements":     "ENGAGEMENTS",
    # Legacy Mondo headers
    "post count":      "POSTS",
    # Ignore % delta columns from either format
    "impressions %":   None, "views %":       None,
    "engagements %":   None, "post count %":  None,
    "posts %":         None, "followers %":   None,
}

# Platform-name normalization: input string → canonical key
PLATFORM_ALIASES = {
    "instagram":     "INSTAGRAM",  "ig":       "INSTAGRAM",
    "tiktok":        "TIKTOK",     "tt":       "TIKTOK",
    "x":             "X",          "twitter":  "X",          "twitter/x": "X",
    "youtube":       "YOUTUBE",    "yt":       "YOUTUBE",
    "facebook":      "FACEBOOK",   "fb":       "FACEBOOK",   "meta":      "FACEBOOK",
}

# Metrics we prompt for if the summary CSV doesn't provide them.
# Native tools cover all of these; only prompt if Jon's summary skipped one.
PROMPT_METRICS = ["FOLLOWERS", "FOLLOWER_GAIN", "POSTS", "VIEWS", "TOP_POST_VIEWS"]


def parse_value(raw):
    """Convert a raw cell value to a normalized string, or '' if blank."""
    s = str(raw).strip().replace(",", "")
    if not s: return ""
    s_lower = s.lower()
    if s_lower in ("na", "n/a", "-"): return "N/A"
    if s_lower == "tbd": return "TBD"
    try:
        f = float(s.rstrip("%"))
        if s.rstrip().endswith("%"):
            return f"{f/100:.4f}"
        return str(int(f)) if f == int(f) else f"{f:.4f}"
    except ValueError:
        return s


def prompt_period():
    """Ask for period as YYYY-MM. Default to previous full month."""
    now = datetime.now()
    prev_y, prev_m = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    default = f"{prev_y}-{prev_m:02d}"
    raw = input(f"Period YYYY-MM [{default}]: ").strip()
    if not raw: return default
    try:
        y, m = raw.split("-")
        int(y); int(m)
        return f"{int(y):04d}-{int(m):02d}"
    except (ValueError, IndexError):
        print(f"  ✗ Invalid — using default: {default}")
        return default


def native_path_for(data_dir, period):
    """Convention: data/RoadTrippinSocialsMM_YY.csv (matches Jon's historical naming)."""
    year, month = period.split("-")
    yy = year[-2:]
    return os.path.join(data_dir, f"RoadTrippinSocials{month}_{yy}.csv")


def load_native_summary(path):
    """Parse a summary CSV into {platform: {metric: value}}.
    Accepts new headers, legacy Mondo headers, mixed. Blank cells skipped."""
    if not path or not os.path.exists(path):
        return {}
    out = {}
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Build header → metric map
        col_map = {}
        for h in headers:
            key = h.strip().lower()
            if key in NATIVE_COLUMNS and NATIVE_COLUMNS[key]:
                col_map[h] = NATIVE_COLUMNS[key]

        # Find the platform column
        plat_col = None
        for h in headers:
            if h.strip().lower() in ("platform", "channel"):
                plat_col = h; break
        if plat_col is None and headers:
            plat_col = headers[0]

        for row in reader:
            plat_raw = str(row.get(plat_col, "")).strip().lower()
            plat = PLATFORM_ALIASES.get(plat_raw) or plat_raw.upper()
            if plat not in PLATFORMS:
                continue  # skip TOTAL, AVG rows etc.
            out[plat] = {}
            for header, metric in col_map.items():
                val = parse_value(row.get(header, ""))
                if val:
                    out[plat][metric] = val
    return out


def load_existing(csv_path):
    """Load existing socials.csv into {(period, platform, metric): value}."""
    if not os.path.exists(csv_path): return {}
    rows = {}
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        expected = {"period", "platform", "metric", "value"}
        actual = set(reader.fieldnames or [])
        if not expected.issubset(actual):
            print(f"⚠ socials.csv has unexpected columns: {actual}")
            return {}
        for r in reader:
            try:
                rows[(r["period"], r["platform"], r["metric"])] = r["value"]
            except KeyError:
                continue
    return rows


def write_csv(csv_path, data):
    """Write {(period, platform, metric): value} → sorted long-form CSV."""
    metric_order = ["FOLLOWERS","FOLLOWER_GAIN","POSTS","VIEWS","IMPRESSIONS",
                    "ENGAGEMENTS","TOP_POST_VIEWS","ENGAGEMENT_RATE","AVG_VIEW_DURATION"]
    def sort_key(item):
        (p, plat, met), _ = item
        return (-int(p.replace("-","")),
                PLATFORMS.index(plat) if plat in PLATFORMS else 99,
                metric_order.index(met) if met in metric_order else 99)
    rows = sorted(data.items(), key=sort_key)
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["period", "platform", "metric", "value"])
        for (period, platform, metric), value in rows:
            w.writerow([period, platform, metric, value])


def get_prev_month(period):
    y, m = map(int, period.split("-"))
    if m == 1: return f"{y-1}-12"
    return f"{y}-{m-1:02d}"


def calc_follower_gain(period, platform, current_followers, existing):
    """Fallback: compute follower gain from previous month if not supplied."""
    prev = get_prev_month(period)
    prev_val = existing.get((prev, platform, "FOLLOWERS"))
    try:
        cur = float(current_followers)
        pv = float(prev_val) if prev_val else None
        if pv is not None: return f"{cur - pv:.0f}"
    except (ValueError, TypeError): pass
    return None


def calc_engagement_rate(views_or_impressions, engagements):
    """Compute engagement rate from views (preferred) or impressions."""
    try:
        base = float(views_or_impressions); e = float(engagements)
        if base > 0: return f"{e/base:.4f}"
    except (ValueError, TypeError): pass
    return None


def show_platforms_status(period, existing, summary_data):
    """Show what's covered per platform before prompting."""
    print(f"\nStatus for {period}:")
    print(f"  {'Platform':<12}{'From summary':<18}{'In socials.csv':<20}")
    for p in PLATFORMS:
        from_sum = f"✓ {len(summary_data[p])} metrics" if p in summary_data else "—"
        n_existing = sum(1 for (per, plat, _) in existing if per == period and plat == p)
        exist_str = f"{n_existing} metrics" if n_existing else "—"
        print(f"  {p:<12}{from_sum:<18}{exist_str:<20}")


def main():
    parser = argparse.ArgumentParser(description="Road Trippin' Socials Tracker (Native Platform Edition)")
    parser.add_argument("--input", default=None,
                        help="Path to native-summary CSV (default: data/RoadTrippinSocialsMM_YY.csv)")
    parser.add_argument("--csv", default=None, help="Path to socials.csv")
    parser.add_argument("--interactive", action="store_true",
                        help="Skip CSV parsing; prompt for every metric")
    parser.add_argument("--period", default=None,
                        help="Skip period prompt (format: YYYY-MM)")
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(script_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    csv_path = args.csv or os.path.join(data_dir, "socials.csv")

    print("=" * 60)
    print("ROAD TRIPPIN' — SOCIALS TRACKER (Native Platform Edition)")
    print("=" * 60)
    print(f"Output: {csv_path}")
    print("Data source: platform-native analytics via Jon")
    print("(Mondo is deprecated — retained for backward compat only)\n")

    existing = load_existing(csv_path)
    if existing:
        periods = sorted(set(p for (p, _, _) in existing.keys()), reverse=True)
        print(f"Existing: {len(existing)} rows across {len(periods)} months  ·  latest: {periods[0]}\n")

    period = args.period or prompt_period()

    # Try to load summary CSV
    summary_data = {}
    if not args.interactive:
        summary_path = args.input or native_path_for(data_dir, period)
        print(f"\nLooking for summary CSV: {summary_path}")
        if os.path.exists(summary_path):
            print(f"  ✓ Found")
            summary_data = load_native_summary(summary_path)
            if summary_data:
                print(f"  ✓ Parsed {len(summary_data)} platforms: {', '.join(summary_data.keys())}")
            else:
                print(f"  ⚠ No usable rows — falling back to prompts")
        else:
            year, month = period.split("-")
            yy = year[-2:]
            print(f"  Not found — falling back to interactive prompts")
            print(f"  (Expected file: RoadTrippinSocials{month}_{yy}.csv with columns:")
            print(f"   platform, followers, follower_gain, posts, views, top_post_views, impressions, engagements)")

    show_platforms_status(period, existing, summary_data)
    print(f"\nEntering socials for {period}\n")

    new_data = {}
    detected = list(summary_data.keys()) if summary_data else []
    if not detected:
        ans = input("Which platforms? (comma-separated) [INSTAGRAM,TIKTOK,X,YOUTUBE]: ").strip()
        if not ans: ans = "INSTAGRAM,TIKTOK,X,YOUTUBE"
        detected = [PLATFORM_ALIASES.get(p.strip().lower(), p.strip().upper()) for p in ans.split(",")]

    for platform in detected:
        print(f"\n─── {platform} ───")
        plat_summary = summary_data.get(platform, {})
        if plat_summary:
            print(f"  From native summary:")
            for metric, val in plat_summary.items():
                print(f"    {metric:<18} {val}")
                new_data[(period, platform, metric)] = val

        # Prompt for missing standard metrics
        missing = [m for m in PROMPT_METRICS if m not in plat_summary]
        if missing:
            print(f"  Missing (blank = skip):")
            for metric in missing:
                existing_val = existing.get((period, platform, metric), "")
                prompt_str = f"    {metric:<18} "
                if existing_val:
                    prompt_str = f"    {metric:<18} [{existing_val}] "
                raw = input(prompt_str)
                if not raw.strip() and existing_val:
                    new_data[(period, platform, metric)] = existing_val
                else:
                    val = parse_value(raw)
                    if val:
                        new_data[(period, platform, metric)] = val

        # Auto-fill follower gain from prev month if we have FOLLOWERS but no gain
        if (period, platform, "FOLLOWERS") in new_data and (period, platform, "FOLLOWER_GAIN") not in new_data:
            gain = calc_follower_gain(period, platform, new_data[(period, platform, "FOLLOWERS")], existing)
            if gain is not None:
                new_data[(period, platform, "FOLLOWER_GAIN")] = gain
                print(f"    {'FOLLOWER_GAIN':<18} {gain} (auto vs prev month)")

        # Auto-compute engagement rate if we have both views and engagements
        views = new_data.get((period, platform, "VIEWS"))
        eng   = new_data.get((period, platform, "ENGAGEMENTS"))
        if views and eng:
            er = calc_engagement_rate(views, eng)
            if er:
                new_data[(period, platform, "ENGAGEMENT_RATE")] = er
                print(f"    {'ENGAGEMENT_RATE':<18} {float(er)*100:.2f}% (auto: engagements / views)")

    # Merge and preview
    merged = dict(existing)
    for k, v in new_data.items():
        merged[k] = v

    print(f"\nSummary for {period}:")
    print(f"  New/updated rows: {len(new_data)}")
    print(f"  Total in socials.csv after save: {len(merged)}")

    # Missing values report
    EXPECTED = ["FOLLOWERS", "FOLLOWER_GAIN", "POSTS", "VIEWS", "TOP_POST_VIEWS"]
    missing_by_platform = {}
    for plat in detected:
        gaps = [m for m in EXPECTED
                if (period, plat, m) not in new_data
                and (period, plat, m) not in existing]
        if gaps: missing_by_platform[plat] = gaps
    if missing_by_platform:
        print(f"\n⚠ Missing values worth chasing:")
        for plat, gaps in missing_by_platform.items():
            print(f"  {plat}:")
            for m in gaps:
                hint = {
                    "FOLLOWERS":      "(Jon or native platform Followers view)",
                    "FOLLOWER_GAIN":  "(Jon; or auto-computes from prev month FOLLOWERS)",
                    "POSTS":          "(Jon; count of posts published in period)",
                    "VIEWS":          "(Jon; total views on posts in period)",
                    "TOP_POST_VIEWS": "(Jon; best-performing post views)",
                }.get(m, "")
                print(f"    • {m:<18} {hint}")

    ans = input(f"\nWrite to {csv_path}? [Y/n]: ").strip().lower()
    if ans in ("", "y", "yes"):
        write_csv(csv_path, merged)
        print(f"✓ Saved {len(merged)} rows to {csv_path}")
    else:
        print("Aborted (no changes written).")


if __name__ == "__main__":
    main()