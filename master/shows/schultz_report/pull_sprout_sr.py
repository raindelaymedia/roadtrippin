"""
SR — daily Sprout Social pull (Jordan Schultz's personal accounts + sponsor tags)
=================================================================================
Pulls every post on the Sprout-connected profiles since CAMPAIGN_START that carries a sponsor tag
(Chime, Fanatics, Hims, Lowe's) with its lifetime metrics, and saves:

    data_sr/sprout/posts.json                current snapshot: one entry per tagged post
    data_sr/sprout/daily/YYYY-MM-DD.csv      that day's lifetime views per post (history for
                                             "views during a period" — never rewritten)

Only sponsor-tagged posts are kept: on Jordan's personal accounts that's the show content. YouTube is
skipped: the SR channel is counted from YouTube itself (all of it is integrated), so Sprout would double count. Runs in
the daily workflow (SPROUT_TOKEN secret) and is pushed to raindelaymedia/The-Schultz-Report with the
other SR data. Uses master/sprout.py.

    python master/shows/schultz_report/pull_sprout_sr.py
"""

import csv
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, MASTER)
from sprout import Sprout   # noqa: E402

CAMPAIGN_START = "2026-09-01"
GROWTH_START = "2026-08-18"             # start of the RDM term (account growth)
SKIP_NETWORKS = {"youtube"}             # counted from YouTube directly
SR_HANDLES = {"theschultzreport"}       # the show's accounts; everything else is Jordan's (X @Schultz_Report is HIS)
SPONSOR_TAGS = ["Chime", "Fanatics", "Hims", "Lowe's"]
OUT = os.path.join(HERE, "data_sr", "sprout")
ET = ZoneInfo("America/New_York")
NETWORK = {"fb_instagram_account": "INSTAGRAM", "instagram": "INSTAGRAM", "tiktok": "TIKTOK", "twitter": "X",
           "x": "X", "facebook": "FACEBOOK", "threads": "THREADS", "youtube": "YOUTUBE", "linkedin": "LINKEDIN"}


def main():
    sp = Sprout()
    profiles = [p for p in sp.profiles() if p.get("network_type") not in SKIP_NETWORKS]
    by_id = {p["customer_profile_id"]: p for p in profiles}
    # Show content = any CAMPAIGN tag (Fanatics, Hims, Chime, Lowe's, Unbranded ...) - one tag per post in Sprout.
    # LABEL tags (High Priority, Customer Feedback) are workflow flags, not content, and are ignored.
    tags = {t["tag_id"]: t["text"] for t in sp.tags() if t.get("type") == "CAMPAIGN" or t.get("text") in SPONSOR_TAGS}
    today = datetime.now(ET).date()
    end = (today - timedelta(days=1)).isoformat()
    print(f"SPROUT · {len(profiles)} profiles · tags {', '.join(tags.values())} · posts {CAMPAIGN_START} → {end}")

    # One profile at a time: Sprout's post records don't say which profile they came from
    posts = []
    for pid in by_id:
        posts += [{**p, "customer_profile_id": pid} for p in sp.posts([pid], CAMPAIGN_START, end, tag_ids=list(tags))]
    out = []
    for p in posts:
        prof = by_id.get(p.get("customer_profile_id"), {})
        m = p.get("metrics", {})
        net = NETWORK.get(prof.get("network_type"), "")
        if net == "X":                          # X is measured in impressions (how the team and the reports count it)
            views = m.get("lifetime.impressions") or 0
        else:
            views = m.get("lifetime.views") or m.get("lifetime.video_views") or m.get("lifetime.impressions") or 0
        out.append({
            "url": p.get("perma_link"), "created": (p.get("created_time") or "")[:10],
            "profile": prof.get("native_name"), "profile_id": p.get("customer_profile_id"),
            "network": NETWORK.get(prof.get("network_type"), (prof.get("network_type") or "").upper()),
            "owner": "SR" if (prof.get("native_name") or "").lower() in SR_HANDLES else "JS",
            "sponsors": sorted({tags[int(t["id"])] for t in (p.get("internal", {}).get("tags") or [])
                                if int(t["id"]) in tags}),
            "views": views, "impressions": m.get("lifetime.impressions"), "video_views": m.get("lifetime.video_views"),
            "reactions": m.get("lifetime.reactions"), "text": (p.get("text") or "")[:140],
        })
    out.sort(key=lambda r: (r["created"], r["url"] or ""))
    os.makedirs(os.path.join(OUT, "daily"), exist_ok=True)
    json.dump({"pulled": today.isoformat(), "through": end, "campaign_start": CAMPAIGN_START,
               "profiles": [{"id": p["customer_profile_id"], "network": NETWORK.get(p.get("network_type"), p.get("network_type")),
                             "handle": p.get("native_name"), "name": p.get("name")} for p in profiles],
               "posts": out}, open(os.path.join(OUT, "posts.json"), "w", encoding="utf-8"), indent=1)
    with open(os.path.join(OUT, "daily", f"{today.isoformat()}.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "views", "impressions"])
        w.writerows([r["url"], r["views"], r["impressions"]] for r in out)

    # Account-level daily metrics (followers, net growth, impressions/views) since the RDM start
    prof_ids = [p["customer_profile_id"] for p in profiles]
    daily = sp.daily(prof_ids, GROWTH_START, end, ["lifetime_snapshot.followers_count", "net_follower_growth",
                                                   "impressions", "video_views", "views"])
    with open(os.path.join(OUT, "profiles_daily.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\r\n")
        w.writerow(["date", "profile_id", "network", "handle", "owner", "followers", "net_follower_growth",
                    "impressions", "video_views", "views"])
        for r in sorted(daily, key=lambda r: (r["date"] or "", r["profile_id"] or 0)):
            prof, m = by_id.get(r["profile_id"], {}), r["metrics"]
            handle = prof.get("native_name") or ""
            w.writerow([(r["date"] or "")[:10], r["profile_id"], NETWORK.get(prof.get("network_type"), ""), handle,
                        "SR" if handle.lower() in SR_HANDLES else "JS", m.get("lifetime_snapshot.followers_count"),
                        m.get("net_follower_growth"), m.get("impressions"), m.get("video_views"), m.get("views")])
    print(f"  profiles_daily.csv · {len(daily)} profile-days since {GROWTH_START}")

    summary = {}
    for r in out:
        for s in r["sponsors"]:
            k = (s, r["owner"], r["network"])
            n, v = summary.get(k, (0, 0))
            summary[k] = (n + 1, v + (r["views"] or 0))
    for (s, o, n), (c, v) in sorted(summary.items()):
        print(f"  {s:<9} {o} {n:<10} {c:>4} posts · {v:>11,} views")
    print(f"✓ {len(out)} sponsor-tagged posts saved")


if __name__ == "__main__":
    main()
