"""
SR — growth since the start of the RDM term (Aug 18 2026), week by week (Mon–Sun)
===============================================================================
Instagram per window: views, interactions, follows and unfollows (Instagram insights), plus the
follower count today. Weeks run Monday–Sunday (reported Mondays); the first is Aug 18–23 and
the current one is partial. Saved to data_sr/growth_sr.json and pushed to the shared repo, whose
Overview reads it together with the YouTube daily data in tracker_data_sr.json and the TikTok
account snapshots in data_sr/tiktok/.

Reads IG_TOKEN_SR (secret / config_socials.py); never refreshes it (sync_socials.py does that).
Instagram insights lag ~48h, so the last two days of the current window fill in later.

    python master/shows/schultz_report/pull_growth_sr.py
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
import sync_socials as ss   # noqa: E402

START = date(2026, 8, 18)
WINDOW = 7
OUT = os.path.join(HERE, "data_sr", "growth_sr.json")


def windows(through):
    """Monday–Sunday weeks from START (the first one runs START → that Sunday); the current week is partial."""
    out, s = [], START
    while s <= through:
        e = s + timedelta(days=6 - s.weekday())
        out.append((s, min(e, through), e > through))
        s = e + timedelta(days=1)
    return out


def follows(ig, uid, first, last):
    """(follows, unfollows) in the range — insights metric follows_and_unfollows, by follow_type."""
    got = {"FOLLOWER": 0, "NON_FOLLOWER": 0}
    cur = first
    while cur <= last:
        stop = min(cur + timedelta(days=29), last)
        d = ig.get(f"{uid}/insights", metric="follows_and_unfollows", period="day", metric_type="total_value",
                   breakdown="follow_type", since=ss.unix(cur), until=ss.unix(stop + timedelta(days=1)))["data"]
        for x in d:
            for bd in x["total_value"].get("breakdowns", []):
                for r in bd.get("results", []):
                    got[r["dimension_values"][0]] = got.get(r["dimension_values"][0], 0) + r["value"]
        cur = stop + timedelta(days=1)
    return got["FOLLOWER"], got["NON_FOLLOWER"]


def main():
    token = ss.load_token({"env": "IG_TOKEN_SR"})
    if not token:
        raise SystemExit("no IG_TOKEN_SR — skipped")
    ig = ss.IG(token)
    me = ig.get("me", fields="user_id,username,followers_count")
    if me["username"] != "theschultzreport":
        raise SystemExit(f"IG_TOKEN_SR is connected to @{me['username']}, not @theschultzreport")
    uid = me["user_id"]
    through = date.today() - timedelta(days=1)
    rows = []
    for s, e, partial in windows(through):
        f, u = follows(ig, uid, s, e)
        rows.append({"start": s.isoformat(), "end": e.isoformat(), "partial": partial,
                     "views": ig.account_total(uid, "views", s, e),
                     "interactions": ig.account_total(uid, "total_interactions", s, e),
                     "follows": f, "unfollows": u, "net_followers": f - u})
        print(f"  {s} → {e}{' (partial)' if partial else ''}: views {rows[-1]['views']:>10,} · "
              f"followers +{f:,} / −{u:,} = {f - u:+,}")
    # Recent posts with views (for the Content tab's top posts) — last 21 days
    posts = []
    since = (through - timedelta(days=20)).isoformat()
    page = ig.get(f"{uid}/media", fields="id,caption,permalink,timestamp,media_type,like_count,comments_count", limit=50)
    for m in page.get("data", []):
        if m["timestamp"][:10] < since:
            continue
        posts.append({"url": m.get("permalink"), "created": m["timestamp"][:10], "text": (m.get("caption") or "")[:140],
                      "type": m.get("media_type"), "views": ig.post_views(m["id"]), "likes": m.get("like_count"),
                      "comments": m.get("comments_count")})
    out = {"start": START.isoformat(), "window_days": WINDOW, "through": through.isoformat(),
           "pulled": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "instagram": {"followers_now": me["followers_count"], "windows": rows, "posts": posts}}
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"✓ growth_sr.json · Instagram @{me['username']} · {me['followers_count']:,} followers")


if __name__ == "__main__":
    main()
