"""
Sprout Social API client (Analytics API) — shared by this repo and RDM's internal Fanatics reporting.
Docs: https://api.sproutsocial.com/docs/  ·  needs a Sprout Advanced (or higher) plan.

Token: SPROUT_TOKEN — GitHub secret, or master/config_socials.py locally (gitignored). API tokens are
long-lived and don't rotate, so (unlike Instagram/TikTok) both repos can use one without conflicts.
Optional: SPROUT_CUSTOMER_ID (otherwise the first customer the token can see).

    python master/sprout.py status                                  # customer, profiles, tags (start here)
    python master/sprout.py daily  --start 2026-10-01 --end 2026-10-15 [--profile <name or id> ...]
    python master/sprout.py posts  --start 2026-10-01 --end 2026-10-15 --tag Fanatics [--profile ...]

In code:
    from sprout import Sprout
    sp = Sprout()                                   # reads the token
    sp.profiles(); sp.tags()
    sp.daily(profile_ids, "2026-10-01", "2026-10-15", ["impressions", "video_views", "followers"])
    sp.posts(profile_ids, "2026-10-01", "2026-10-15", tag_ids=[...], metrics=[...])

Limits: 60 requests/minute, 250K/month; ≤100 profiles and ≤1 year per request. Field and metric names
differ by network — run `status`, then `daily`/`posts` once, and check what comes back before relying on one.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "https://api.sproutsocial.com"
DEFAULT_DAILY = ["impressions", "video_views", "followers", "net_follower_growth", "post_count",
                 "reactions", "comments", "shares"]
DEFAULT_POST = ["lifetime.impressions", "lifetime.video_views", "lifetime.views", "lifetime.reactions"]
POST_FIELDS = ["created_time", "perma_link", "text", "customer_profile_id", "internal.tags.id"]


def _config(name):
    val = os.environ.get(name)
    if val:
        return val
    path = os.path.join(HERE, "config_socials.py")
    if os.path.exists(path):
        spec = importlib.util.spec_from_file_location("config_socials", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, name, None)
    return None


class Sprout:
    def __init__(self, token=None, customer_id=None):
        self.token = token or _config("SPROUT_TOKEN")
        if not self.token:
            raise SystemExit("No SPROUT_TOKEN (GitHub secret, or master/config_socials.py locally)")
        self._cid = customer_id or _config("SPROUT_CUSTOMER_ID")

    # ── HTTP ──
    def _req(self, method, path, body=None):
        url = f"{BASE}{path}"
        for attempt in range(5):
            r = requests.request(method, url, json=body, timeout=60,
                                 headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
            if r.status_code == 429 or r.status_code >= 500:          # rate limit / transient
                time.sleep(min(60, 2 ** attempt * 5))
                continue
            if r.status_code >= 400:
                raise SystemExit(f"Sprout {method} {path}: HTTP {r.status_code} — {r.text[:300]}")
            return r.json()
        raise SystemExit(f"Sprout {method} {path}: still failing after retries")

    def _paged(self, path, body):
        """All pages. Metric names differ by network, so metrics Sprout rejects are dropped and retried."""
        out, page = [], 1
        while True:
            try:
                j = self._req("POST", path, {**body, "page": page})
            except SystemExit as e:
                bad = re.search(r"invalid metrics: ([^\"]+)", str(e))
                if not bad or "metrics" not in body:
                    raise
                drop = {m.strip() for m in bad.group(1).split(",")}
                body = {**body, "metrics": [m for m in body["metrics"] if m not in drop]}
                if not body["metrics"]:
                    raise
                print(f"  · Sprout doesn't offer {', '.join(sorted(drop))} here — skipped")
                continue
            out += j.get("data", [])
            paging = j.get("paging", {})
            if page >= (paging.get("total_pages") or 1):
                return out
            page += 1

    # ── Metadata ──
    def customers(self):
        return self._req("GET", "/v1/metadata/client").get("data", [])

    @property
    def customer_id(self):
        if not self._cid:
            cs = self.customers()
            if not cs:
                raise SystemExit("This Sprout token can't see any customer accounts")
            self._cid = cs[0]["customer_id"]
        return self._cid

    def profiles(self):
        return self._req("GET", f"/v1/{self.customer_id}/metadata/customer").get("data", [])

    def tags(self):
        return self._req("GET", f"/v1/{self.customer_id}/metadata/customer/tags").get("data", [])

    def resolve_profiles(self, names_or_ids):
        """Profile names / handles / IDs → customer_profile_ids (all profiles if empty)."""
        profs = self.profiles()
        if not names_or_ids:
            return [p["customer_profile_id"] for p in profs]
        out = []
        for x in names_or_ids:
            m = [p for p in profs if str(p["customer_profile_id"]) == str(x)
                 or (p.get("native_name") or "").lower() == str(x).lower().lstrip("@")
                 or (p.get("name") or "").lower() == str(x).lower()]
            if not m:
                raise SystemExit(f"No Sprout profile matches '{x}' — run `status` to see them")
            out += [p["customer_profile_id"] for p in m]
        return out

    def resolve_tags(self, names):
        tags = self.tags()
        out = []
        for n in names or []:
            m = [t for t in tags if (t.get("text") or "").lower() == n.lower()]
            if not m:
                raise SystemExit(f"No Sprout tag '{n}' — tags: {', '.join(sorted(t.get('text', '') for t in tags))}")
            out += [t["tag_id"] for t in m]
        return out

    # ── Analytics ──
    def daily(self, profile_ids, start, end, metrics=None):
        """Daily account metrics per profile: [{date, profile_id, metrics{...}}]."""
        rows = self._paged(f"/v1/{self.customer_id}/analytics/profiles", {
            "filters": [f"customer_profile_id.eq({', '.join(map(str, profile_ids))})",
                        f"reporting_period.in({start}...{end})"],
            "metrics": metrics or DEFAULT_DAILY})
        return [{"date": r["dimensions"].get("reporting_period.by(day)"),
                 "profile_id": r["dimensions"].get("customer_profile_id"), "metrics": r.get("metrics", {})}
                for r in rows]

    def posts(self, profile_ids, start, end, tag_ids=None, metrics=None, timezone="America/New_York"):
        """Posts created in [start, end] (dates), optionally only those carrying any of tag_ids."""
        filters = [f"customer_profile_id.eq({', '.join(map(str, profile_ids))})",
                   f"created_time.in({start}T00:00:00..{end}T23:59:59)"]
        posts = self._paged(f"/v1/{self.customer_id}/analytics/posts", {
            "fields": POST_FIELDS, "filters": filters, "metrics": metrics or DEFAULT_POST, "timezone": timezone})
        if tag_ids:   # tag filtering is done here: every post comes back with internal.tags
            want = {str(t) for t in tag_ids}
            posts = [p for p in posts if want & {str(t.get("id")) for t in (p.get("internal", {}).get("tags") or [])}]
        return posts


def main():
    ap = argparse.ArgumentParser(description="Sprout Social API")
    ap.add_argument("step", choices=["status", "daily", "posts"])
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--profile", nargs="*", default=[], help="profile names, @handles or IDs (default: all)")
    ap.add_argument("--tag", nargs="*", default=[], help="Sprout tag names, e.g. Fanatics")
    ap.add_argument("--raw", action="store_true", help="print the raw JSON (to see every metric returned)")
    args = ap.parse_args()
    sp = Sprout()

    if args.step == "status":
        print("Customers:", ", ".join(f"{c['name']} ({c['customer_id']})" for c in sp.customers()))
        print(f"\nProfiles (customer {sp.customer_id}):")
        for p in sp.profiles():
            print(f"  {p['customer_profile_id']:>10}  {p.get('network_type', ''):<20} @{p.get('native_name', '')}  · {p.get('name', '')}")
        print("\nTags:")
        for t in sorted(sp.tags(), key=lambda t: t.get("text", "")):
            print(f"  {t['tag_id']:>10}  {t.get('text', ''):<24} {t.get('type', '')}{'' if t.get('active', True) else ' (inactive)'}")
        return

    if not (args.start and args.end):
        raise SystemExit("--start and --end are required (YYYY-MM-DD)")
    pids = sp.resolve_profiles(args.profile)
    if args.step == "daily":
        rows = sp.daily(pids, args.start, args.end)
        if args.raw:
            print(json.dumps(rows[:20], indent=2))
            return
        totals = {}
        for r in rows:
            t = totals.setdefault(r["profile_id"], {})
            for k, v in r["metrics"].items():
                if isinstance(v, (int, float)) and k not in ("followers",):
                    t[k] = t.get(k, 0) + v
        names = {p["customer_profile_id"]: p.get("native_name") for p in sp.profiles()}
        for pid, t in totals.items():
            print(f"@{names.get(pid, pid)}: " + ", ".join(f"{k} {v:,.0f}" for k, v in sorted(t.items())))
        return

    tag_ids = sp.resolve_tags(args.tag)
    posts = sp.posts(pids, args.start, args.end, tag_ids)
    if args.raw:
        print(json.dumps(posts[:10], indent=2))
        return
    print(f"{len(posts)} post(s){' tagged ' + ', '.join(args.tag) if args.tag else ''}")
    for p in posts:
        m = p.get("metrics", {})
        print(f"  {p.get('created_time', '')[:10]}  views {m.get('lifetime.video_views') or m.get('lifetime.views') or 0:>9,}  "
              f"impr {m.get('lifetime.impressions') or 0:>9,}  {p.get('perma_link', '')}")


if __name__ == "__main__":
    sys.exit(main())
