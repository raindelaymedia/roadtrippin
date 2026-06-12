"""
Road Trippin' × Fanatics Sportsbook — Monthly Delivery Report Builder
=====================================================================
Generates the monthly Fanatics delivery report as a print-ready HTML file
(open in a browser → Print → Save as PDF).

Two halves:
  1. DATA LAYER  — pulls everything it can automatically:
       • YouTube  : per-video views/durations/thumbnails over the period
                    (YT Analytics + Data API, same auth as build_tracker2.py)
       • Megaphone: Total Delivery summed from megaphone_per_episode.csv
       • Socials  : IG / TikTok / X from socials.csv (calendar-month rows)
       • Cumulative totals from data/fanatics_history.csv
     ...then PROMPTS for the handful it can't (episode classification,
     integrations, talent posts, top social posts) — same feel as the
     revenue tracker.
  2. RENDERER    — lays the assembled data into the 4-page branded report.

Usage:
    python build_fanatics_report.py                       # current calendar month
    python build_fanatics_report.py --start 2026-06-01 --end 2026-06-30
    python build_fanatics_report.py --recreate            # rebuild Report 4 offline (no APIs)
    python build_fanatics_report.py --no-write            # don't append to history

Requirements (live runs only):
    pip install google-auth google-auth-oauthlib google-api-python-client python-dateutil
"""

import argparse
import csv
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

# ─────────────────────────────────────────────────────────────────
# FANATICS CONTRACT CONSTANTS  (hardcoded per the deal)
# ─────────────────────────────────────────────────────────────────
TERM_START            = date(2026, 2, 13)
TERM_END              = date(2026, 9, 13)
TERM_DAYS             = 212
TERM_CUMULATIVE_START = date(2026, 2, 17)   # content counting starts 2/17

EP_TARGET             = 94
GROUP_EP_TARGET       = 56
SOLO_PERK_TARGET      = 24
SOLO_CHANNING_TARGET  = 14
IMP_GOAL_LOW          = 47_000_000
IMP_GOAL_HIGH         = 50_000_000
SHOUTOUT_TARGET       = 94
SEGMENT_TARGET        = 52
AD_READ_TARGET        = 94
INTEGRATIONS_TARGET   = SHOUTOUT_TARGET + SEGMENT_TARGET + AD_READ_TARGET   # 240
TALENT_POSTS_TARGET   = 182

MULT_GROUP            = 6     # impression multiplier — full group episode
MULT_SOLO             = 5     # impression multiplier — full solo episode
MULT_CLIPS_SHORTS     = 2     # impression multiplier — clips & shorts

# Duration boundaries (Report 4+):  shorts ≤3:00, clips 3:01–30:00, full >30:00
SHORTS_MAX  = 180     # seconds
CLIPS_MAX   = 1800    # seconds

GOLD = "#C9A84C"

TALENT = [
    {"key": "perk",     "name": "KENDRICK PERKINS",  "handle": "@KendrickPerkins",  "min_wk": 2},
    {"key": "channing", "name": "CHANNING FRYE",      "handle": "@ChanningFrye",     "min_wk": 2},
    {"key": "rj",       "name": "RICHARD JEFFERSON",  "handle": "@RichardJefferson", "min_wk": 2},
    {"key": "allie",    "name": "ALLIE CLIFTON",      "handle": "@AllieClifton",     "min_wk": 1},
]

HISTORY_FIELDS = [
    "period_start", "period_end",
    "yt_total_views", "yt_total_count_new",
    "yt_full_views", "yt_full_count_new",
    "yt_clip_views", "yt_clip_count_new",
    "yt_short_views", "yt_short_count_new",
    "mega_views", "ig_views", "tiktok_views", "tiktok_count_new", "x_imp",
    "group_eps", "solo_perk", "solo_chan",
    "shoutouts", "segments", "ad_reads",
    "perk_posts", "channing_posts", "rj_posts", "allie_posts",
    "impressions",
]


# ═════════════════════════════════════════════════════════════════
# SMALL HELPERS
# ═════════════════════════════════════════════════════════════════
def fmt(n):
    """1234567 -> '1,234,567'. Passes through non-numbers."""
    try:
        return f"{int(round(float(n))):,}"
    except (ValueError, TypeError):
        return str(n)


def parse_iso_duration(dur):
    """ISO-8601 'PT1H2M3S' -> seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def hms(seconds):
    """seconds -> '1:11:44' or '12:30'."""
    h, rem = divmod(int(seconds), 3600)
    mi, s = divmod(rem, 60)
    return f"{h}:{mi:02d}:{s:02d}" if h else f"{mi}:{s:02d}"


def days_inclusive(d0, d1):
    return (d1 - d0).days + 1


def pct(part, whole):
    return (part / whole * 100) if whole else 0.0


def prompt_int(label, default=None):
    sfx = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"  {label}{sfx}: ").strip().replace(",", "")
        if not raw and default is not None:
            return default
        try:
            return int(raw)
        except ValueError:
            print("    ↳ enter a whole number.")


# ═════════════════════════════════════════════════════════════════
# DATA SOURCES (LIVE)
# ═════════════════════════════════════════════════════════════════
def authenticate_yt():
    """OAuth Playground refresh-token flow — identical to build_tracker2.py."""
    from config import (YT_CLIENT_ID as CLIENT_ID, YT_CLIENT_SECRET as CLIENT_SECRET,
                        YT_REFRESH_TOKEN as REFRESH_TOKEN)
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials(
        token=None, refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly",
                "https://www.googleapis.com/auth/youtube.readonly"])
    creds.refresh(Request())
    return creds


def pull_period_videos(youtube, start, end):
    """Every video PUBLISHED in [start, end], classified by duration.
    Views are lifetime views as of now (matches the Top-Content ranking and
    the 'N videos / N new this period' counts in the report).
    Returns list of dicts: id,title,published(date),secs,views,thumb,url,bucket."""
    from config import YT_CHANNEL_ID as CHANNEL_ID
    ch = youtube.channels().list(part="contentDetails", id=CHANNEL_ID).execute()
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    start_s, end_s = start.isoformat(), end.isoformat()
    out, seen, page = [], set(), None
    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads,
            maxResults=50, pageToken=page).execute()
        ids = [it["contentDetails"]["videoId"] for it in resp["items"]]
        det = youtube.videos().list(
            part="contentDetails,snippet,statistics", id=",".join(ids)).execute()
        oldest_on_page = None
        for v in det["items"]:
            vid = v["id"]
            if vid in seen:
                continue
            seen.add(vid)
            pub = v["snippet"]["publishedAt"][:10]
            oldest_on_page = pub if oldest_on_page is None else min(oldest_on_page, pub)
            if pub < start_s or pub > end_s:
                continue
            secs = parse_iso_duration(v["contentDetails"]["duration"])
            bucket = "short" if secs <= SHORTS_MAX else "clip" if secs <= CLIPS_MAX else "full"
            out.append({
                "id": vid, "title": v["snippet"]["title"], "published": pub,
                "secs": secs, "views": int(v["statistics"].get("viewCount", 0)),
                "thumb": f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
                "url": f"https://youtu.be/{vid}", "bucket": bucket,
            })
        page = resp.get("nextPageToken")
        # Stop paging once we're safely older than the window (uploads are newest-first).
        if not page or (oldest_on_page and oldest_on_page < start_s):
            break
    return out


def yt_window_totals(youtube, start, end):
    """Sum lifetime views + counts since TERM_CUMULATIVE_START for cumulative,
    and within [start,end] for this-period. Returns (this_period, cumulative)
    dicts each with views & counts per bucket + totals."""
    cum_videos = pull_period_videos(youtube, TERM_CUMULATIVE_START, end)

    def agg(vids):
        d = {b: {"views": 0, "count": 0} for b in ("full", "clip", "short")}
        for v in vids:
            d[v["bucket"]]["views"] += v["views"]
            d[v["bucket"]]["count"] += 1
        d["total_views"] = sum(d[b]["views"] for b in ("full", "clip", "short"))
        d["total_count"] = sum(d[b]["count"] for b in ("full", "clip", "short"))
        return d

    this_vids = [v for v in cum_videos if start.isoformat() <= v["published"] <= end.isoformat()]
    return agg(this_vids), agg(cum_videos), cum_videos


def megaphone_total(csv_path, start, end):
    """Sum TOTAL DELIVERY for episodes PUBLISHED in [start, end]."""
    if not os.path.exists(csv_path):
        return None
    total = 0
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            pub_raw = (r.get("PUBLISHED") or "").strip()
            if not pub_raw:
                continue
            try:
                pub = datetime.strptime(pub_raw[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if start <= pub <= end:
                try:
                    total += int(float(r.get("TOTAL DELIVERY", 0) or 0))
                except ValueError:
                    pass
    return total


def socials_for_month(csv_path, ym):
    """Return {'ig':views,'tiktok':views,'tiktok_count':n,'x':impressions} for a
    YYYY-MM month from socials.csv, or None for any field not present."""
    out = {"ig": None, "tiktok": None, "tiktok_count": None, "x": None}
    if not os.path.exists(csv_path):
        return out
    with open(csv_path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["period"].strip() != ym:
                continue
            plat, metric = r["platform"].strip().upper(), r["metric"].strip().upper()
            try:
                val = int(float(r["value"]))
            except (ValueError, TypeError):
                continue
            if plat in ("INSTAGRAM", "IG") and metric in ("VIEWS", "REACH"):
                out["ig"] = val
            elif plat == "TIKTOK" and metric == "VIEWS":
                out["tiktok"] = val
            elif plat == "TIKTOK" and metric == "POSTS":
                out["tiktok_count"] = val
            elif plat in ("X", "TWITTER") and metric in ("IMPRESSIONS", "VIEWS"):
                out["x"] = val
    return out


# ═════════════════════════════════════════════════════════════════
# HISTORY (cumulative-from-prior-periods)
# ═════════════════════════════════════════════════════════════════
def load_history(csv_path):
    if not os.path.exists(csv_path):
        return []
    with open(csv_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def history_cumulative(rows):
    """Sum the prior-period rows into a cumulative dict. Full views are DERIVED
    as total-clip-short (the stored full column does not reconcile; total/clip/
    short do). Impressions come straight from the stored per-period column."""
    def s(col):
        return sum(int(r[col]) for r in rows) if rows else 0
    cum_total = s("yt_total_views")
    cum_clip = s("yt_clip_views")
    cum_short = s("yt_short_views")
    return {
        "yt_total_views": cum_total,
        "yt_full_views": cum_total - cum_clip - cum_short,
        "yt_clip_views": cum_clip,
        "yt_short_views": cum_short,
        "yt_total_count": s("yt_total_count_new"),
        "yt_full_count": s("yt_full_count_new"),
        "yt_clip_count": s("yt_clip_count_new"),
        "yt_short_count": s("yt_short_count_new"),
        "mega_views": s("mega_views"),
        "ig_views": s("ig_views"),
        "tiktok_views": s("tiktok_views"),
        "tiktok_count": s("tiktok_count_new"),
        "x_imp": s("x_imp"),
        "group_eps": s("group_eps"), "solo_perk": s("solo_perk"), "solo_chan": s("solo_chan"),
        "shoutouts": s("shoutouts"), "segments": s("segments"), "ad_reads": s("ad_reads"),
        "perk_posts": s("perk_posts"), "channing_posts": s("channing_posts"),
        "rj_posts": s("rj_posts"), "allie_posts": s("allie_posts"),
        "impressions": s("impressions"),
    }


def period_impressions(full_views, clip_views, short_views, group_eps, solo_eps,
                       other_views=0, group_full_views=None, solo_full_views=None):
    """Impressions contributed by ONE period = full-ep (6x/5x) + clips/shorts (2x)
    + other platforms (1x: Megaphone, IG, TikTok, X).
    full_ep_imp uses the actual group/solo full-episode view split when provided
    (exact); otherwise blends 6x/5x by episode-count ratio (≈, used when only
    aggregate full views are known)."""
    if group_full_views is not None and solo_full_views is not None:
        full_ep_imp = group_full_views * MULT_GROUP + solo_full_views * MULT_SOLO
    else:
        tot = group_eps + solo_eps
        blend = ((group_eps * MULT_GROUP + solo_eps * MULT_SOLO) / tot) if tot else MULT_GROUP
        full_ep_imp = full_views * blend
    clips_short_imp = (clip_views + short_views) * MULT_CLIPS_SHORTS
    return round(full_ep_imp + clips_short_imp + other_views)


# ═════════════════════════════════════════════════════════════════
# MANUAL PROMPTS  (the handful the APIs can't give us)
# ═════════════════════════════════════════════════════════════════
def prompt_manual(defaults=None):
    d = defaults or {}
    print("\n" + "─" * 55)
    print("MANUAL FIELDS — enter this period's counts")
    print("─" * 55)
    print("\nEpisode classification (this period):")
    group = prompt_int("Group episodes", d.get("group_eps"))
    perk = prompt_int("Solo — Kendrick Perkins", d.get("solo_perk"))
    chan = prompt_int("Solo — Channing Frye", d.get("solo_chan"))
    print("\nIntegrations (this period):")
    shout = prompt_int("Top-of-show shoutouts", d.get("shoutouts"))
    seg = prompt_int("Sponsored segments", d.get("segments"))
    ad = prompt_int("Host-read ad reads", d.get("ad_reads"))
    print("\nTalent posts (this period):")
    pk = prompt_int("Perk posts", d.get("perk_posts"))
    cf = prompt_int("Channing posts", d.get("channing_posts"))
    rj = prompt_int("RJ posts", d.get("rj_posts"))
    al = prompt_int("Allie posts", d.get("allie_posts"))

    socials = []
    print("\nTop 3 social posts (blank title to stop):")
    for i in range(1, 4):
        title = input(f"  #{i} title: ").strip()
        if not title:
            break
        plat = input(f"  #{i} platform (Instagram/TikTok/X): ").strip() or "Instagram"
        pdate = input(f"  #{i} date (e.g. Apr 26): ").strip()
        views = prompt_int(f"#{i} views")
        socials.append({"rank": i, "platform": plat, "date": pdate,
                        "views": views, "title": title})

    return {
        "group_eps": group, "solo_perk": perk, "solo_chan": chan,
        "shoutouts": shout, "segments": seg, "ad_reads": ad,
        "perk_posts": pk, "channing_posts": cf, "rj_posts": rj, "allie_posts": al,
        "top_social": socials,
    }


# ═════════════════════════════════════════════════════════════════
# ASSEMBLE  → a single report_data dict the renderer consumes
# ═════════════════════════════════════════════════════════════════
def assemble(period_raw, manual, cum_prior, top_content, start, end, generated,
             this_imp=None, cum_from_history=False):
    """period_raw: this-period auto values. cum_prior: summed prior periods.
    Builds the full dict. Normally cumulative = prior + this period. When
    cum_from_history is True (full-month POC), cumulative is taken straight from
    cum_prior (history already runs through `end`) and the this-period columns
    are shown for display only — so a wider display window can't double-count."""
    ap = 0 if cum_from_history else 1     # add this period into cumulative?

    # ---- cumulative ----
    def c(key, pk=None):
        return cum_prior.get(key, 0) + ap * period_raw.get(pk or key, 0)

    cum_full = cum_prior["yt_full_views"] + ap * period_raw["yt_full_views"]
    cum_clip = cum_prior["yt_clip_views"] + ap * period_raw["yt_clip_views"]
    cum_short = cum_prior["yt_short_views"] + ap * period_raw["yt_short_views"]
    cum_total = cum_full + cum_clip + cum_short
    cum_mega = c("mega_views"); cum_ig = c("ig_views")
    cum_tt = c("tiktok_views"); cum_x = c("x_imp")

    # episodes / integrations / talent cumulative
    cum_group = cum_prior["group_eps"] + ap * manual["group_eps"]
    cum_perk = cum_prior["solo_perk"] + ap * manual["solo_perk"]
    cum_chan = cum_prior["solo_chan"] + ap * manual["solo_chan"]
    cum_eps = cum_group + cum_perk + cum_chan
    tp_eps = manual["group_eps"] + manual["solo_perk"] + manual["solo_chan"]

    cum_shout = cum_prior["shoutouts"] + ap * manual["shoutouts"]
    cum_seg = cum_prior["segments"] + ap * manual["segments"]
    cum_ad = cum_prior["ad_reads"] + ap * manual["ad_reads"]
    cum_integrations = cum_shout + cum_seg + cum_ad
    tp_integrations = manual["shoutouts"] + manual["segments"] + manual["ad_reads"]

    talent_keys = ["perk_posts", "channing_posts", "rj_posts", "allie_posts"]
    tp_talent = {k: manual[k] for k in talent_keys}
    cum_talent = {k: cum_prior[k] + ap * manual[k] for k in talent_keys}
    tp_talent_total = sum(tp_talent.values())
    cum_talent_total = sum(cum_talent.values())

    # ---- impressions ----
    if this_imp is None:
        other_tp = (period_raw["mega_views"] + period_raw["ig_views"]
                    + period_raw["tiktok_views"] + period_raw["x_imp"])
        this_imp = period_impressions(
            period_raw["yt_full_views"], period_raw["yt_clip_views"], period_raw["yt_short_views"],
            manual["group_eps"], manual["solo_perk"] + manual["solo_chan"],
            other_views=other_tp)
    total_imp = cum_prior["impressions"] + ap * this_imp

    clips_short_imp = (cum_clip + cum_short) * MULT_CLIPS_SHORTS
    other_imp = cum_mega + cum_ig + cum_tt + cum_x
    full_ep_imp = total_imp - clips_short_imp - other_imp   # residual → matches headline exactly

    # ---- header metrics ----
    days_into = days_inclusive(TERM_START, generated) if generated >= TERM_START else 0
    pct_elapsed = pct(days_into, TERM_DAYS)
    tp_vd = (period_raw["yt_total_views"] + period_raw["mega_views"] + period_raw["ig_views"]
             + period_raw["tiktok_views"] + period_raw["x_imp"])
    cum_vd = cum_total + cum_mega + cum_ig + cum_tt + cum_x
    pace = round(total_imp / days_into * TERM_DAYS) if days_into else 0
    pct_plan = pct(total_imp, IMP_GOAL_LOW)

    talent_cards = []
    weeks_elapsed = days_into // 7 or 1     # whole weeks, matches the PDF's per-wk avg
    for t in TALENT:
        cumv = cum_talent[f"{t['key']}_posts"]
        wk_avg = cumv // weeks_elapsed
        talent_cards.append({**t, "tp": tp_talent[f"{t['key']}_posts"], "cum": cumv,
                             "wk_avg": wk_avg})

    return {
        "start": start, "end": end, "generated": generated,
        "days_into": days_into, "pct_elapsed": pct_elapsed,
        "tp_vd": tp_vd, "cum_vd": cum_vd,
        "total_imp": total_imp, "pct_plan": pct_plan, "pace": pace,
        "platforms": {
            "yt_total": {"tp": period_raw["yt_total_views"], "cum": cum_total,
                         "ct_total": cum_prior["yt_total_count"] + period_raw["yt_total_count"],
                         "ct_new": period_raw["yt_total_count"]},
            "yt_full": {"tp": period_raw["yt_full_views"], "cum": cum_full,
                        "ct_total": cum_prior["yt_full_count"] + period_raw["yt_full_count"],
                        "ct_new": period_raw["yt_full_count"]},
            "yt_clip": {"tp": period_raw["yt_clip_views"], "cum": cum_clip,
                        "ct_total": cum_prior["yt_clip_count"] + period_raw["yt_clip_count"],
                        "ct_new": period_raw["yt_clip_count"]},
            "yt_short": {"tp": period_raw["yt_short_views"], "cum": cum_short,
                         "ct_total": cum_prior["yt_short_count"] + period_raw["yt_short_count"],
                         "ct_new": period_raw["yt_short_count"]},
            "mega": {"tp": period_raw["mega_views"], "cum": cum_mega},
            "ig": {"tp": period_raw["ig_views"], "cum": cum_ig},
            "tiktok": {"tp": period_raw["tiktok_views"], "cum": cum_tt,
                       "vids_tp": period_raw["tiktok_count"],
                       "vids_total": cum_prior["tiktok_count"] + period_raw["tiktok_count"]},
            "x": {"tp": period_raw["x_imp"], "cum": cum_x},
        },
        "eps": {"tp": tp_eps, "cum": cum_eps,
                "group": cum_group, "solo_perk": cum_perk, "solo_chan": cum_chan},
        "integrations": {"tp": tp_integrations, "cum": cum_integrations,
                         "shoutouts": cum_shout, "segments": cum_seg, "ad_reads": cum_ad},
        "talent": talent_cards,
        "talent_tp_total": tp_talent_total, "talent_cum_total": cum_talent_total,
        "top_full": top_content.get("full", []),
        "top_clip": top_content.get("clip", []),
        "top_short": top_content.get("short", []),
        "top_social": manual.get("top_social", []),
        "imp_full": full_ep_imp, "imp_clips_short": clips_short_imp, "imp_other": other_imp,
        "cum_full_views": cum_full, "cum_clips_short_views": cum_clip + cum_short,
        # values needed to append a history row:
        "_this_imp": this_imp,
        "_period_raw": period_raw, "_manual": manual,
    }


# ═════════════════════════════════════════════════════════════════
# HTML RENDER  (imported from fanatics_report_template)
# ═════════════════════════════════════════════════════════════════
from fanatics_report_template import render_html


# ═════════════════════════════════════════════════════════════════
# HISTORY APPEND
# ═════════════════════════════════════════════════════════════════
def append_history(csv_path, data):
    pr, mn = data["_period_raw"], data["_manual"]
    row = {
        "period_start": data["start"].isoformat(), "period_end": data["end"].isoformat(),
        "yt_total_views": pr["yt_total_views"], "yt_total_count_new": pr["yt_total_count"],
        "yt_full_views": pr["yt_full_views"], "yt_full_count_new": pr["yt_full_count"],
        "yt_clip_views": pr["yt_clip_views"], "yt_clip_count_new": pr["yt_clip_count"],
        "yt_short_views": pr["yt_short_views"], "yt_short_count_new": pr["yt_short_count"],
        "mega_views": pr["mega_views"], "ig_views": pr["ig_views"],
        "tiktok_views": pr["tiktok_views"], "tiktok_count_new": pr["tiktok_count"],
        "x_imp": pr["x_imp"],
        "group_eps": mn["group_eps"], "solo_perk": mn["solo_perk"], "solo_chan": mn["solo_chan"],
        "shoutouts": mn["shoutouts"], "segments": mn["segments"], "ad_reads": mn["ad_reads"],
        "perk_posts": mn["perk_posts"], "channing_posts": mn["channing_posts"],
        "rj_posts": mn["rj_posts"], "allie_posts": mn["allie_posts"],
        "impressions": data["_this_imp"],
    }
    exists = os.path.exists(csv_path)
    rows = load_history(csv_path) if exists else []
    rows = [r for r in rows if not (r["period_start"] == row["period_start"]
                                     and r["period_end"] == row["period_end"])]
    rows.append({k: str(row[k]) for k in HISTORY_FIELDS})
    rows.sort(key=lambda r: r["period_start"])
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        w.writeheader()
        w.writerows(rows)


# ═════════════════════════════════════════════════════════════════
# RECREATE MODE  (offline rebuild of Report 4 — no APIs needed)
# ═════════════════════════════════════════════════════════════════
def recreate_report4(data_dir):
    """Rebuild the Apr 13–May 10 report straight from history + a fixture of the
    manual/top-content values transcribed from the published PDF."""
    rows = load_history(os.path.join(data_dir, "fanatics_history.csv"))
    this = rows[-1]                       # 2026-04-13 … 2026-05-10
    prior = history_cumulative(rows[:-1])  # the three earlier periods

    ti = lambda k: int(this[k])
    full_v = ti("yt_total_views") - ti("yt_clip_views") - ti("yt_short_views")  # derived
    period_raw = {
        "yt_total_views": ti("yt_total_views"), "yt_total_count": ti("yt_total_count_new"),
        "yt_full_views": full_v, "yt_full_count": ti("yt_full_count_new"),
        "yt_clip_views": ti("yt_clip_views"), "yt_clip_count": ti("yt_clip_count_new"),
        "yt_short_views": ti("yt_short_views"), "yt_short_count": ti("yt_short_count_new"),
        "mega_views": ti("mega_views"), "ig_views": ti("ig_views"),
        "tiktok_views": ti("tiktok_views"), "tiktok_count": ti("tiktok_count_new"),
        "x_imp": ti("x_imp"),
    }
    # Counts shown on the PDF (videos in each bucket cumulatively) — the count_new
    # columns drift because the duration boundary changed mid-term, so the report's
    # published counts are used as the fixture.
    period_raw["yt_total_count"] = 122
    period_raw["yt_full_count"] = 9
    period_raw["yt_clip_count"] = 45
    period_raw["yt_short_count"] = 68

    manual = {
        "group_eps": ti("group_eps"), "solo_perk": ti("solo_perk"), "solo_chan": ti("solo_chan"),
        "shoutouts": ti("shoutouts"), "segments": ti("segments"), "ad_reads": ti("ad_reads"),
        "perk_posts": ti("perk_posts"), "channing_posts": ti("channing_posts"),
        "rj_posts": ti("rj_posts"), "allie_posts": ti("allie_posts"),
        "top_social": [
            {"rank": 1, "platform": "Instagram", "date": "Apr 26", "views": 513741,
             "title": "The Road Trippin' Mailbag is officially OPEN. We want your hottest "
                      "takes and deepest questions on Playoff Point Guards"},
            {"rank": 2, "platform": "Instagram", "date": "May 4", "views": 479829,
             "title": "\u201cShoes all muddy on your coffee table.\u201d Perk & RJ call out "
                      "Jaylen Brown — Celtics lacked adjustments when it mattered most"},
            {"rank": 3, "platform": "X", "date": "May 4", "views": 353875,
             "title": "You can't talk Kobe without talking mentality. The IQ and that relentless "
                      "Mamba Mentality — the crew dives deep into what made the Bean different"},
        ],
    }
    top_content = {
        "full": [
            {"rank": 1, "views": 28863, "date": "Apr 22", "dur": "1:11:44",
             "title": "LeBron And Ant Just STUNNED Houston & Denver + CJ the VILLAIN??",
             "thumb": "https://i.ytimg.com/vi/placeholder1/maxresdefault.jpg", "url": "#"},
            {"rank": 2, "views": 25873, "date": "Apr 16", "dur": "1:38:16",
             "title": "Luka RETURNS! Draymond DEFINES This Era & PERK COOKS Paolo!",
             "thumb": "https://i.ytimg.com/vi/placeholder2/maxresdefault.jpg", "url": "#"},
            {"rank": 3, "views": 24380, "date": "Apr 20", "dur": "1:35:57",
             "title": "Perk ADMITS He Was Wrong, KD NO SHOW & Tatum LOOKS Elite",
             "thumb": "https://i.ytimg.com/vi/placeholder3/maxresdefault.jpg", "url": "#"},
        ],
        "clip": [
            {"rank": 1, "views": 99628, "date": "Apr 22", "dur": "",
             "title": "LeBron Just Broke the Trap That Stopped Brunson, Murray & KD",
             "thumb": "https://i.ytimg.com/vi/placeholder4/maxresdefault.jpg", "url": "#"},
            {"rank": 2, "views": 96580, "date": "Apr 14", "dur": "",
             "title": "Perk Ran Into Ja Morant's Dad After Calling Him Out: \"I Don't Give Two F*s\"",
             "thumb": "https://i.ytimg.com/vi/placeholder5/maxresdefault.jpg", "url": "#"},
            {"rank": 3, "views": 64661, "date": "May 7", "dur": "",
             "title": "MPJ Reveals What REALLY Happened with Cam Thomas in Brooklyn",
             "thumb": "https://i.ytimg.com/vi/9LFMqUAyB_U/maxresdefault.jpg", "url": "#"},
        ],
        "short": [
            {"rank": 1, "views": 359915, "date": "Apr 15", "dur": "",
             "title": "Ja Morant OUT THE LEAGUE!? Kendrick Perkins Says It's Possible",
             "thumb": "https://i.ytimg.com/vi/placeholder6/maxresdefault.jpg", "url": "#"},
            {"rank": 2, "views": 184451, "date": "Apr 15", "dur": "",
             "title": "Richard Jefferson DID WHAT!?",
             "thumb": "https://i.ytimg.com/vi/placeholder7/maxresdefault.jpg", "url": "#"},
            {"rank": 3, "views": 118943, "date": "May 2", "dur": "",
             "title": "Lakers STEP UP To Defeat Rockets… OKC Next?",
             "thumb": "https://i.ytimg.com/vi/m51RPlzYGnQ/maxresdefault.jpg", "url": "#"},
        ],
    }
    start = datetime.strptime(this["period_start"], "%Y-%m-%d").date()
    end = datetime.strptime(this["period_end"], "%Y-%m-%d").date()
    # The bootstrap's per-period talent columns carry ~11 posts of manual-recount
    # noise vs the report's published per-talent cumulatives (Perk 140, Channing
    # 123, RJ 45, Allie 31 = 339). Reconcile the prior totals to those published
    # figures so the recreation is exact; live runs just sum prior + this period.
    pdf_cum = {"perk_posts": 140, "channing_posts": 123, "rj_posts": 45, "allie_posts": 31}
    for k, v in pdf_cum.items():
        prior[k] = v - int(this[k])     # prior = published cumulative − this period
    # Use the stored, published per-period impression value so the recreation is
    # exact (live runs compute it from the formula instead).
    return assemble(period_raw, manual, prior, top_content, start, end, date(2026, 5, 11),
                    this_imp=int(this["impressions"]))


# ═════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Road Trippin' × Fanatics report builder")
    ap.add_argument("--start", help="Period start YYYY-MM-DD")
    ap.add_argument("--end", help="Period end YYYY-MM-DD")
    ap.add_argument("--recreate", action="store_true", help="Rebuild Report 4 offline (no APIs)")
    ap.add_argument("--full-month", action="store_true",
                    help="Display a full-month this-period window while taking cumulative "
                         "straight from history (run AFTER the contiguous slice that brings "
                         "history through the period end). Implies --no-write.")
    ap.add_argument("--no-write", action="store_true", help="Do not append to fanatics_history.csv")
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = args.data_dir or os.path.join(script_dir, "data")
    out_dir = os.path.join(data_dir, "reports", "fanatics")
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 55)
    print("ROAD TRIPPIN' × FANATICS — DELIVERY REPORT BUILDER")
    print("=" * 55)

    if args.recreate:
        print("Mode: RECREATE (offline rebuild of Apr 13–May 10 report)\n")
        data = recreate_report4(data_dir)
    else:
        # period dates (default = current calendar month)
        if args.start and args.end:
            start = datetime.strptime(args.start, "%Y-%m-%d").date()
            end = datetime.strptime(args.end, "%Y-%m-%d").date()
        else:
            today = date.today()
            start = today.replace(day=1)
            nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            end = nxt - timedelta(days=1)
        print(f"Period: {start} → {end}\n")

        creds = authenticate_yt()
        from googleapiclient.discovery import build as build_api
        youtube = build_api("youtube", "v3", credentials=creds)
        print("Pulling YouTube …")
        tp, cum_win, cum_vids = yt_window_totals(youtube, start, end)
        period_raw = {
            "yt_total_views": tp["total_views"], "yt_total_count": tp["total_count"],
            "yt_full_views": tp["full"]["views"], "yt_full_count": tp["full"]["count"],
            "yt_clip_views": tp["clip"]["views"], "yt_clip_count": tp["clip"]["count"],
            "yt_short_views": tp["short"]["views"], "yt_short_count": tp["short"]["count"],
        }
        print("Summing Megaphone …")
        period_raw["mega_views"] = megaphone_total(
            os.path.join(data_dir, "megaphone_per_episode.csv"), start, end) or 0
        print("Reading socials …")
        soc = socials_for_month(os.path.join(data_dir, "socials.csv"), start.strftime("%Y-%m"))
        period_raw["ig_views"] = soc["ig"] or prompt_int("Instagram views (not in socials.csv)", 0)
        period_raw["tiktok_views"] = soc["tiktok"] or prompt_int("TikTok views", 0)
        period_raw["tiktok_count"] = soc["tiktok_count"] or prompt_int("TikTok video count", 0)
        period_raw["x_imp"] = soc["x"] or prompt_int("X impressions", 0)

        # top content from the cumulative video pull, published-in-period, top 3 by views
        in_period = [v for v in cum_vids if start.isoformat() <= v["published"] <= end.isoformat()]
        def top3(bucket):
            vs = sorted([v for v in in_period if v["bucket"] == bucket],
                        key=lambda x: x["views"], reverse=True)[:3]
            return [{"rank": i + 1, "views": v["views"],
                     "date": datetime.strptime(v["published"], "%Y-%m-%d").strftime("%b %d"),
                     "dur": hms(v["secs"]) if bucket == "full" else "",
                     "title": v["title"], "thumb": v["thumb"], "url": v["url"]}
                    for i, v in enumerate(vs)]
        top_content = {"full": top3("full"), "clip": top3("clip"), "short": top3("short")}

        manual = prompt_manual()
        all_rows = load_history(os.path.join(data_dir, "fanatics_history.csv"))
        if args.full_month:
            # Cumulative comes from history (which must already run through `end`);
            # the full-month window is for the this-period display only.
            last_end = max((r["period_end"] for r in all_rows), default="")
            if last_end < end.isoformat():
                print(f"  ⚠  history only runs through {last_end or 'never'}; run the "
                      f"contiguous slice through {end} first so cumulative is complete.")
            prior = history_cumulative(all_rows)
            data = assemble(period_raw, manual, prior, top_content, start, end,
                            date.today(), cum_from_history=True)
        else:
            prior = history_cumulative(all_rows)
            data = assemble(period_raw, manual, prior, top_content, start, end, date.today())

    # ---- render ----
    html = render_html(data)
    fname = f"Road_Trippin_Fanatics_{data['start']:%m%d}_{data['end']:%m%d}_{data['end']:%y}.html"
    out_path = os.path.join(out_dir, fname)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✓ Report written: {out_path}")
    print(f"  Impressions: {fmt(data['total_imp'])}  ·  "
          f"{data['pct_plan']:.2f}% of {fmt(IMP_GOAL_LOW)}  ·  pace {fmt(data['pace'])}")

    if not args.recreate and not args.no_write and not args.full_month:
        append_history(os.path.join(data_dir, "fanatics_history.csv"), data)
        print("  ↳ appended period to fanatics_history.csv")
    print("=" * 55)


if __name__ == "__main__":
    main()