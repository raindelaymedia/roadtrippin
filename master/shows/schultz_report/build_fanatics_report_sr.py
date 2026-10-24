"""
The Schultz Report × Fanatics Sportsbook — Monthly Delivery Report Builder
==========================================================================
Same shape as the Road Trippin' builder (build_fanatics_report.py), rebuilt for
the Schultz Report deal (PSA + Media Plan v1). Generates a print-ready HTML
report (open in a browser → Print → Save as PDF).

Only Fanatics-watermarked content counts toward delivery.

Data sources:
  • YouTube  — views that happened DURING the period on every SR channel video posted
               on/after CONTENT_START (Sep 1, 2026), per video (YouTube Analytics; see
               master/yt_period_views.py). New-upload counts = videos published in the period.
  • data_sr/fanatics_episodes_sr.csv — every full episode, tagged by type:
        solo · keyshawn · offseason ... 6x  (shoutout, segment, YouTube host-read,
                                             podcast ad read, first position, branding)
        player · special .............. 5x  (no sponsored segment)
    Any other video over 30 min stops the run until it's tagged. Clips & Shorts 2x.
  • data_sr/fanatics_posts_sr.csv — every watermarked social post by URL
        (SR = show account, KJ = Keyshawn). Instagram views are refreshed through
        the SR Instagram token when it can see the post; otherwise the CSV value is used.
  • socials_sr.csv — SR TikTok VIEWS / POSTS and X IMPRESSIONS (or VIEWS), every
    calendar month the period touches (all posts on those accounts are watermarked).
  • Manual prompts — sponsorship items, added value, events, and Jordan's reported
    totals. Answers are saved per period and reused as defaults on a re-run.
  • data_sr/fanatics_history_sr.csv — one row per reported period (cumulative)

Pending items (no data access yet) show as "Pending" and count as zero:
  Keyshawn X, FanCash giveaways, in-app content. Jordan's reported figures are
  shown but NOT counted until they can be verified (JORDAN_COUNTED below).

Usage (from repo root):
    python master/shows/schultz_report/build_fanatics_report_sr.py --start 2026-08-18 --end 2026-09-30 --no-write
    python master/shows/schultz_report/build_fanatics_report_sr.py --start 2026-08-18 --end 2026-09-30
"""

import argparse
import csv
import json
import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# ─────────────────────────────────────────────────────────────────
# CONTRACT CONSTANTS  (PSA + Media Plan v1)
# ─────────────────────────────────────────────────────────────────
TERM_START = date(2026, 9, 1)          # partnership effectively began Sep 1 (first Fanatics content);
TERM_END   = date(2027, 8, 31)          # 12-month flight → Aug 31, 2027 (PSA dates said Aug 2026 – Jul 2027)
TERM_DAYS  = (TERM_END - TERM_START).days + 1
# YouTube: every view during a period on channel videos posted on/after this date counts
CONTENT_START = date(2026, 9, 1)
IMP_GOAL   = 87_915_000                # Minimum Impression Target
# Weekly posting averages are measured from here (start of the first report)
POSTING_START = date(2026, 9, 1)     # first watermarked content: September 2026
REPORT_VERSION = "v1.1"

# Episodes: floor / cycle target / ceiling (ceiling includes specials)
EP_FLOOR, EP_TARGET, EP_CEILING = 90, 100, 115
EP_TYPES = [   # type in fanatics_episodes_sr.csv, label, plan count, carries a sponsored segment (→ 6x)
    ("solo",      "Jordan-Led (Solo)",       39, True),
    ("keyshawn",  "Jordan + Keyshawn",       22, True),
    ("player",    "Jordan + Player",         17, True),
    ("offseason", "Jordan-Led (Offseason)",  13, True),
]
SPECIALS_MAX = 25   # incremental; outside the floor and the impression target

SPONSOR_ITEMS = [   # key, label, target, default = episodes with segment only?
    ("shoutouts",   "Top-of-Show Shoutouts",            90, False),
    ("segments",    "Sponsored Segments (On-Cam)",      75, True),
    ("video_reads", "YouTube Host-Read Ads",            90, False),
    ("ad_reads",    "Podcast Ad Reads (:60)",           90, False),
    ("prime",       "Prime (First-Position) Placement", 90, False),
    ("branding",    "Fanatics Branding (Watermark + Set)", 90, False),
]
ADDED_VALUE = [     # key, label, target
    ("inapp_weeks", "In-App Content & Picks (weeks)", 50),
    ("fancash",     "FanCash / Collectible Giveaways", 40),
]
CLIPS_TARGET, SHORTS_TARGET = 300, 450

REPORTER = [  # key, display, handle, metric label, posts target, min/wk
    {"key": "js_x",  "name": "JORDAN SCHULTZ · X",         "handle": "@JordanSchultz", "target": 150, "min_wk": 2, "unit": "impressions"},
    {"key": "js_ig", "name": "JORDAN SCHULTZ · INSTAGRAM", "handle": "@JordanSchultz", "target": 100, "min_wk": 2, "unit": "views"},
    {"key": "js_tt", "name": "JORDAN SCHULTZ · TIKTOK",    "handle": "@JordanSchultz", "target": 50,  "min_wk": 1, "unit": "views"},
]
JORDAN_COUNTED = True    # Sprout Social: Fanatics-tagged posts on Jordan's personal accounts
KEYSHAWN = {"target": 30, "min_wk": 1}

EVENTS = [   # key, label, target
    ("london",    "NFL in London (Oct 4)",   1),
    ("series",    "Original Branded Series", 6),
    ("tentpoles", "Tentpole Activations",    6),
]

# Impressions per view/download = Fanatics elements delivered in it (agreed Oct 2026)
MULT_EPISODE = 4       # full episode (every type): top-of-show shoutout, ad read, branded segment
                       # (Risers & Fallers Tue / SNF Parlay Fri), Fanatics branded imagery
MULT_AUDIO = 3         # podcast download: shoutout, ad read, branded segment (no imagery in audio)
MULT_CLIPS_SHORTS = 2
SHORTS_MAX, CLIPS_MAX = 180, 1800   # seconds: ≤3:00 short, ≤30:00 clip; longer must be tagged

# Fields with no data access yet: shown as "Pending", counted as zero
PENDING = {"kj_x_views", "kj_x_posts", "fancash", "inapp_weeks"}

ET = ZoneInfo("America/New_York")
IG_API = "https://graph.instagram.com/v25.0"

EP_KEYS = [f"eps_{t}" for t, *_ in EP_TYPES] + ["eps_special"]
MANUAL_KEYS = [k for k, *_ in SPONSOR_ITEMS] + [k for k, *_ in ADDED_VALUE] + [k for k, *_ in EVENTS]
JORDAN_KEYS = [f"{r['key']}_{m}" for r in REPORTER for m in ("views", "posts")]
SOCIAL_KEYS = (["ig_views", "ig_posts", "tiktok_views", "tiktok_posts", "x_imp",
                "kj_ig_views", "kj_ig_posts", "kj_x_views", "kj_x_posts", "audio_downloads"] + JORDAN_KEYS)
HISTORY_FIELDS = (["period_start", "period_end",
                   "yt_total_views", "yt_total_count_new", "yt_full_views", "yt_full_count_new",
                   "yt_clip_views", "yt_clip_count_new", "yt_short_views", "yt_short_count_new"]
                  + EP_KEYS + SOCIAL_KEYS + MANUAL_KEYS
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


def et_date(iso):
    """UTC ISO timestamp → YYYY-MM-DD in Eastern time."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET).date().isoformat()


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


def months_in(start, end):
    ym, out = start.replace(day=1), []
    while ym <= end:
        out.append(ym.strftime("%Y-%m"))
        ym = (ym + timedelta(days=32)).replace(day=1)
    return out


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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


def pull_videos(youtube, yta, start, end, episodes):
    """Every channel video published on/after CONTENT_START, with the views that happened
    DURING [start, end] (YouTube Analytics) — see master/yt_period_views.py. Videos
    published in the period are flagged `new` (they drive the counts); every video's
    period views count toward impressions. Tagged episodes are full episodes whatever
    their length; everything else is bucketed by length."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from yt_period_views import uploads_since, period_views
    from config_sr import YT_CHANNEL_ID as CHANNEL_ID
    vids = [v for v in uploads_since(youtube, CHANNEL_ID, CONTENT_START.isoformat()) if v["published"] <= end.isoformat()]
    views = period_views(yta, [v["id"] for v in vids], start, end)
    out = []
    for v in vids:
        ep_type = episodes.get(v["id"], {}).get("type")
        secs = v["secs"]
        out.append({**v, "views": views.get(v["id"], 0), "new": v["published"] >= start.isoformat(),
                    "ep_type": ep_type,
                    "bucket": "full" if ep_type else "short" if secs <= SHORTS_MAX else "clip" if secs <= CLIPS_MAX else "untagged"})
    return out


def yt_period(videos):
    """Views = views during the period on all since-cutoff content; counts = new uploads only."""
    d = {b: {"views": 0, "count": 0} for b in ("full", "clip", "short")}
    for v in videos:
        d[v["bucket"]]["views"] += v["views"]
        d[v["bucket"]]["count"] += 1 if v["new"] else 0
    row = {
        "yt_total_views": sum(d[b]["views"] for b in d), "yt_total_count_new": sum(d[b]["count"] for b in d),
        "yt_full_views": d["full"]["views"], "yt_full_count_new": d["full"]["count"],
        "yt_clip_views": d["clip"]["views"], "yt_clip_count_new": d["clip"]["count"],
        "yt_short_views": d["short"]["views"], "yt_short_count_new": d["short"]["count"],
    }
    for t, *_ in EP_TYPES + [("special",)]:
        row[f"eps_{t}"] = sum(1 for v in videos if v["ep_type"] == t and v["new"])
    return row


def episode_multiplier(ep_type):
    seg = {t: has_seg for t, _, _, has_seg in EP_TYPES}
    return MULT_EPISODE                 # same for every episode type (types still drive episode counts)


# ═════════════════════════════════════════════════════════════════
# SOCIAL
# ═════════════════════════════════════════════════════════════════
def load_ig_token():
    tok = os.environ.get("IG_TOKEN_SR")
    if tok:
        return tok
    try:
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "config_socials.py")
        spec = importlib.util.spec_from_file_location("config_socials", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "IG_TOKEN_SR", None)
    except (FileNotFoundError, AttributeError):
        return None


def refresh_post_views(posts, earliest):
    """Refresh Instagram views for ledger posts visible to the SR account. Returns how many."""
    tok = load_ig_token()
    if not tok:
        print("  · No IG_TOKEN_SR — using the views already in fanatics_posts_sr.csv")
        return 0
    import requests
    code = lambda u: (re.search(r"/(?:p|reel|reels)/([\w-]+)", u or "") or [None, None])[1]
    media, url = {}, f"{IG_API}/me/media"
    params = {"fields": "id,permalink,timestamp", "limit": 100, "access_token": tok}
    while url:
        r = requests.get(url, params=params, timeout=30).json()
        if "error" in r:
            print(f"  ⚠ Instagram: {r['error'].get('message', '')[:80]} — using CSV views")
            return 0
        batch = r.get("data", [])
        media.update({code(m["permalink"]): m["id"] for m in batch})
        url, params = r.get("paging", {}).get("next"), None
        if batch and batch[-1]["timestamp"][:10] < earliest:
            break
    n, today = 0, date.today().isoformat()
    for p in posts:
        mid = media.get(code(p["url"])) if p["platform"].upper() == "INSTAGRAM" else None
        if not mid:
            continue
        ins = requests.get(f"{IG_API}/{mid}/insights", params={"metric": "views", "access_token": tok},
                           timeout=30).json()
        vals = {x["name"]: x["values"][0]["value"] for x in ins.get("data", [])}
        if "views" in vals:
            p.update({"views": str(vals["views"]), "views_source": "api", "views_as_of": today})
            n += 1
    return n


TT_ACCOUNTS = {"SR": "sr", "JS": "js"}   # ledger account → tiktok_auth.py connection label


def refresh_tiktok_views(posts):
    """Exact TikTok views for ledger rows, through each account's own connection
    (master/tiktok_auth.py). Accounts that aren't connected keep the CSV value."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    try:
        from tiktok_auth import video_stats
    except ImportError:
        return 0
    n, today = 0, date.today().isoformat()
    for acct, label in TT_ACCOUNTS.items():
        rows = [p for p in posts if p["account"] == acct and p["platform"].upper() == "TIKTOK"]
        if not rows:
            continue
        try:
            stats = video_stats(label, [p["url"] for p in rows])
        except SystemExit as e:
            print(f"  · TikTok {acct}: {e} — using CSV views")
            continue
        for p in rows:
            vid = re.search(r"(\d{15,25})", p["url"])
            st = stats.get(vid.group(1)) if vid else None
            if st and st.get("views") is not None:
                p.update({"views": str(st["views"]), "views_source": "api", "views_as_of": today})
                n += 1
        missing = [p["url"] for p in rows if not (re.search(r"(\d{15,25})", p["url"]) and stats.get(re.search(r"(\d{15,25})", p["url"]).group(1)))]
        if missing:
            print(f"  ⚠ TikTok {acct}: {len(missing)} video(s) not returned (deleted, private, or another account's)")
    return n


def write_posts(path, posts):
    cols = ["url", "account", "platform", "date", "title", "views", "views_source", "views_as_of", "notes"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows({k: p.get(k, "") for k in cols} for p in posts)


def social_for_period(posts, socials_path, start, end):
    s, e = start.isoformat(), end.isoformat()
    inp = [p for p in posts if s <= p["date"] <= e]
    sum_v = lambda acct, plat: sum(to_int(p["views"]) for p in inp if p["account"] == acct and p["platform"].upper() == plat)
    cnt = lambda acct, plat: sum(1 for p in inp if p["account"] == acct and p["platform"].upper() == plat)
    out = {
        "ig_views": sum_v("SR", "INSTAGRAM"), "ig_posts": cnt("SR", "INSTAGRAM"),
        "kj_ig_views": sum_v("KJ", "INSTAGRAM"), "kj_ig_posts": cnt("KJ", "INSTAGRAM"),
        "kj_x_views": None, "kj_x_posts": None, "audio_downloads": None,
    }
    # SR TikTok + X: every month the period touches (account totals; all posts watermarked)
    months = set(months_in(start, end))
    vals = {}
    for r in read_csv(socials_path):
        if r["period"].strip() in months:
            key = (r["platform"].strip().upper(), r["metric"].strip().upper())
            vals.setdefault(key, 0)
            vals[key] += to_int(r["value"])
    if cnt("SR", "TIKTOK"):          # watermarked videos listed → count only those
        out["tiktok_views"], out["tiktok_posts"] = sum_v("SR", "TIKTOK"), cnt("SR", "TIKTOK")
    else:                             # fallback: account totals
        out["tiktok_views"] = vals.get(("TIKTOK", "VIEWS"), 0)
        out["tiktok_posts"] = vals.get(("TIKTOK", "POSTS"), 0)
    out["x_imp"] = vals.get(("X", "IMPRESSIONS"), vals.get(("X", "VIEWS"), 0))
    top = sorted((p for p in inp if to_int(p["views"])), key=lambda p: -to_int(p["views"]))[:3]
    acct_lbl = {("SR", "INSTAGRAM"): "Instagram · @theschultzreport", ("SR", "TIKTOK"): "TikTok · @theschultzreport",
                ("KJ", "INSTAGRAM"): "Instagram · Schultz Report × Keyshawn"}
    out["_top_social"] = [{"rank": i + 1, "platform": acct_lbl.get((p["account"], p["platform"].upper()), p["platform"]),
                           "date": datetime.strptime(p["date"], "%Y-%m-%d").strftime("%b %d"),
                           "views": to_int(p["views"]), "title": p["title"] or p["url"], "url": p["url"]}
                          for i, p in enumerate(top)]
    return out


# ═════════════════════════════════════════════════════════════════
# MANUAL INPUTS
# ═════════════════════════════════════════════════════════════════
def prompt_manual(saved, row):
    d = saved or {}
    m = {}
    eps = sum(row[k] for k in EP_KEYS)
    eps_seg = sum(row[f"eps_{t}"] for t, _, _, has_seg in EP_TYPES if has_seg)
    print("\n" + "─" * 60 + "\nMANUAL FIELDS — this period's counts (Enter keeps [default])\n" + "─" * 60)
    print(f"\nSponsorship delivery ({eps} episodes, {eps_seg} with a sponsored segment):")
    for k, label, _, seg_only in SPONSOR_ITEMS:
        m[k] = prompt_int(label, d.get(k, eps_seg if seg_only else eps))
    print("\nAdded value:")
    for k, label, _ in ADDED_VALUE:
        if k in PENDING:
            print(f"  {label}: Pending")
            m[k] = None
        else:
            m[k] = prompt_int(label, d.get(k, 0))
    print("\nAudio:")
    m["audio_downloads"] = (None if "audio_downloads" in PENDING
                            else prompt_int("Podcast downloads (all platforms)", d.get("audio_downloads", 0)))
    print("\nMarquee moments delivered this period:")
    for k, label, _ in EVENTS:
        m[k] = prompt_int(label, d.get(k, 0))
    print("\nJordan Schultz — Fanatics-tagged posts" + (" (Sprout Social, counted):" if JORDAN_COUNTED
                                                        else " (reported, shown but not counted):"))
    for r in REPORTER:
        m[f"{r['key']}_posts"] = prompt_int(f"{r['name'].title()} — posts", d.get(f"{r['key']}_posts", 0))
        m[f"{r['key']}_views"] = prompt_int(f"{r['name'].title()} — {r['unit']}", d.get(f"{r['key']}_views", 0))
    return m


# ═════════════════════════════════════════════════════════════════
# HISTORY
# ═════════════════════════════════════════════════════════════════
def sum_history(rows):
    return {k: sum(to_int(r.get(k)) for r in rows) for k in HISTORY_FIELDS[2:]}


def write_history(path, row):
    """Saves the period, replacing any earlier row that overlaps it (e.g. a combined
    Aug 18 – Sep 30 report later rebuilt as separate August and September reports)."""
    s, e = row["period_start"], row["period_end"]
    rows = [r for r in read_csv(path) if r["period_end"] < s or r["period_start"] > e]
    rows.append({k: "" if row.get(k) is None else str(row.get(k, 0)) for k in HISTORY_FIELDS})
    rows.sort(key=lambda r: r["period_start"])
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        w.writeheader()
        w.writerows(rows)


# ═════════════════════════════════════════════════════════════════
# IMPRESSIONS
# ═════════════════════════════════════════════════════════════════
def counted_social(r):
    jordan = (to_int(r["js_x_views"]) + to_int(r["js_ig_views"]) + to_int(r["js_tt_views"])) if JORDAN_COUNTED else 0
    return (to_int(r["ig_views"]) + to_int(r["tiktok_views"]) + to_int(r["x_imp"])
            + to_int(r["kj_ig_views"]) + to_int(r["kj_x_views"]) + jordan)


def period_impressions(row, videos):
    """YouTube / Social / Audio impressions for ONE period. Full-episode views x4,
    clips & Shorts x2, podcast downloads x3, social views x1."""
    imp_eps = sum(v["views"] * episode_multiplier(v["ep_type"]) for v in videos if v["bucket"] == "full")
    imp_yt = imp_eps + (row["yt_clip_views"] + row["yt_short_views"]) * MULT_CLIPS_SHORTS
    return imp_yt, counted_social(row), to_int(row["audio_downloads"]) * MULT_AUDIO


# ═════════════════════════════════════════════════════════════════
# ASSEMBLE → dict for the renderer
# ═════════════════════════════════════════════════════════════════
def assemble(row, prior_rows, top_content, top_social, start, end, generated):
    prior = sum_history(prior_rows)
    cum = {k: prior.get(k, 0) + to_int(row.get(k, 0)) for k in HISTORY_FIELDS[2:]}
    # a field stays "Pending" until any period has a real value for it
    pending = {k for k in PENDING if row.get(k) is None and all((r.get(k) or "") == "" for r in prior_rows)}
    days_into = max(0, min((min(end, generated) - TERM_START).days + 1, TERM_DAYS))
    weeks = max(((min(end, generated) - POSTING_START).days + 1) / 7, 1)
    pct = lambda a, b: (a / b * 100) if b else 0

    show = lambda r: to_int(r["ig_views"]) + to_int(r["tiktok_views"]) + to_int(r["x_imp"])
    talent = lambda r: to_int(r["kj_ig_views"]) + to_int(r["kj_x_views"]) + (
        (to_int(r["js_x_views"]) + to_int(r["js_ig_views"]) + to_int(r["js_tt_views"])) if JORDAN_COUNTED else 0)
    vd = lambda r: to_int(r["yt_total_views"]) + to_int(r["audio_downloads"]) + show(r) + talent(r)
    total_imp = cum["impressions"]

    reporter = []
    for r in REPORTER:
        posts = cum[f"{r['key']}_posts"]
        reporter.append({**r, "tp_posts": row[f"{r['key']}_posts"], "cum_posts": posts,
                         "tp_views": row[f"{r['key']}_views"], "cum_views": cum[f"{r['key']}_views"],
                         "wk_avg": posts / weeks, "counted": JORDAN_COUNTED})

    eps_tp = sum(row[f"eps_{t}"] for t, *_ in EP_TYPES)
    eps_cum = sum(cum[f"eps_{t}"] for t, *_ in EP_TYPES)
    kj_posts = lambda r: to_int(r["kj_ig_posts"]) + to_int(r["kj_x_posts"])
    return {
        "start": start, "end": end, "generated": generated, "version": REPORT_VERSION,
        "term_start": TERM_START, "term_end": TERM_END, "term_days": TERM_DAYS,
        "days_into": days_into, "pct_elapsed": pct(days_into, TERM_DAYS), "weeks": weeks,
        "tp_vd": vd(row), "cum_vd": vd(cum),
        "goal": IMP_GOAL, "total_imp": total_imp, "pct_plan": pct(total_imp, IMP_GOAL),
        "pace": round(total_imp / days_into * TERM_DAYS) if days_into else 0,
        "pending": pending, "jordan_counted": JORDAN_COUNTED,
        "kpi": {   # contract KPI split: YouTube / Social / Audio (Social shown as two sources)
            "youtube": {"tp_views": row["yt_total_views"], "cum_views": cum["yt_total_views"],
                        "tp_imp": row["imp_youtube"], "cum_imp": cum["imp_youtube"]},
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
                "types": [{"key": t, "label": lbl, "plan": plan, "seg": seg,
                           "tp": row[f"eps_{t}"], "cum": cum[f"eps_{t}"]}
                          for t, lbl, plan, seg in EP_TYPES]},
        "sponsor": [{"label": lbl, "target": t, "tp": row[k], "cum": cum[k]} for k, lbl, t, _ in SPONSOR_ITEMS],
        "content": [{"label": "YouTube Clips (branded)", "target": CLIPS_TARGET,
                     "tp": row["yt_clip_count_new"], "cum": cum["yt_clip_count_new"]},
                    {"label": "YouTube Shorts (branded)", "target": SHORTS_TARGET,
                     "tp": row["yt_short_count_new"], "cum": cum["yt_short_count_new"]}]
                   + [{"label": lbl, "target": t, "tp": row[k], "cum": cum[k], "pending": k in pending}
                      for k, lbl, t in ADDED_VALUE],
        "reporter": reporter,
        "keyshawn": {"tp_posts": kj_posts(row), "cum_posts": kj_posts(cum), "target": KEYSHAWN["target"],
                     "tp_views": talent(row), "cum_views": talent(cum), "min_wk": KEYSHAWN["min_wk"],
                     "x_pending": "kj_x_views" in pending},
        "events": [{"label": lbl, "target": t, "tp": row[k], "cum": cum[k]} for k, lbl, t in EVENTS],
        "top_full": top_content.get("full", []), "top_clip": top_content.get("clip", []),
        "top_short": top_content.get("short", []), "top_social": top_social,
        "mults": {"episode": MULT_EPISODE, "audio": MULT_AUDIO, "clips": MULT_CLIPS_SHORTS},
    }


# ═════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════
from fanatics_report_template_sr import render_html


def main():
    ap = argparse.ArgumentParser(description="The Schultz Report × Fanatics — delivery report builder")
    ap.add_argument("--start", help="Period start YYYY-MM-DD (default: last full month)")
    ap.add_argument("--end", help="Period end YYYY-MM-DD")
    ap.add_argument("--no-write", action="store_true",
                    help="Don't save the period to fanatics_history_sr.csv or refreshed views to fanatics_posts_sr.csv")
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = args.data_dir or os.path.join(script_dir, "data_sr")
    out_dir = os.path.join(data_dir, "reports", "fanatics")
    os.makedirs(out_dir, exist_ok=True)
    hist_path = os.path.join(data_dir, "fanatics_history_sr.csv")
    posts_path = os.path.join(data_dir, "fanatics_posts_sr.csv")
    eps_path = os.path.join(data_dir, "fanatics_episodes_sr.csv")

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
        print("Loaded saved inputs for this period → press Enter to keep them")

    # YouTube
    episodes = {r["video_id"]: r for r in read_csv(eps_path)}
    valid = {t for t, *_ in EP_TYPES} | {"special"}
    bad = [r for r in episodes.values() if r["type"] not in valid]
    if bad:
        raise SystemExit(f"⚠ fanatics_episodes_sr.csv: unknown type for {', '.join(r['video_id'] for r in bad)} "
                         f"(use {', '.join(sorted(valid))})")
    creds = authenticate_yt()
    from googleapiclient.discovery import build as build_api
    youtube = build_api("youtube", "v3", credentials=creds)
    yta = build_api("youtubeAnalytics", "v2", credentials=creds)
    print("\nPulling YouTube …")
    vids = pull_videos(youtube, yta, start, end, episodes)
    untagged = [v for v in vids if v["bucket"] == "untagged"]
    if untagged:
        print("\n⚠ Videos over 30 min that aren't in fanatics_episodes_sr.csv — tag them (or mark as a clip) first:")
        for v in untagged:
            print(f"    {v['id']}  {v['published']}  {hms(v['secs'])}  {v['title'][:60]}")
        raise SystemExit(1)
    row = yt_period(vids)
    for v in sorted((v for v in vids if v["bucket"] == "full"), key=lambda x: x["published"]):
        print(f"  {v['published']}  {v['ep_type']:<9} {episode_multiplier(v['ep_type'])}x  {v['views']:>8,}  {v['title'][:50]}")
    print(f"  {row['yt_full_count_new']} episodes · {row['yt_clip_count_new']} clips · {row['yt_short_count_new']} Shorts")

    # Social (watermarked post ledger + SR TikTok/X totals)
    print("\nSocial …")
    posts = read_csv(posts_path)
    n = refresh_post_views(posts, start.isoformat())
    n += refresh_tiktok_views(posts)
    print(f"  {n} post view(s) refreshed (Instagram + TikTok) · {len(posts)} posts in the ledger")
    soc = social_for_period(posts, os.path.join(data_dir, "socials_sr.csv"), start, end)
    top_social = soc.pop("_top_social")
    row.update(soc)

    # Manual
    manual = prompt_manual(saved, row)
    row.update(manual)
    json.dump(manual, open(inputs_path, "w", encoding="utf-8"), indent=2)

    imp_yt, imp_soc, imp_aud = period_impressions(row, vids)
    row.update({"period_start": start.isoformat(), "period_end": end.isoformat(),
                "imp_youtube": imp_yt, "imp_social": imp_soc, "imp_audio": imp_aud,
                "impressions": imp_yt + imp_soc + imp_aud})

    def top3(bucket):
        vs = sorted([v for v in vids if v["bucket"] == bucket], key=lambda x: -x["views"])[:3]
        return [{"rank": i + 1, "views": v["views"], "title": v["title"], "thumb": v["thumb"], "url": v["url"],
                 "date": datetime.strptime(v["published"], "%Y-%m-%d").strftime("%b %d"),
                 "dur": hms(v["secs"]) if bucket == "full" else ""} for i, v in enumerate(vs)]
    top_content = {b: top3(b) for b in ("full", "clip", "short")}

    prior_rows = [r for r in read_csv(hist_path) if r["period_end"] < start.isoformat()]
    data = assemble(row, prior_rows, top_content, top_social, start, end, date.today())

    html = render_html(data)
    out_path = os.path.join(out_dir, f"Schultz_Report_Fanatics_{start:%m%d}_{end:%m%d}_{end:%y}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    k = data["kpi"]
    print(f"\n✓ Report: {out_path}")
    print(f"  Impressions this period {fmt(row['impressions'])}  (YouTube {fmt(imp_yt)} · Social {fmt(imp_soc)}"
          f" [talent {fmt(k['social_talent']['tp_imp'])} / SR show {fmt(k['social_show']['tp_imp'])}]"
          f" · Audio {'Pending' if 'audio_downloads' in data['pending'] else fmt(imp_aud)})")
    print(f"  Cumulative {fmt(data['total_imp'])}  ·  {data['pct_plan']:.2f}% of {fmt(IMP_GOAL)}"
          f"  ·  pace {fmt(data['pace'])}")
    if not JORDAN_COUNTED:
        js = sum(to_int(row[f"{r['key']}_views"]) for r in REPORTER)
        print(f"  Jordan (reported, not counted): {fmt(js)}")
    if not args.no_write:
        write_history(hist_path, row)
        write_posts(posts_path, posts)
        print(f"  ↳ saved period to {os.path.basename(hist_path)} · refreshed views to {os.path.basename(posts_path)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
