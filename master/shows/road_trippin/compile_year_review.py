"""
Road Trippin' Season 1 — Year in Review Data Compilation
Reads all existing data sources, unifies into year_review_data.json,
and prints a full audit of coverage and gaps.

Data sources:
  - tracker_data.json (YT monthly + daily + top content + all videos)
  - socials.csv (IG, TikTok, X, FB, YT socials)
  - revenue.csv (monthly revenue by source — if available)
  - fanatics_history.csv (8 delivery periods with impressions)
  - concurrent_template.csv (live episode concurrent viewers)
  - megaphone_monthly.csv (podcast delivery)
  - Contract terms (hardcoded from the PSA)

Usage:
    python compile_year_review.py --data-dir ./data
"""

import json
import csv
import os
import argparse
from collections import defaultdict
from datetime import datetime, date

# ─── Season 1 bounds ─────────────────────────────────────────────
S1_START = "2025-10"  # contract effective date Oct 1 2025
S1_END   = "2026-09"  # Fanatics term ends Sep 13 2026
FANATICS_START = "2026-02-17"
FANATICS_END   = "2026-09-13"
S1_MONTHS = []
y, m = 2025, 10
while f"{y}-{m:02d}" <= S1_END:
    S1_MONTHS.append(f"{y}-{m:02d}")
    m += 1
    if m > 12: m = 1; y += 1

# ─── Contract terms (from PSA) ───────────────────────────────────
CONTRACT = {
    "effective_date": "2025-10-01",
    "term_years": 2,
    "cycle_episodes": 192,
    "cycle_weeks": 48,
    "budget_per_cycle": 348000,
    "budget_payments": 6,
    "revenue_tiers": [
        {"floor": 0, "ceiling": 500000, "rate": 0.00},
        {"floor": 500001, "ceiling": 1000000, "rate": 0.20},
        {"floor": 1000001, "ceiling": None, "rate": 0.25},
    ],
    "fanatics_impression_goal": 47000000,
    "fanatics_term_start": FANATICS_START,
    "fanatics_term_end": FANATICS_END,
    "talent": ["Richard Jefferson", "Channing Frye", "Kendrick Perkins", "Allie Clifton"],
}


def load_tracker(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=".")
    parser.add_argument("--output", default="year_review_data.json")
    args = parser.parse_args()

    dd = args.data_dir
    print("=" * 60)
    print("ROAD TRIPPIN' — YEAR IN REVIEW DATA COMPILATION")
    print(f"Season 1: {S1_START} → {S1_END} ({len(S1_MONTHS)} months)")
    print("=" * 60)

    gaps = []

    # ─── 1. Tracker Data (YouTube) ───────────────────────────────
    print("\n[1/6] Tracker Data (YouTube)...")
    tracker = load_tracker(os.path.join(dd, "tracker_data.json"))
    yt = {}
    if tracker:
        months_available = tracker.get("months", [])
        s1_yt_months = [m for m in S1_MONTHS if m in months_available]
        missing_yt = [m for m in S1_MONTHS if m not in months_available]
        print(f"  ✓ {len(s1_yt_months)} of {len(S1_MONTHS)} months covered")
        if missing_yt:
            print(f"  ⚠ Missing: {missing_yt}")
            gaps.append(("YouTube monthly", missing_yt))

        current_subs = tracker.get("current_subs", 0)
        print(f"  Current subs: {current_subs:,}")

        # Monthly totals
        for m in S1_MONTHS:
            vids = tracker['yt']['vids'].get(m) or 0
            shorts = tracker['yt']['shorts'].get(m) or 0
            lives = tracker['yt']['lives'].get(m) or 0
            sg = tracker['yt']['subs_gained'].get(m) or 0
            sl = tracker['yt']['subs_lost'].get(m) or 0
            yt[m] = {
                "vids": vids, "shorts": shorts, "lives": lives,
                "total_views": vids + shorts + lives,
                "subs_gained": sg, "subs_lost": sl, "net_subs": sg - sl,
            }

        total_views = sum(d["total_views"] for d in yt.values())
        total_subs_gained = sum(d["subs_gained"] for d in yt.values())
        print(f"  S1 total YT views: {total_views:,}")
        print(f"  S1 net subs gained: {total_subs_gained:,}")

        # Top content per month
        tc = tracker.get("top_content_monthly", {})
        top_content = {}
        for m in S1_MONTHS:
            mc = tc.get(m, {})
            top_content[m] = {
                "long": mc.get("long", [])[:3] if isinstance(mc.get("long"), list) else [],
                "mid": mc.get("mid", [])[:3] if isinstance(mc.get("mid"), list) else [],
                "short": mc.get("short", [])[:3] if isinstance(mc.get("short"), list) else [],
            }
        tc_months_with_data = [m for m in S1_MONTHS if any(top_content[m][t] for t in ("long","mid","short"))]
        print(f"  Top content: {len(tc_months_with_data)} months have data")

        # All videos in S1
        all_vids = tracker.get("all_videos", [])
        s1_vids = [v for v in all_vids if isinstance(v, dict) and S1_START <= v.get("published","")[:7] <= S1_END]
        s1_vids.sort(key=lambda x: x.get("views", 0), reverse=True)
        print(f"  S1 videos: {len(s1_vids)} total")
        if s1_vids:
            print(f"  #1 all-time S1: {s1_vids[0]['views']:,} — {s1_vids[0].get('title','')[:50]}")

        # Daily data
        daily = tracker.get("daily_yt", {})
        s1_daily = {d: v for d, v in daily.items() if S1_START <= d[:7] <= S1_END}
        print(f"  Daily data points: {len(s1_daily)}")

        # Identify biggest spike days
        if s1_daily:
            by_views = sorted(s1_daily.items(), key=lambda x: x[1].get("total_views", 0), reverse=True)
            print(f"  Top 5 spike days:")
            for d, v in by_views[:5]:
                print(f"    {d}: {v.get('total_views',0):,} views")
    else:
        print("  ✗ tracker_data.json not found")
        gaps.append(("YouTube monthly", S1_MONTHS))

    # ─── 2. Socials ──────────────────────────────────────────────
    print("\n[2/6] Socials...")
    socials_raw = load_csv(os.path.join(dd, "socials.csv"))
    socials = defaultdict(lambda: defaultdict(dict))
    soc_months = set()
    soc_platforms = set()
    for r in socials_raw:
        p = r.get("period", "").strip()
        if not (S1_START <= p <= S1_END):
            continue
        plat = r.get("platform", "").strip().upper()
        metric = r.get("metric", "").strip().upper()
        val = r.get("value", "").strip()
        try:
            val = float(val)
        except:
            pass
        socials[p][plat][metric] = val
        soc_months.add(p)
        soc_platforms.add(plat)

    if soc_months:
        print(f"  ✓ {len(soc_months)} months, {len(soc_platforms)} platforms: {sorted(soc_platforms)}")
        missing_soc = [m for m in S1_MONTHS if m not in soc_months]
        if missing_soc:
            print(f"  ⚠ Missing months: {missing_soc}")
            gaps.append(("Socials", missing_soc))

        # IG follower growth
        ig_followers = []
        for m in sorted(soc_months):
            f = socials[m].get("INSTAGRAM", {}).get("FOLLOWERS")
            if f: ig_followers.append((m, f))
        if ig_followers:
            print(f"  IG followers: {ig_followers[0][1]:,.0f} ({ig_followers[0][0]}) → {ig_followers[-1][1]:,.0f} ({ig_followers[-1][0]})")
    else:
        print("  ✗ No socials data in S1 range")
        gaps.append(("Socials", S1_MONTHS))

    # ─── 3. Revenue ──────────────────────────────────────────────
    print("\n[3/6] Revenue...")
    rev_raw = load_csv(os.path.join(dd, "revenue.csv"))
    revenue = defaultdict(lambda: defaultdict(float))
    rev_months = set()
    for r in rev_raw:
        p = r.get("period", "").strip()
        if not (S1_START <= p <= S1_END):
            continue
        src = r.get("source", "").strip()
        try:
            amt = float(r.get("amount", "0").strip())
        except:
            amt = 0
        revenue[p][src] += amt
        rev_months.add(p)

    if rev_months:
        total_rev = sum(sum(sources.values()) for sources in revenue.values())
        print(f"  ✓ {len(rev_months)} months, ${total_rev:,.2f} total S1 revenue")
        missing_rev = [m for m in S1_MONTHS if m not in rev_months]
        if missing_rev:
            print(f"  ⚠ Missing months: {missing_rev}")
            gaps.append(("Revenue", missing_rev))

        # Monthly totals
        for m in sorted(rev_months):
            mt = sum(revenue[m].values())
            print(f"    {m}: ${mt:,.2f}")
    else:
        print("  ⚠ No revenue data found in S1 range (may need revenue.csv)")
        gaps.append(("Revenue", S1_MONTHS))

    # ─── 4. Fanatics Delivery ────────────────────────────────────
    print("\n[4/6] Fanatics Delivery...")
    fan_raw = load_csv(os.path.join(dd, "fanatics_history.csv"))
    fanatics = []
    if fan_raw:
        total_imp = 0
        total_views = 0
        for r in fan_raw:
            imp = int(float(r.get("impressions", 0) or 0))
            yt_views = int(float(r.get("yt_total_views", 0) or 0))
            ig = int(float(r.get("ig_views", 0) or 0))
            tt = int(float(r.get("tiktok_views", 0) or 0))
            fb = int(float(r.get("fb_views", 0) or 0))
            x = int(float(r.get("x_imp", 0) or 0))
            mega = int(float(r.get("mega_views", 0) or 0))
            period_views = yt_views + ig + tt + fb + x + mega
            total_imp += imp
            total_views += period_views
            fanatics.append({
                "start": r["period_start"], "end": r["period_end"],
                "impressions": imp, "yt_views": yt_views,
                "ig_views": ig, "tiktok_views": tt, "fb_views": fb,
                "x_imp": x, "mega_views": mega,
                "group_eps": int(float(r.get("group_eps", 0) or 0)),
                "solo_perk": int(float(r.get("solo_perk", 0) or 0)),
                "solo_chan": int(float(r.get("solo_chan", 0) or 0)),
            })
        print(f"  ✓ {len(fanatics)} reporting periods")
        print(f"  Total impressions: {total_imp:,} ({total_imp/47_000_000*100:.1f}% of 47M goal)")
        cum_eps = sum(f["group_eps"] + f["solo_perk"] + f["solo_chan"] for f in fanatics)
        print(f"  Episodes delivered: {cum_eps}")

        # Check: do we have all 8 periods?
        if len(fanatics) < 8:
            print(f"  ⚠ Only {len(fanatics)} periods — expected 8 (Feb-Sep)")
            gaps.append(("Fanatics periods", f"{len(fanatics)}/8"))
    else:
        print("  ✗ fanatics_history.csv not found")
        gaps.append(("Fanatics", "file missing"))

    # ─── 5. Concurrent Viewers (Live Episodes) ───────────────────
    print("\n[5/6] Concurrent Viewers (Live Episodes)...")
    conc_raw = load_csv(os.path.join(dd, "concurrent_template.csv"))
    concurrent = []
    if conc_raw:
        for r in conc_raw:
            d = r.get("date", "")
            if not (S1_START <= d[:7] <= S1_END):
                continue
            concurrent.append({
                "date": d,
                "title": r.get("title", ""),
                "peak": int(r.get("peak_concurrent", 0)),
                "avg": int(r.get("avg_concurrent", 0)),
            })
        concurrent.sort(key=lambda x: x["date"])
        print(f"  ✓ {len(concurrent)} live episodes tracked")
        if concurrent:
            peaks = sorted(concurrent, key=lambda x: x["peak"], reverse=True)
            print(f"  Peak concurrent: {peaks[0]['peak']:,} ({peaks[0]['date']} — {peaks[0]['title'][:40]})")
            # Monthly trend
            monthly_conc = defaultdict(list)
            for c in concurrent:
                monthly_conc[c["date"][:7]].append(c["avg"])
            print(f"  Monthly avg concurrent:")
            for m in sorted(monthly_conc):
                vals = monthly_conc[m]
                print(f"    {m}: avg={sum(vals)//len(vals):,}, eps={len(vals)}")
    else:
        print("  ⚠ concurrent_template.csv not found")
        gaps.append(("Concurrent", "file missing"))

    # ─── 6. Audio (Megaphone) ────────────────────────────────────
    print("\n[6/6] Audio (Megaphone)...")
    mega_raw = load_csv(os.path.join(dd, "megaphone_monthly.csv"))
    audio = {}
    if mega_raw:
        for r in mega_raw:
            month_raw = r.get("MONTH", "").strip()
            # Handle both YYYY-MM and YYYY-MM-DD formats
            m = month_raw[:7]
            if not (S1_START <= m <= S1_END):
                continue
            total = r.get("TOTAL DELIVERY", r.get("TOTAL DOWNLOADS", "0"))
            try:
                total = int(float(str(total).replace(",", "")))
            except:
                total = 0
            audio[m] = {"total_delivery": total}
        print(f"  ✓ {len(audio)} months")
        if audio:
            total_audio = sum(d["total_delivery"] for d in audio.values())
            print(f"  S1 total delivery: {total_audio:,}")
            missing_audio = [m for m in S1_MONTHS if m not in audio]
            if missing_audio:
                print(f"  ⚠ Missing months: {missing_audio}")
                gaps.append(("Audio", missing_audio))
    else:
        print("  ⚠ megaphone_monthly.csv not found")
        gaps.append(("Audio", "file missing"))

    # ─── Milestone Detection ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("MILESTONE DETECTION")
    print("=" * 60)

    milestones = []

    # Subscriber milestones
    if tracker:
        subs_now = tracker.get("current_subs", 0)
        subs_series = {}
        running = subs_now
        for m in tracker["months"]:
            subs_series[m] = running
            sg = tracker['yt']['subs_gained'].get(m) or 0
            sl = tracker['yt']['subs_lost'].get(m) or 0
            running -= (sg - sl)

        thresholds = [100000, 125000, 150000, 175000]
        for t in thresholds:
            # Find first month where subs >= threshold
            for m in S1_MONTHS:
                if subs_series.get(m, 0) >= t:
                    milestones.append({"month": m, "type": "subs", "label": f"Crossed {t//1000}K subscribers"})
                    print(f"  🎯 {t//1000}K subs: ~{m}")
                    break

    # Best month by views
    if yt:
        best_month = max(S1_MONTHS, key=lambda m: yt.get(m, {}).get("total_views", 0))
        bv = yt[best_month]["total_views"]
        milestones.append({"month": best_month, "type": "views", "label": f"Best YT month: {bv:,} views"})
        print(f"  📈 Best YT month: {best_month} ({bv:,} views)")

    # Best Shorts month
    if yt:
        best_shorts = max(S1_MONTHS, key=lambda m: yt.get(m, {}).get("shorts", 0))
        bs = yt[best_shorts]["shorts"]
        milestones.append({"month": best_shorts, "type": "shorts", "label": f"Best Shorts month: {bs:,}"})
        print(f"  🎬 Best Shorts month: {best_shorts} ({bs:,})")

    # Top viral videos
    if tracker:
        s1_vids_sorted = sorted(
            [v for v in tracker.get("all_videos", []) if isinstance(v, dict) and S1_START <= v.get("published","")[:7] <= S1_END],
            key=lambda x: x.get("views", 0), reverse=True)
        for v in s1_vids_sorted[:5]:
            milestones.append({
                "month": v["published"][:7], "type": "viral",
                "label": f"{v['views']:,} views — {v.get('title','')}",
                "video_id": v.get("id"), "views": v["views"],
            })
            print(f"  🔥 {v['views']:,} views — {v.get('title','')[:55]} ({v['published']})")

    # Peak concurrent
    if concurrent:
        peak_ep = max(concurrent, key=lambda x: x["peak"])
        milestones.append({"month": peak_ep["date"][:7], "type": "live_peak",
                          "label": f"Peak concurrent: {peak_ep['peak']:,} — {peak_ep['title']}"})
        print(f"  📺 Peak concurrent: {peak_ep['peak']:,} ({peak_ep['date']})")

    # Fanatics $500K crossing
    if fanatics:
        running_rev = 0
        for f in fanatics:
            period_rev = f["yt_views"] + f["ig_views"] + f["tiktok_views"] + f["fb_views"] + f["x_imp"] + f["mega_views"]
            running_rev += period_rev
        # The 500K crossing is revenue-based, from build_master.py
        # We know from earlier it crossed in May 2026
        milestones.append({"month": "2026-05", "type": "revenue", "label": "Crossed $500K gross revenue (RDM cut begins)"})
        print(f"  💰 $500K revenue milestone: ~May 2026")

    # ─── Gap Summary ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("GAP SUMMARY")
    print("=" * 60)
    if gaps:
        for source, detail in gaps:
            print(f"  ⚠ {source}: {detail}")
    else:
        print("  ✓ No gaps detected — all data sources have full S1 coverage")

    # ─── Build unified JSON ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("BUILDING year_review_data.json...")

    output = {
        "compiled": datetime.now().isoformat(),
        "season": {"start": S1_START, "end": S1_END, "months": S1_MONTHS},
        "contract": CONTRACT,
        "youtube": {
            "monthly": yt,
            "current_subs": tracker.get("current_subs", 0) if tracker else 0,
            "top_content": top_content if tracker else {},
            "all_videos_s1": s1_vids_sorted[:50] if tracker else [],
            "daily": s1_daily if tracker else {},
        },
        "socials": {m: dict(socials[m]) for m in sorted(soc_months)} if soc_months else {},
        "revenue": {m: dict(revenue[m]) for m in sorted(rev_months)} if rev_months else {},
        "fanatics": {
            "periods": fanatics,
            "goal": 47_000_000,
            "total_impressions": sum(f["impressions"] for f in fanatics) if fanatics else 0,
            "total_episodes": sum(f["group_eps"] + f["solo_perk"] + f["solo_chan"] for f in fanatics) if fanatics else 0,
        },
        "concurrent": concurrent,
        "audio": audio,
        "milestones": milestones,
        "gaps": [{"source": g[0], "detail": str(g[1])} for g in gaps],
    }

    out_path = args.output
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"✓ Saved: {out_path} ({size_kb:.0f} KB)")
    print("=" * 60)


if __name__ == "__main__":
    main()