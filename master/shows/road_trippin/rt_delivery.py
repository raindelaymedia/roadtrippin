"""
Road Trippin' × Fanatics — delivery for any window (Season 2 data layer)
=======================================================================
Works out what RT + Girls Tripp delivered in a window and saves it as a record
(data/reports/fanatics/rt_delivery_<start>_<end>.json), with pacing against the Year 1
delivery goal (130M impressions, Oct 16 2026 – Oct 18 2027) and the talent post minimums.

YouTube — every view DURING the window on channel videos published on/after
CONTENT_START (2025-10-01, all Fanatics-integrated), per video, from YouTube Analytics
(master/yt_period_views.py). RT channel with RT's login, GT channel with GT's.
Each video is classified by playlist first, then by length:
    Perk Unplugged / Channing's Mailbag playlists ... solo episode   (5x)
    Girls Tripp Full Episodes playlist ............... GT episode    (6x, S2 TBD)
    RT Full Episodes playlist ........................ group episode (6x)
    otherwise: <= 3:00 short, else clip ............... clips & Shorts (2x)

Counted (Season 2, Jon Oct 2026): RT group episodes, Girls Tripp, Channing's Mailbag, Perk Unplugged — not
Football Related. Mailbag / Unplugged are on hiatus. Clips, Shorts, show socials and talent posts count too.
RT and GT are broken out separately (YouTube, audio, social).

Girls Tripp Instagram — the non-collab GT posts listed in data/girls_tripp/fanatics_posts_gt.csv (RT gets credit
for RT × GT collabs through RT's whole-account numbers), lifetime views via the Instagram API (IG_TOKEN_GT).

Everything else comes from an inputs file (data/reports/fanatics/inputs_rt_<start>_<end>.json):
RT social views (Instagram, TikTok, X, Facebook), Megaphone total delivery (RT, GT),
episode / integration / talent-post counts. Each value can be a list of parts that are
added up, e.g. [sep_14_30, oct_1_15]; null marks a part that's still missing.

Usage (from repo root):
    python master/shows/road_trippin/rt_delivery.py --start 2026-09-14 --end 2026-10-15
"""

import argparse
import importlib.util
import json
import os
import sys
from datetime import date, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, MASTER)
from yt_period_views import uploads_since, period_views, playlist_video_ids   # noqa: E402

CONTENT_START = "2025-10-01"
SHORTS_MAX = 180
PLAYLISTS = {   # classification order matters: first match wins
    "solo": ["PLX3ZLYz4-6vHA_GG37kXNZowGAKqu94Sh",    # Perk Unplugged (RT channel)
             "PLX3ZLYz4-6vFapW85GvTgNr-4rJjgkzqi"],   # Channing's Mailbag (RT channel)
    "gt_episode": ["PLcPj2Bidz6D4"],                  # Girls Tripp Full Episodes (GT channel)
    "group": ["PLX3ZLYz4-6vE2_ZNLW5AfzbHTd1jTskDl"],  # RT Full Episodes (RT channel)
}
MULTS = {"group": 6, "solo": 5, "gt_episode": 6, "clip": 2, "short": 2,   # same as Season 1 (kept for S2, Oct 2026)
         "social": 1, "audio": 1}
SEASON = "Season 2 (renewal Year 1)"
YEAR1 = ("2026-10-16", "2027-10-18")     # reporting year: our S2 start → media plan (Exhibit C) Year 1 end
YEAR1_DAYS = (date.fromisoformat(YEAR1[1]) - date.fromisoformat(YEAR1[0])).days + 1
DELIVERY_GOAL = 130_000_000              # contractual impressions per year, shortfall cured with makegoods
TALENT_MIN = {"rj": 3, "perk": 4, "channing": 4, "allie": 3}   # Fanatics posts per week (575/yr minimum overall)
LABELS = {"group": "Group episodes", "solo": "Solo episodes (Perk Unplugged · Mailbag)",
          "gt_episode": "Girls Tripp episodes", "clip": "Clips", "short": "Shorts"}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def yt_clients(cfg):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    creds = Credentials(token=None, refresh_token=cfg.YT_REFRESH_TOKEN, client_id=cfg.YT_CLIENT_ID,
                        client_secret=cfg.YT_CLIENT_SECRET, token_uri="https://oauth2.googleapis.com/token",
                        scopes=["https://www.googleapis.com/auth/yt-analytics.readonly",
                                "https://www.googleapis.com/auth/youtube.readonly"])
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds), build("youtubeAnalytics", "v2", credentials=creds)


def youtube_window(cfg, start, end, playlist_sets, show):
    """Per-video views during [start, end] for one channel, classified."""
    yt, yta = yt_clients(cfg)
    vids = [v for v in uploads_since(yt, cfg.YT_CHANNEL_ID, CONTENT_START) if v["published"] <= end]
    views = period_views(yta, [v["id"] for v in vids], start, end)
    out = []
    for v in vids:
        kind = next((k for k, ids in playlist_sets if v["id"] in ids), None)
        kind = kind or ("short" if v["secs"] <= SHORTS_MAX else "clip")
        out.append({**v, "show": show, "kind": kind, "views": views.get(v["id"], 0),
                    "new": v["published"] >= start})
    return out


def gt_instagram_posts(start, end):
    """Girls Tripp Instagram for the window: the NON-collab posts listed in data/girls_tripp/fanatics_posts_gt.csv
    (url, notes) that were published in the window, with their lifetime views. Collabs with RT are credited to RT,
    whose whole-account numbers already include them. Returns (views, posts, missing_urls) or None if no list."""
    path = os.path.join(HERE, "data", "girls_tripp", "fanatics_posts_gt.csv")
    if not os.path.exists(path):
        return None
    import csv
    import re
    urls = [r["url"].strip() for r in csv.DictReader(open(path, encoding="utf-8-sig")) if (r.get("url") or "").strip()]
    code = lambda u: (re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", u) or [None, None])[1]
    want = {code(u): u for u in urls if code(u)}
    sync = load_module("sync_socials", os.path.join(MASTER, "sync_socials.py"))
    tok = sync.load_token({"env": "IG_TOKEN_GT"})
    if not tok:
        return None
    ig = sync.IG(tok)
    uid = ig.get("me", fields="user_id")["user_id"]
    found, after = {}, None
    while True:                                          # walk the account's media back to the window start
        params = {"fields": "id,permalink,timestamp", "limit": 50, **({"after": after} if after else {})}
        page = ig.get(f"{uid}/media", **params)
        for m in page.get("data", []):
            c = code(m.get("permalink", ""))
            if c in want:
                found[c] = m
        older = [m for m in page.get("data", []) if m["timestamp"][:10] < start]
        after = page.get("paging", {}).get("cursors", {}).get("after")
        if older or not page.get("paging", {}).get("next"):
            break
    posts = []
    for c, m in found.items():
        if start <= m["timestamp"][:10] <= end:
            posts.append({"url": want[c], "date": m["timestamp"][:10], "views": ig.post_views(m["id"]) or 0})
    missing = [u for c, u in want.items() if c not in found]
    return sum(p["views"] for p in posts), posts, missing


def total(v):
    """Inputs value → number. Lists are added up; any None part means 'missing'."""
    if isinstance(v, list):
        return None if any(x is None for x in v) else sum(v)
    return v


def main():
    ap = argparse.ArgumentParser(description="RT + GT Fanatics delivery for a window")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()
    s, e = args.start, args.end
    out_dir = os.path.join(HERE, "data", "reports", "fanatics")
    inputs_path = os.path.join(out_dir, f"inputs_rt_{s.replace('-', '')}_{e.replace('-', '')}.json")
    inp = json.load(open(inputs_path, encoding="utf-8")) if os.path.exists(inputs_path) else {}
    days = (date.fromisoformat(e) - date.fromisoformat(s)).days + 1
    print(f"RT × FANATICS DELIVERY · {s} → {e} ({days} days)")

    # ── YouTube: RT channel and GT channel, broken out by show ──
    rt_cfg = load_module("config", os.path.join(HERE, "config.py"))
    gt_cfg = load_module("config_gt", os.path.join(HERE, "config_gt.py"))
    rt_yt, _ = yt_clients(rt_cfg)
    gt_yt, _ = yt_clients(gt_cfg)
    sets = [(k, set().union(*(playlist_video_ids(gt_yt if k == "gt_episode" else rt_yt, p) for p in pids)))
            for k, pids in PLAYLISTS.items()]
    videos = youtube_window(rt_cfg, s, e, sets, "RT") + youtube_window(gt_cfg, s, e, sets, "GT")
    yt = {"RT": {}, "GT": {}}
    for show in yt:
        for k in LABELS:
            vs = [v for v in videos if v["show"] == show and v["kind"] == k]
            if vs and (sum(v["views"] for v in vs) or any(v["new"] for v in vs)):
                yt[show][k] = {"views": sum(v["views"] for v in vs), "new": sum(1 for v in vs if v["new"]),
                               "impressions": sum(v["views"] for v in vs) * MULTS[k]}

    # ── Social: RT = whole-account numbers (RT gets the collab credit); GT = non-collab URL list ──
    rt_social = {k: total(inp.get("rt_social", {}).get(k)) for k in ("instagram", "tiktok", "x", "facebook")}
    g = gt_instagram_posts(s, e)
    gt_ig, gt_posts, gt_missing = (g if g else (None, [], []))
    social = {"RT": rt_social, "GT": {"instagram": gt_ig}}

    # ── Audio: Megaphone total delivery (downloads + streams), per feed ──
    audio = {"RT": total(inp.get("megaphone", {}).get("rt")), "GT": total(inp.get("megaphone", {}).get("gt"))}

    per_show = {}
    for show in ("RT", "GT"):
        yi = sum(x["impressions"] for x in yt[show].values())
        si = sum(v or 0 for v in social[show].values()) * MULTS["social"]
        ai = (audio[show] or 0) * MULTS["audio"]
        per_show[show] = {"youtube_impressions": yi, "social_impressions": si, "audio_impressions": ai,
                          "impressions": yi + si + ai}
    impressions = sum(x["impressions"] for x in per_show.values())

    # ── Pacing: Year 1 goal and talent post minimums, prorated to the window ──
    goal_window = DELIVERY_GOAL * days / YEAR1_DAYS
    counts = inp.get("counts", {})
    talent = {k: {"posts": counts.get(f"{k}_posts"), "minimum": round(m * days / 7, 1)} for k, m in TALENT_MIN.items()}

    missing = [f"{show} {k}" for show in social for k, v in social[show].items() if v is None]
    missing += [f"Megaphone {k}" for k, v in audio.items() if v is None]
    rec = {
        "start": s, "end": e, "days": days, "generated": date.today().isoformat(), "content_start": CONTENT_START,
        "season": SEASON, "multipliers": MULTS, "youtube": yt, "social": social, "audio": audio, "per_show": per_show,
        "impressions": impressions, "goal": {"year": DELIVERY_GOAL, "window": round(goal_window),
                                              "pace": round(impressions / goal_window, 3) if goal_window else None},
        "talent": talent, "counts": counts, "gt_instagram_posts": gt_posts, "gt_instagram_unmatched": gt_missing,
        "missing": missing, "notes": inp.get("notes", ""),
        "top_videos": [{k: v[k] for k in ("show", "kind", "title", "published", "views", "url")}
                       for v in sorted(videos, key=lambda v: -v["views"])[:10]],
    }
    path = os.path.join(out_dir, f"rt_delivery_{s.replace('-', '')}_{e.replace('-', '')}.json")
    json.dump(rec, open(path, "w", encoding="utf-8"), indent=2)

    f = lambda v: "MISSING" if v is None else f"{v:,.0f}"
    for show, name in (("RT", "ROAD TRIPPIN'"), ("GT", "GIRLS TRIPP")):
        print(f"\n{name}")
        for k, x in yt[show].items():
            print(f"  YouTube {LABELS[k]:<38} {f(x['views']):>11} views × {MULTS[k]} = {f(x['impressions']):>11}   ({x['new']} new)")
        for k, v in social[show].items():
            print(f"  {k.title():<46} {f(v):>11}")
        print(f"  {'Megaphone (downloads + streams)':<46} {f(audio[show]):>11}")
        print(f"  {name} impressions {f(per_show[show]['impressions']):>34}")
    print(f"\nIMPRESSIONS  {f(impressions)}  ·  Year 1 goal prorated to {days} days: {f(goal_window)}"
          f"  ·  pace {rec['goal']['pace'] or 0:.0%}")
    print("Talent posts vs minimum (prorated):",
          ", ".join(f"{k} {t['posts'] if t['posts'] is not None else '?'}/{t['minimum']}" for k, t in talent.items()))
    if gt_missing:
        print(f"⚠ {len(gt_missing)} GT Instagram URL(s) not found on the account: {gt_missing[:3]}")
    if missing:
        print(f"⚠ Still missing (counted as 0): {', '.join(missing)}")
    print(f"✓ Saved {os.path.relpath(path)}")


if __name__ == "__main__":
    main()
