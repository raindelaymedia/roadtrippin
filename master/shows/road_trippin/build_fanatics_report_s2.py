"""
Road Trippin' × Fanatics — Season 2 delivery report (renewal Year 1: Oct 16 2026 – Oct 18 2027)
================================================================================================
Builds the client report for a window on top of rt_delivery.compute() (YouTube views DURING the window per
video, RT and Girls Tripp separately; GT Instagram from the non-collab URL list) plus the inputs file
data/reports/fanatics/inputs_rt_<start>_<end>.json for what the APIs can't give:

    {"rt_social": {"instagram": n, "tiktok": n, "x": n, "facebook": n}, "tiktok_count": n,
     "megaphone": {"rt": n, "gt": n},
     "counts": {"group_eps": n, "solo_perk": n, "solo_chan": n, "gt_eps": n,
                "shoutouts": n, "segments": n, "ad_reads": n,
                "perk_posts": n, "channing_posts": n, "rj_posts": n, "allie_posts": n},
     "top_social": [{"title": "...", "platform": "Instagram", "date": "Oct 20", "views": n}, ...],
     "notes": "..."}

Anything missing shows as "Pending" and counts as 0. Season to date = this window + the Season 2 rows already in
data/fanatics_history.csv (period_start ≥ Oct 16 2026). Draft by default; --write saves the window to the history
(do that once the report is final).

    python master/shows/road_trippin/build_fanatics_report_s2.py --start 2026-10-16 --end 2026-10-31
    python master/shows/road_trippin/build_fanatics_report_s2.py --start 2026-10-16 --end 2026-10-31 --write
"""

import argparse
import csv
import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rt_delivery as rd                                   # noqa: E402
from fanatics_report_template_s2 import render_html          # noqa: E402

HISTORY = os.path.join(HERE, "data", "fanatics_history.csv")
OUT_DIR = os.path.join(HERE, "data", "reports", "fanatics")
YEAR_START, YEAR_END = (date.fromisoformat(x) for x in rd.YEAR1)
YEAR_DAYS = rd.YEAR1_DAYS
TARGETS = {"eps": 85, "eps_min": 78, "integrations": 255}     # ~85 shoutouts + ~85 segments + ~85 ad reads
TALENT = [
    {"key": "rj", "name": "RICHARD JEFFERSON", "handle": "@RichardJefferson", "min_wk": 3},
    {"key": "perk", "name": "KENDRICK PERKINS", "handle": "@KendrickPerkins", "min_wk": 4},
    {"key": "channing", "name": "CHANNING FRYE", "handle": "@ChanningFrye", "min_wk": 4},
    {"key": "allie", "name": "ALLIE CLIFTON", "handle": "@AllieClifton", "min_wk": 3},
]
# History columns Season 2 adds to fanatics_history.csv (older rows leave them blank)
S2_FIELDS = ["gt_full_views", "gt_clip_views", "gt_short_views", "gt_yt_count_new", "gt_ig_posts",
             "rt_full_imp", "gt_full_imp", "rt_impressions", "gt_impressions"]


def _n(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def read_history():
    if not os.path.exists(HISTORY):
        return [], []
    with open(HISTORY, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def window_row(s, e, rec, videos, inp):
    """This window as a history row (raw numbers; None = still missing)."""
    yt, soc, au, c = rec["youtube"], rec["social"], rec["audio"], inp.get("counts", {})
    v = lambda show, k, f="views": (yt[show].get(k) or {}).get(f, 0)
    rt_full = v("RT", "group") + v("RT", "solo") + v("RT", "gt_episode")
    rt_full_new = v("RT", "group", "new") + v("RT", "solo", "new") + v("RT", "gt_episode", "new")
    rt_full_imp = sum((yt["RT"].get(k) or {}).get("impressions", 0) for k in ("group", "solo", "gt_episode"))
    gt_full, gt_full_imp = v("GT", "gt_episode"), (yt["GT"].get("gt_episode") or {}).get("impressions", 0)
    row = {
        "period_start": s, "period_end": e,
        "yt_full_views": rt_full, "yt_full_count_new": rt_full_new,
        "yt_clip_views": v("RT", "clip"), "yt_clip_count_new": v("RT", "clip", "new"),
        "yt_short_views": v("RT", "short"), "yt_short_count_new": v("RT", "short", "new"),
        "mega_views": au["RT"], "ig_views": soc["RT"]["instagram"], "tiktok_views": soc["RT"]["tiktok"],
        "tiktok_count_new": inp.get("tiktok_count"), "x_imp": soc["RT"]["x"], "fb_views": soc["RT"]["facebook"],
        "group_eps": c.get("group_eps"), "solo_perk": c.get("solo_perk"), "solo_chan": c.get("solo_chan"),
        "shoutouts": c.get("shoutouts"), "segments": c.get("segments"), "ad_reads": c.get("ad_reads"),
        "perk_posts": c.get("perk_posts"), "channing_posts": c.get("channing_posts"),
        "rj_posts": c.get("rj_posts"), "allie_posts": c.get("allie_posts"),
        "gt_full_views": gt_full, "gt_clip_views": v("GT", "clip"), "gt_short_views": v("GT", "short"),
        "gt_yt_count_new": sum(x.get("new", 0) for x in yt["GT"].values()),
        "gt_ig_views": soc["GT"]["instagram"], "gt_ig_posts": len(rec.get("gt_instagram_posts") or []),
        "gt_mega": au["GT"], "gt_eps": c.get("gt_eps"),
        "rt_full_imp": rt_full_imp, "gt_full_imp": gt_full_imp,
        "rt_impressions": rec["per_show"]["RT"]["impressions"], "gt_impressions": rec["per_show"]["GT"]["impressions"],
        "impressions": rec["impressions"],
        "note": "Season 2 (renewal Year 1) · counts toward the 130M goal · RT + Girls Tripp",
    }
    row["yt_total_views"] = row["yt_full_views"] + row["yt_clip_views"] + row["yt_short_views"]
    row["yt_total_count_new"] = row["yt_full_count_new"] + row["yt_clip_count_new"] + row["yt_short_count_new"]
    row["gt_yt_views"] = row["gt_full_views"] + row["gt_clip_views"] + row["gt_short_views"]
    return row


def top_cards(videos, show, kinds, start, end, n=3):
    pick = sorted((x for x in videos if x["show"] == show and x["kind"] in kinds and start <= x["published"] <= end),
                  key=lambda x: -(x.get("lifetime_views") or x["views"]))[:n]
    out = []
    for i, x in enumerate(pick, 1):
        dur = f"{x['secs'] // 60}:{x['secs'] % 60:02d}" if x.get("secs") else ""
        d = date.fromisoformat(x["published"])
        out.append({"rank": i, "views": x.get("lifetime_views") or x["views"], "title": x["title"], "url": x["url"],
                    "thumb": x["thumb"], "date": f"{d.strftime('%b')} {d.day:02d}", "dur": dur})
    return out


def assemble(s, e, row, prior, videos, inp):
    end = date.fromisoformat(e)
    tp = lambda k: row.get(k)
    cum = lambda k: (None if row.get(k) is None and not prior.get(k) else prior.get(k, 0) + (row.get(k) or 0))
    days_into = (end - YEAR_START).days + 1
    total_imp = prior.get("impressions", 0) + row["impressions"]
    plat = lambda k_tp, extra=None: {"tp": tp(k_tp), "cum": cum(k_tp), **(extra or {})}
    rt = {
        "yt_total": plat("yt_total_views", {"ct_new": row["yt_total_count_new"]}),
        "yt_full": plat("yt_full_views", {"ct_new": row["yt_full_count_new"]}),
        "yt_clip": plat("yt_clip_views", {"ct_new": row["yt_clip_count_new"]}),
        "yt_short": plat("yt_short_views", {"ct_new": row["yt_short_count_new"]}),
        "mega": plat("mega_views"), "ig": plat("ig_views"), "fb": plat("fb_views"), "x": plat("x_imp"),
        "tiktok": plat("tiktok_views", {"vids_tp": row.get("tiktok_count_new")}),
        "imp_tp": row["rt_impressions"], "imp_cum": prior.get("rt_impressions", 0) + row["rt_impressions"],
    }
    gt = {
        "yt_total": plat("gt_yt_views", {"ct_new": row["gt_yt_count_new"]}),
        "yt_full": plat("gt_full_views", {"ct_new": sum(1 for x in videos if x["show"] == "GT" and x["kind"] == "gt_episode" and x["new"])}),
        "yt_clip": plat("gt_clip_views", {"ct_new": sum(1 for x in videos if x["show"] == "GT" and x["kind"] == "clip" and x["new"])}),
        "yt_short": plat("gt_short_views", {"ct_new": sum(1 for x in videos if x["show"] == "GT" and x["kind"] == "short" and x["new"])}),
        "mega": plat("gt_mega"), "ig": plat("gt_ig_views", {"posts_tp": row.get("gt_ig_posts")}),
        "imp_tp": row["gt_impressions"], "imp_cum": prior.get("gt_impressions", 0) + row["gt_impressions"],
    }
    vd_keys = ["yt_total_views", "mega_views", "ig_views", "tiktok_views", "x_imp", "fb_views", "gt_yt_views", "gt_mega", "gt_ig_views"]
    ci = lambda k: int(cum(k) or 0)
    talent, need_total = [], 0.0
    for t in TALENT:
        need = t["min_wk"] * days_into / 7
        need_total += need
        talent.append({**t, "tp": row.get(f"{t['key']}_posts"), "cum": cum(f"{t['key']}_posts"), "need": need})
    tal_cum = [x["cum"] for x in talent]
    eps_cum = sum(ci(k) for k in ("group_eps", "solo_perk", "solo_chan"))
    return {
        "start": date.fromisoformat(s), "end": end, "generated": date.today(), "season": rd.SEASON,
        "year_start": YEAR_START, "year_end": YEAR_END, "year_days": YEAR_DAYS, "days_into": days_into,
        "pct_elapsed": days_into / YEAR_DAYS * 100,
        "tp_vd": sum(_n(row.get(k)) for k in vd_keys), "cum_vd": sum(ci(k) for k in vd_keys),
        "tp_imp": row["impressions"], "total_imp": total_imp, "pct_goal": total_imp / rd.DELIVERY_GOAL * 100,
        "pace": total_imp / days_into * YEAR_DAYS if days_into else 0,
        "rt": rt, "gt": gt, "targets": TARGETS,
        "eps": {"cum": eps_cum, "group": ci("group_eps"), "solo_perk": ci("solo_perk"), "solo_chan": ci("solo_chan"),
                "gt": cum("gt_eps")},
        "integrations": {"cum": ci("shoutouts") + ci("segments") + ci("ad_reads"), "shoutouts": ci("shoutouts"),
                         "segments": ci("segments"), "ad_reads": ci("ad_reads")},
        "talent": talent, "talent_need_total": need_total,
        "talent_tp_total": None if any(x["tp"] is None for x in talent) else sum(x["tp"] for x in talent),
        "talent_cum_total": None if any(x is None for x in tal_cum) else sum(tal_cum),
        "top_full": top_cards(videos, "RT", ("group", "solo"), s, e),
        "top_clip": top_cards(videos, "RT", ("clip",), s, e),
        "top_short": top_cards(videos, "RT", ("short",), s, e),
        "top_gt": top_cards(videos, "GT", ("gt_episode", "clip", "short"), s, e),
        "top_social": [{**p, "rank": i} for i, p in enumerate(inp.get("top_social") or [], 1)][:3],
        "method": {
            "rt_full_views": ci("yt_full_views"), "rt_full_imp": prior.get("rt_full_imp", 0) + row["rt_full_imp"],
            "gt_full_views": ci("gt_full_views"), "gt_full_imp": prior.get("gt_full_imp", 0) + row["gt_full_imp"],
            "cs_views": sum(ci(k) for k in ("yt_clip_views", "yt_short_views", "gt_clip_views", "gt_short_views")),
            "cs_imp": 2 * sum(ci(k) for k in ("yt_clip_views", "yt_short_views", "gt_clip_views", "gt_short_views")),
            "other": sum(ci(k) for k in ("mega_views", "ig_views", "tiktok_views", "x_imp", "fb_views", "gt_mega", "gt_ig_views")),
        },
    }


def write_history(fields, rows, row):
    fields = list(fields) or ["period_start", "period_end"]
    for k in list(row) + S2_FIELDS:
        if k not in fields:
            fields.insert(fields.index("note") if "note" in fields else len(fields), k)
    rows = [r for r in rows if not (r["period_start"] == row["period_start"] and r["period_end"] == row["period_end"])]
    rows.append({k: "" if row.get(k) is None else (str(int(row[k])) if isinstance(row[k], float) and row[k].is_integer() else str(row[k]))
                 for k in row})
    rows.sort(key=lambda r: r["period_start"])
    with open(HISTORY, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\r\n", extrasaction="ignore")
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in fields} for r in rows)


def main():
    ap = argparse.ArgumentParser(description="RT × Fanatics Season 2 delivery report")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--write", action="store_true", help="save this window to fanatics_history.csv (final reports only)")
    args = ap.parse_args()
    s, e = args.start, args.end
    inp = rd.load_inputs(s, e)
    print(f"RT × FANATICS · SEASON 2 REPORT · {s} → {e}" + ("" if inp else "  (no inputs file yet — socials/audio/counts Pending)"))
    rec, videos = rd.compute(s, e, inp)

    fields, hist = read_history()
    prior_rows = [r for r in hist if r["period_start"] >= rd.YEAR1[0] and r["period_end"] < s]
    prior = {}
    for r in prior_rows:
        for k, v in r.items():
            if k not in ("period_start", "period_end", "note") and (v or "").strip():
                prior[k] = prior.get(k, 0) + _n(v)
    row = window_row(s, e, rec, videos, inp)
    d = assemble(s, e, row, prior, videos, inp)

    tag = f"{s[5:7]}{s[8:10]}_{e[5:7]}{e[8:10]}_{e[2:4]}"
    out = os.path.join(OUT_DIR, f"Road_Trippin_Fanatics_S2_{tag}{'' if args.write else '_DRAFT'}.html")
    open(out, "w", encoding="utf-8").write(render_html(d))
    print(f"  impressions this window {rec['impressions']:,.0f} (RT {row['rt_impressions']:,.0f} · GT {row['gt_impressions']:,.0f})"
          f" · season {d['total_imp']:,.0f} = {d['pct_goal']:.1f}% of 130M with {d['pct_elapsed']:.1f}% of the year"
          f" · pace ~{d['pace'] / 1e6:.0f}M")
    if rec["missing"]:
        print(f"  ⚠ Pending (counted as 0): {', '.join(rec['missing'])}")
    if rec.get("gt_instagram_unmatched"):
        print(f"  ⚠ GT Instagram URLs not found on the account: {len(rec['gt_instagram_unmatched'])}")
    if args.write:
        write_history(fields, hist, row)
        print(f"  ✓ saved {s} → {e} to fanatics_history.csv")
    print(f"✓ {os.path.relpath(out)}")


if __name__ == "__main__":
    main()
