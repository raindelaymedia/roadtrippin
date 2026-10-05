"""
The Schultz Report × Fanatics Sportsbook — Monthly Delivery Report Builder
==========================================================================
Same shape as the Road Trippin' builder (build_fanatics_report.py), rebuilt for
the Schultz Report deal (PSA + Media Plan v1). Generates a print-ready HTML
report (open in a browser → Print → Save as PDF).

Data sources:
  • YouTube  — per-video pull for the SR channel (config_sr.py), same
               full / clip / short buckets and lifetime-views method as RT
  • socials_sr.csv (calendar-month rows), platform keys below:
        SR show accounts .... INSTAGRAM VIEWS · TIKTOK VIEWS · X IMPRESSIONS (or VIEWS)
                              INSTAGRAM = SR's own posts only. Collab posts with
                              @JordanSchultz share one view count, so they're
                              counted once, under Jordan.
        Jordan (reporter) ... JS_X / JS_INSTAGRAM / JS_TIKTOK
                              FANATICS_POSTS + FANATICS_IMPRESSIONS (X) or FANATICS_VIEWS
                              → Fanatics-integrated posts ONLY, not the whole account
        Keyshawn ............ KJ_INSTAGRAM / KJ_X  FANATICS_POSTS + FANATICS_VIEWS
        Podcast ............. AUDIO DOWNLOADS
    Anything missing is prompted for.
  • Manual prompts — episodes by type, sponsorship items, added value, events,
    top social posts. Answers are saved per period and reused as defaults on a
    re-run, so iterating on a report doesn't mean retyping everything.
  • data_sr/fanatics_history_sr.csv — one row per reported period (cumulative)

Usage (from repo root):
    python master/shows/schultz_report/build_fanatics_report_sr.py --start 2026-09-01 --end 2026-09-30
    python master/shows/schultz_report/build_fanatics_report_sr.py --start 2026-09-01 --end 2026-09-30 --no-write
"""

import argparse
import csv
import json
import os
import re
from datetime import date, datetime, timedelta

# ─────────────────────────────────────────────────────────────────
# CONTRACT CONSTANTS  (PSA + Media Plan v1)
# ─────────────────────────────────────────────────────────────────
TERM_START = date(2026, 8, 1)          # flight: Aug 2026 – Jul 2027 (12 months)
TERM_END   = date(2027, 7, 31)
TERM_DAYS  = (TERM_END - TERM_START).days + 1
IMP_GOAL   = 87_915_000                # Minimum Impression Target
# Weekly posting averages are measured from here (first full month, first report)
POSTING_START = date(2026, 9, 1)

# Episodes: floor / cycle target / ceiling (ceiling includes specials)
EP_FLOOR, EP_TARGET, EP_CEILING = 90, 100, 115
EP_TYPES = [   # key, label, plan count, carries a sponsored segment (→ 6x)
    ("eps_tue",       "Jordan-Led (Tue)",               39, True),
    ("eps_thu_kj",    "Jordan and/or Keyshawn (Thu)",   22, True),
    ("eps_thu_guest", "Jordan + Guest (Thu)",           17, False),
    ("eps_off",       "Jordan-Led (Offseason)",         13, True),
]
SPECIALS_MAX = 25   # incremental; outside the floor and the impression target

SPONSOR_ITEMS = [   # key, label, target
    ("shoutouts",   "Top-of-Show Shoutouts",          90),
    ("segments",    "Sponsored Segments (On-Cam)",    75),
    ("ad_reads",    "Podcast Ad Reads (:60)",         90),
    ("video_reads", "YouTube Host-Read Ads",          90),
    ("prime",       "Prime (First-Position) Placement", 90),
]
ADDED_VALUE = [     # key, label, target
    ("inapp_weeks", "In-App Content & Picks (weeks)", 50),
    ("fancash",     "FanCash / Collectible Giveaways", 40),
]
CLIPS_TARGET, SHORTS_TARGET = 300, 450

REPORTER = [  # key, display, handle, platform key in socials_sr.csv, metric, posts target, min/wk
    {"key": "js_x",  "name": "JORDAN SCHULTZ · X",         "handle": "@JordanSchultz", "plat": "JS_X",
     "metric": "FANATICS_IMPRESSIONS", "target": 150, "min_wk": 2, "unit": "impressions"},
    {"key": "js_ig", "name": "JORDAN SCHULTZ · INSTAGRAM", "handle": "@JordanSchultz", "plat": "JS_INSTAGRAM",
     "metric": "FANATICS_VIEWS", "target": 100, "min_wk": 2, "unit": "views"},
    {"key": "js_tt", "name": "JORDAN SCHULTZ · TIKTOK",    "handle": "@JordanSchultz", "plat": "JS_TIKTOK",
     "metric": "FANATICS_VIEWS", "target": 50, "min_wk": 1, "unit": "views"},
]
KEYSHAWN = {"plats": ["KJ_INSTAGRAM", "KJ_X"], "target": 30, "min_wk": 1}

EVENTS = [   # key, label, target
    ("london",    "NFL in London (Oct 4)",   1),
    ("series",    "Original Branded Series", 6),
    ("tentpoles", "Tentpole Activations",    6),
]

MULT_SEG   = 6   # full episode with a sponsored segment
MULT_NOSEG = 5   # full episode without one (guest episodes, specials)
MULT_CLIPS_SHORTS = 2
SHORTS_MAX, CLIPS_MAX = 180, 1800   # seconds: ≤3:00 short, ≤30:00 clip, >30:00 full

MANUAL_KEYS = ([k for k, *_ in EP_TYPES] + ["eps_special"] + [k for k, *_ in SPONSOR_ITEMS]
               + [k for k, *_ in ADDED_VALUE] + [k for k, *_ in EVENTS])
SOCIAL_KEYS = ["ig_views", "tiktok_views", "tiktok_posts", "x_imp",
               "js_x_views", "js_x_posts", "js_ig_views", "js_ig_posts", "js_tt_views", "js_tt_posts",
               "kj_views", "kj_posts", "audio_downloads"]
HISTORY_FIELDS = (["period_start", "period_end",
                   "yt_total_views", "yt_total_count_new", "yt_full_views", "yt_full_count_new",
                   "yt_clip_views", "yt_clip_count_new", "yt_short_views", "yt_short_count_new"]
                  + SOCIAL_KEYS + MANUAL_KEYS
                  + ["imp_youtube", "imp_social", "imp_audio", "impressions"])


# ═════════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════════
def fmt(n):
    try:
        return f"{int(round(float(n))):,}"
    except (ValueError, TypeError):
        return str(n)


def to_int(v):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def parse_iso_duration(dur):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0) if m else 0


def hms(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def prompt_int(label, default=None):
    sfx = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {label}{sfx}: ").strip().replace(",", "")
        if not raw and default is not None:
            return int(default)
        try:
            return int(float(raw))
        except ValueError:
            print("    ↳ enter a whole number.")


# ═════════════════════════════════════════════════════════════════
# YOUTUBE
# ═════════════════════════════════════════════════════════════════
def authenticate_yt():
    from config_sr import (YT_CLIENT_ID as CLIENT_ID, YT_CLIENT_SECRET as CLIENT_SECRET,
                           YT_REFRESH_TOKEN as REFRESH_TOKEN)
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials(
        token=None, refresh_token=REFRESH_TOKEN, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.readonly"])
    creds.refresh(Request())
    return creds


def pull_videos(youtube, start, end):
    """Every video PUBLISHED in [start, end], bucketed by length. Views are lifetime
    views as of now (same method as the RT report)."""
    from config_sr import YT_CHANNEL_ID as CHANNEL_ID
    ch = youtube.channels().list(part="contentDetails", id=CHANNEL_ID).execute(num_retries=3)
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    s, e = start.isoformat(), end.isoformat()
    out, seen, page = [], set(), None
    while True:
        resp = youtube.playlistItems().list(part="contentDetails", playlistId=uploads,
                                            maxResults=50, pageToken=page).execute(num_retries=3)
        ids = [it["contentDetails"]["videoId"] for it in resp["items"]]
        if not ids:
            break
        det = youtube.videos().list(part="contentDetails,snippet,statistics",
                                    id=",".join(ids)).execute(num_retries=3)
        oldest = None
        for v in det["items"]:
            if v["id"] in seen:
                continue
            seen.add(v["id"])
            pub = v["snippet"]["publishedAt"][:10]
            oldest = pub if oldest is None else min(oldest, pub)
            if not (s <= pub <= e):
                continue
            secs = parse_iso_duration(v["contentDetails"].get("duration"))
            out.append({
                "id": v["id"], "title": v["snippet"]["title"], "published": pub, "secs": secs,
                "views": int(v["statistics"].get("viewCount", 0)),
                "thumb": f"https://i.ytimg.com/vi/{v['id']}/maxresdefault.jpg",
                "url": f"https://youtu.be/{v['id']}",
                "bucket": "short" if secs <= SHORTS_MAX else "clip" if secs <= CLIPS_MAX else "full",
            })
        page = resp.get("nextPageToken")
        if not page or (oldest and oldest < s):
            break
    return out


def yt_period(videos):
    d = {b: {"views": 0, "count": 0} for b in ("full", "clip", "short")}
    for v in videos:
        d[v["bucket"]]["views"] += v["views"]
        d[v["bucket"]]["count"] += 1
    return {
        "yt_total_views": sum(d[b]["views"] for b in d), "yt_total_count_new": sum(d[b]["count"] for b in d),
        "yt_full_views": d["full"]["views"], "yt_full_count_new": d["full"]["count"],
        "yt_clip_views": d["clip"]["views"], "yt_clip_count_new": d["clip"]["count"],
        "yt_short_views": d["short"]["views"], "yt_short_count_new": d["short"]["count"],
    }


# ═════════════════════════════════════════════════════════════════
# SOCIALS + AUDIO  (socials_sr.csv)
# ═════════════════════════════════════════════════════════════════
def socials_for_month(csv_path, ym):
    vals = {}
    if os.path.exists(csv_path):
        with open(csv_path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["period"].strip() != ym:
                    continue
                try:
                    vals[(r["platform"].strip().upper(), r["metric"].strip().upper())] = int(float(r["value"]))
                except (ValueError, TypeError):
                    pass

    def first(*keys):
        return next((vals[k] for k in keys if k in vals), None)

    out = {
        "ig_views":      first(("INSTAGRAM", "VIEWS")),
        "tiktok_views":  first(("TIKTOK", "VIEWS")),
        "tiktok_posts":  first(("TIKTOK", "POSTS")),
        "x_imp":         first(("X", "IMPRESSIONS"), ("X", "VIEWS")),
        "audio_downloads": first(("AUDIO", "DOWNLOADS"), ("PODCAST", "DOWNLOADS")),
        "kj_views": None, "kj_posts": None,
    }
    for r in REPORTER:
        out[f"{r['key']}_views"] = first((r["plat"], r["metric"]), (r["plat"], "FANATICS_VIEWS"))
        out[f"{r['key']}_posts"] = first((r["plat"], "FANATICS_POSTS"))
    kv = [first((p, "FANATICS_VIEWS"), (p, "FANATICS_IMPRESSIONS")) for p in KEYSHAWN["plats"]]
    kp = [first((p, "FANATICS_POSTS")) for p in KEYSHAWN["plats"]]
    if any(v is not None for v in kv):
        out["kj_views"] = sum(v or 0 for v in kv)
    if any(v is not None for v in kp):
        out["kj_posts"] = sum(v or 0 for v in kp)
    return out


SOCIAL_PROMPTS = {
    "ig_views": "SR Instagram views — SR's own posts only (leave out collabs with Jordan)", "tiktok_views": "SR TikTok views", "tiktok_posts": "SR TikTok posts",
    "x_imp": "SR X impressions",
    "js_x_views": "Jordan X — Fanatics-post impressions", "js_x_posts": "Jordan X — Fanatics posts",
    "js_ig_views": "Jordan IG — Fanatics-post views", "js_ig_posts": "Jordan IG — Fanatics posts",
    "js_tt_views": "Jordan TikTok — Fanatics-post views", "js_tt_posts": "Jordan TikTok — Fanatics posts",
    "kj_views": "Keyshawn — Fanatics-post views (IG + X)", "kj_posts": "Keyshawn — Fanatics posts (IG + X)",
    "audio_downloads": "Podcast downloads",
}


def fill_socials(soc, saved):
    missing = [k for k in SOCIAL_KEYS if soc.get(k) is None]
    if missing:
        print("\nNot in socials_sr.csv for this month — enter now (0 if none):")
    for k in missing:
        soc[k] = prompt_int(SOCIAL_PROMPTS[k], saved.get(k, 0))
    return soc


# ═════════════════════════════════════════════════════════════════
# MANUAL INPUTS
# ═════════════════════════════════════════════════════════════════
def prompt_manual(saved):
    d = saved or {}
    m = {}
    print("\n" + "─" * 60 + "\nMANUAL FIELDS — this period's counts (Enter keeps [default])\n" + "─" * 60)
    print("\nEpisodes aired:")
    for k, label, *_ in EP_TYPES:
        m[k] = prompt_int(label, d.get(k, 0))
    m["eps_special"] = prompt_int("Special / Tentpole episodes", d.get("eps_special", 0))
    print("\nSponsorship delivery:")
    for k, label, _ in SPONSOR_ITEMS:
        m[k] = prompt_int(label, d.get(k, 0))
    print("\nAdded value:")
    for k, label, _ in ADDED_VALUE:
        m[k] = prompt_int(label, d.get(k, 0))
    print("\nMarquee moments delivered this period:")
    for k, label, _ in EVENTS:
        m[k] = prompt_int(label, d.get(k, 0))

    prev = d.get("top_social", [])
    print("\nTop 3 social posts (Enter on a blank title keeps the saved list):")
    socials = []
    for i in range(1, 4):
        old = prev[i - 1] if i - 1 < len(prev) else {}
        title = input(f"  #{i} title{(' [' + old['title'][:40] + ']') if old else ''}: ").strip()
        if not title:
            if old:
                socials.append(old)
                continue
            break
        plat = input(f"  #{i} platform / account (e.g. Instagram · @JordanSchultz): ").strip() or "Instagram"
        pdate = input(f"  #{i} date (e.g. Sep 12): ").strip()
        views = prompt_int(f"#{i} views")
        socials.append({"rank": i, "platform": plat, "date": pdate, "views": views, "title": title})
    m["top_social"] = socials
    return m


# ═════════════════════════════════════════════════════════════════
# HISTORY
# ═════════════════════════════════════════════════════════════════
def load_history(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def sum_history(rows):
    return {k: sum(to_int(r.get(k)) for r in rows) for k in HISTORY_FIELDS[2:]}


def write_history(path, row):
    rows = [r for r in load_history(path)
            if not (r["period_start"] == row["period_start"] and r["period_end"] == row["period_end"])]
    rows.append({k: str(row.get(k, 0)) for k in HISTORY_FIELDS})
    rows.sort(key=lambda r: r["period_start"])
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        w.writeheader()
        w.writerows(rows)


# ═════════════════════════════════════════════════════════════════
# IMPRESSIONS
# ═════════════════════════════════════════════════════════════════
def period_impressions(row):
    """YouTube / Social / Audio impressions for ONE period.
    Full episodes: 6x for episode types with a sponsored segment, 5x for guest
    episodes and specials — blended by this period's episode mix (the API can't
    tell which episode is which type). Clips & Shorts 2x. Everything else 1x."""
    seg = sum(row.get(k, 0) for k, _, _, has_seg in EP_TYPES if has_seg)
    noseg = sum(row.get(k, 0) for k, _, _, has_seg in EP_TYPES if not has_seg) + row.get("eps_special", 0)
    blend = (seg * MULT_SEG + noseg * MULT_NOSEG) / (seg + noseg) if (seg + noseg) else MULT_SEG
    imp_yt = round(row["yt_full_views"] * blend
                   + (row["yt_clip_views"] + row["yt_short_views"]) * MULT_CLIPS_SHORTS)
    imp_social = (row["ig_views"] + row["tiktok_views"] + row["x_imp"]
                  + row["js_x_views"] + row["js_ig_views"] + row["js_tt_views"] + row["kj_views"])
    imp_audio = row["audio_downloads"]
    return imp_yt, imp_social, imp_audio, blend


# ═════════════════════════════════════════════════════════════════
# ASSEMBLE → dict for the renderer
# ═════════════════════════════════════════════════════════════════
def assemble(row, prior, top_content, top_social, start, end, generated):
    cum = {k: prior.get(k, 0) + to_int(row.get(k, 0)) for k in HISTORY_FIELDS[2:]}
    # measured to the end of the reporting period, not the day the report is run
    days_into = max(0, min((min(end, generated) - TERM_START).days + 1, TERM_DAYS))
    weeks = max(((min(end, generated) - POSTING_START).days + 1) // 7, 1)
    pct = lambda a, b: (a / b * 100) if b else 0

    vd = lambda r: (r["yt_total_views"] + r["audio_downloads"] + r["ig_views"] + r["tiktok_views"]
                    + r["x_imp"] + r["js_x_views"] + r["js_ig_views"]
                    + r["js_tt_views"] + r["kj_views"])
    total_imp = cum["impressions"]
    talent = lambda r: r["js_x_views"] + r["js_ig_views"] + r["js_tt_views"] + r["kj_views"]
    show = lambda r: r["ig_views"] + r["tiktok_views"] + r["x_imp"]

    eps_tp = sum(row[k] for k, *_ in EP_TYPES)
    eps_cum = sum(cum[k] for k, *_ in EP_TYPES)
    reporter = []
    for r in REPORTER:
        posts = cum[f"{r['key']}_posts"]
        reporter.append({**r, "tp_posts": row[f"{r['key']}_posts"], "cum_posts": posts,
                         "tp_views": row[f"{r['key']}_views"], "cum_views": cum[f"{r['key']}_views"],
                         "wk_avg": posts / weeks})

    return {
        "start": start, "end": end, "generated": generated,
        "term_start": TERM_START, "term_end": TERM_END, "term_days": TERM_DAYS,
        "days_into": days_into, "pct_elapsed": pct(days_into, TERM_DAYS), "weeks": weeks,
        "tp_vd": vd(row), "cum_vd": vd(cum),
        "goal": IMP_GOAL, "total_imp": total_imp, "pct_plan": pct(total_imp, IMP_GOAL),
        "pace": round(total_imp / days_into * TERM_DAYS) if days_into else 0,
        "kpi": {   # contract KPI split: YouTube / Social / Audio
            "youtube": {"tp_views": row["yt_total_views"], "cum_views": cum["yt_total_views"],
                        "tp_imp": row["imp_youtube"], "cum_imp": cum["imp_youtube"]},
            # Social is shown as two separate sources so neither figure is ambiguous.
        # Social posts count 1x, so views = impressions for both.
        "social_talent": {"tp_views": talent(row), "cum_views": talent(cum),
                          "tp_imp": talent(row), "cum_imp": talent(cum)},
        "social_show": {"tp_views": show(row), "cum_views": show(cum),
                        "tp_imp": show(row), "cum_imp": show(cum)},
            "audio": {"tp_views": row["audio_downloads"], "cum_views": cum["audio_downloads"],
                      "tp_imp": row["imp_audio"], "cum_imp": cum["imp_audio"]},
        },
        "row": row, "cum": cum,
        "eps": {"tp": eps_tp, "cum": eps_cum, "special_tp": row["eps_special"], "special_cum": cum["eps_special"],
                "types": [{"key": k, "label": lbl, "plan": plan, "seg": seg, "tp": row[k], "cum": cum[k]}
                          for k, lbl, plan, seg in EP_TYPES]},
        "sponsor": [{"label": lbl, "target": t, "tp": row[k], "cum": cum[k]} for k, lbl, t in SPONSOR_ITEMS],
        "content": [{"label": "YouTube Clips (branded)", "target": CLIPS_TARGET,
                     "tp": row["yt_clip_count_new"], "cum": cum["yt_clip_count_new"]},
                    {"label": "YouTube Shorts (branded)", "target": SHORTS_TARGET,
                     "tp": row["yt_short_count_new"], "cum": cum["yt_short_count_new"]}]
                   + [{"label": lbl, "target": t, "tp": row[k], "cum": cum[k]} for k, lbl, t in ADDED_VALUE],
        "reporter": reporter,
        "keyshawn": {"tp_posts": row["kj_posts"], "cum_posts": cum["kj_posts"], "target": KEYSHAWN["target"],
                     "tp_views": row["kj_views"], "cum_views": cum["kj_views"], "min_wk": KEYSHAWN["min_wk"]},
        "events": [{"label": lbl, "target": t, "tp": row[k], "cum": cum[k]} for k, lbl, t in EVENTS],
        "top_full": top_content.get("full", []), "top_clip": top_content.get("clip", []),
        "top_short": top_content.get("short", []), "top_social": top_social,
        "blend": row.get("_blend", MULT_SEG),
    }


# ═════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════
from fanatics_report_template_sr import render_html


def main():
    ap = argparse.ArgumentParser(description="The Schultz Report × Fanatics — delivery report builder")
    ap.add_argument("--start", help="Period start YYYY-MM-DD (default: last full month)")
    ap.add_argument("--end", help="Period end YYYY-MM-DD")
    ap.add_argument("--no-write", action="store_true", help="Don't write the period to fanatics_history_sr.csv")
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = args.data_dir or os.path.join(script_dir, "data_sr")
    out_dir = os.path.join(data_dir, "reports", "fanatics")
    os.makedirs(out_dir, exist_ok=True)
    hist_path = os.path.join(data_dir, "fanatics_history_sr.csv")

    if args.start and args.end:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
        end = datetime.strptime(args.end, "%Y-%m-%d").date()
    else:   # default: the last full calendar month
        end = date.today().replace(day=1) - timedelta(days=1)
        start = end.replace(day=1)

    print("=" * 60 + "\nTHE SCHULTZ REPORT × FANATICS — DELIVERY REPORT BUILDER\n" + "=" * 60)
    print(f"Period: {start} → {end}   ·   Term: {TERM_START} → {TERM_END}")

    inputs_path = os.path.join(out_dir, f"inputs_{start:%Y%m%d}_{end:%Y%m%d}.json")
    saved = json.load(open(inputs_path, encoding="utf-8")) if os.path.exists(inputs_path) else {}
    if saved:
        print(f"Loaded saved inputs for this period → press Enter to keep them")

    # YouTube
    creds = authenticate_yt()
    from googleapiclient.discovery import build as build_api
    youtube = build_api("youtube", "v3", credentials=creds)
    print("\nPulling YouTube …")
    vids = pull_videos(youtube, start, end)
    row = yt_period(vids)

    # Socials + audio
    soc = fill_socials(socials_for_month(os.path.join(data_dir, "socials_sr.csv"), start.strftime("%Y-%m")), saved)
    row.update({k: to_int(soc[k]) for k in SOCIAL_KEYS})

    # Manual
    manual = prompt_manual(saved)
    row.update({k: manual[k] for k in MANUAL_KEYS})
    json.dump({**{k: row[k] for k in SOCIAL_KEYS}, **manual}, open(inputs_path, "w", encoding="utf-8"), indent=2)

    imp_yt, imp_soc, imp_aud, blend = period_impressions(row)
    row.update({"period_start": start.isoformat(), "period_end": end.isoformat(),
                "imp_youtube": imp_yt, "imp_social": imp_soc, "imp_audio": imp_aud,
                "impressions": imp_yt + imp_soc + imp_aud, "_blend": blend})

    def top3(bucket):
        vs = sorted([v for v in vids if v["bucket"] == bucket], key=lambda x: -x["views"])[:3]
        return [{"rank": i + 1, "views": v["views"], "title": v["title"], "thumb": v["thumb"], "url": v["url"],
                 "date": datetime.strptime(v["published"], "%Y-%m-%d").strftime("%b %d"),
                 "dur": hms(v["secs"]) if bucket == "full" else ""} for i, v in enumerate(vs)]
    top_content = {b: top3(b) for b in ("full", "clip", "short")}

    prior_rows = [r for r in load_history(hist_path) if r["period_end"] < start.isoformat()]
    data = assemble(row, sum_history(prior_rows), top_content, manual["top_social"], start, end, date.today())

    html = render_html(data)
    out_path = os.path.join(out_dir, f"Schultz_Report_Fanatics_{start:%m%d}_{end:%m%d}_{end:%y}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✓ Report: {out_path}")
    print(f"  Impressions this period {fmt(row['impressions'])}  (YouTube {fmt(imp_yt)} · Social {fmt(imp_soc)} [Jordan & Keyshawn {fmt(data['kpi']['social_talent']['tp_imp'])} / SR show {fmt(data['kpi']['social_show']['tp_imp'])}]"
          f" · Audio {fmt(imp_aud)})  ·  full-episode multiplier {blend:.2f}x")
    print(f"  Cumulative {fmt(data['total_imp'])}  ·  {data['pct_plan']:.2f}% of {fmt(IMP_GOAL)}"
          f"  ·  pace {fmt(data['pace'])}")
    if not args.no_write:
        write_history(hist_path, row)
        print(f"  ↳ saved period to {os.path.basename(hist_path)}")
    print("=" * 60)


if __name__ == "__main__":
    main()