"""
RDM — Daily social sync
=======================
Pulls account-level social metrics from platform APIs and writes them into each
show's socials CSV, so the dashboards (which already read those files) stay
current with no manual entry. Runs in the daily workflow BEFORE the dashboard builds.

Platforms so far: Instagram (Instagram API with Instagram Login).
Add a platform by writing one more sync_<platform>() and listing it in SHOWS.

What gets written, per show, for the CURRENT month (month to date):
    VIEWS ............ all account views that happened this month (any post)
    ENGAGEMENTS ...... all interactions that happened this month
    POSTS ............ posts published this month
    TOP_POST_VIEWS ... lifetime views of this month's best post
    FOLLOWERS ........ follower count today (the last run of the month = month-end count)
    FOLLOWER_GAIN .... FOLLOWERS minus last month's FOLLOWERS (when last month has one)
On the 1st–3rd of a month it also re-finalizes LAST month's VIEWS / ENGAGEMENTS /
POSTS / TOP_POST_VIEWS (Instagram can lag ~48h). Last month's FOLLOWERS is left as
the final daily value. Older months are never touched, and rows for other
platforms are left alone.

Usage (from repo root):
    python master/sync_socials.py --show gt
    python master/sync_socials.py --show gt rt --dry-run

Tokens — one name per account, e.g. IG_TOKEN_GT:
  • In the workflow: one GitHub secret per token (read from the environment).
  • Locally: all of them in master/config_socials.py (gitignored), e.g.
        IG_TOKEN_GT = "..."
        IG_TOKEN_RT = "..."
The environment wins if both exist. Instagram tokens expire after 60 days unless
refreshed. ONLY the workflow refreshes them (when TOKEN_OUT_DIR is set): the new
token is written there and saved back to GitHub secrets. Local runs never refresh,
so your laptop and GitHub can't knock each other's tokens out.
"""

import argparse
import csv
import importlib.util
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root

# Show → where its socials CSV lives and where its Instagram token comes from.
SHOWS = {
    "gt": {"csv": "master/shows/road_trippin/data/girls_tripp/socials_gt.csv", "instagram": {"env": "IG_TOKEN_GT"}},
    "rt": {"csv": "master/shows/road_trippin/data/socials.csv",               "instagram": {"env": "IG_TOKEN_RT"}},
    "sr": {"csv": "master/shows/schultz_report/data_sr/socials_sr.csv",       "instagram": {"env": "IG_TOKEN_SR"}},
    "fr": {"csv": "master/shows/road_trippin/data/football_related/data_fr/socials_fr.csv", "instagram": {"env": "IG_TOKEN_FR"}},
}
LOCAL_CONFIG = os.path.join(ROOT, "master", "config_socials.py")   # gitignored
FINALIZE_DAYS = 3        # re-finalize last month on the 1st–3rd
IG_API = "https://graph.instagram.com/v25.0"


# ═════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════
def month_bounds(ym):
    first = date.fromisoformat(ym + "-01")
    end = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, end


def prev_month(ym):
    return (date.fromisoformat(ym + "-01") - timedelta(days=1)).strftime("%Y-%m")


def unix(d):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())


def load_token(spec):
    """GitHub secret (environment) first, then master/config_socials.py."""
    tok = os.environ.get(spec["env"])
    if tok:
        return tok
    if os.path.exists(LOCAL_CONFIG):
        mod_spec = importlib.util.spec_from_file_location("config_socials", LOCAL_CONFIG)
        mod = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(mod)
        return getattr(mod, spec["env"], None)
    return None


def read_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def upsert(rows, platform, values):
    """values: {(period, metric): value}. Replaces those cells, keeps everything else."""
    keys = {(p, platform, m) for (p, m) in values}
    kept = [r for r in rows if (r["period"], r["platform"], r["metric"]) not in keys]
    kept += [{"period": p, "platform": platform, "metric": m, "value": str(v)} for (p, m), v in values.items()]
    kept.sort(key=lambda r: r["period"], reverse=True)
    return kept


def write_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["period", "platform", "metric", "value"], lineterminator="\r\n")
        w.writeheader()
        w.writerows(rows)


def cell(rows, period, platform, metric):
    for r in rows:
        if r["period"] == period and r["platform"] == platform and r["metric"] == metric:
            try:
                return float(r["value"])
            except ValueError:
                return None
    return None


# ═════════════════════════════════════════════════════════════════
# Instagram
# ═════════════════════════════════════════════════════════════════
class IG:
    def __init__(self, token):
        self.token = token

    def get(self, path, **params):
        params["access_token"] = self.token
        r = requests.get(f"{IG_API}/{path}", params=params, timeout=30)
        data = r.json()
        if r.status_code != 200 or "error" in data:
            err = data.get("error", {})
            detail = ", ".join(f"{k} {err[k]}" for k in ("code", "error_subcode", "type") if k in err)
            raise RuntimeError(f"{err.get('message', r.text)}" + (f" ({detail})" if detail else ""))
        return data

    def refresh(self):
        """Extend the token another 60 days. Returns the (possibly new) token."""
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": self.token}, timeout=30)
        data = r.json()
        if "access_token" in data:
            self.token = data["access_token"]
            return self.token, data.get("expires_in")
        raise RuntimeError(data.get("error", {}).get("message", r.text))

    def account_total(self, uid, metric, first, last):
        total, cur = 0, first
        while cur <= last:
            stop = min(cur + timedelta(days=29), last)
            d = self.get(f"{uid}/insights", metric=metric, period="day", metric_type="total_value",
                         since=unix(cur), until=unix(stop + timedelta(days=1)))["data"]
            total += d[0]["total_value"]["value"] if d else 0
            cur = stop + timedelta(days=1)
        return total

    def posts_since(self, uid, since):
        out, after = [], None
        while True:
            params = {"fields": "id,timestamp", "limit": 50}
            if after:
                params["after"] = after
            page = self.get(f"{uid}/media", **params)
            stop = False
            for p in page.get("data", []):
                if p["timestamp"][:10] < since:
                    stop = True
                    continue
                out.append(p)
            after = page.get("paging", {}).get("cursors", {}).get("after")
            if stop or not page.get("paging", {}).get("next"):
                return out

    def post_views(self, media_id):
        try:
            d = self.get(f"{media_id}/insights", metric="views")["data"]
            return d[0]["values"][0]["value"] if d else None
        except RuntimeError:
            return None


def sync_instagram(spec, rows, today, refresh=False):
    token = load_token(spec)
    if not token:
        raise LookupError(f"no {spec['env']} (not a secret here, not in master/config_socials.py) — skipped")
    ig = IG(token)
    me = ig.get("me", fields="user_id,username,followers_count")
    uid = me["user_id"]

    cur = today.strftime("%Y-%m")
    months = [cur] + ([prev_month(cur)] if today.day <= FINALIZE_DAYS else [])
    yesterday = today - timedelta(days=1)
    posts = ig.posts_since(uid, month_bounds(months[-1])[0].isoformat())
    values, report = {}, []

    for ym in months:
        first, end = month_bounds(ym)
        last = min(end, yesterday)
        mp = [p for p in posts if p["timestamp"][:7] == ym]
        views = [v for v in (ig.post_views(p["id"]) for p in mp) if v is not None]
        values[(ym, "POSTS")] = len(mp)
        values[(ym, "TOP_POST_VIEWS")] = max(views) if views else 0
        if last >= first:          # nothing to total on the 1st for the new month yet
            values[(ym, "VIEWS")] = ig.account_total(uid, "views", first, last)
            values[(ym, "ENGAGEMENTS")] = ig.account_total(uid, "total_interactions", first, last)
        if ym == cur:              # followers only for the current month (last run = month-end)
            values[(ym, "FOLLOWERS")] = me["followers_count"]
            pf = cell(rows, prev_month(ym), "INSTAGRAM", "FOLLOWERS")
            if pf is not None:
                values[(ym, "FOLLOWER_GAIN")] = me["followers_count"] - int(pf)
        report.append(ym)

    new_token, expires = None, None
    if refresh:
        try:
            new_token, expires = ig.refresh()
        except RuntimeError as e:
            print(f"    ⚠ token refresh failed: {e}")
    return values, f"@{me['username']}", report, new_token, expires


# ═════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser(description="Sync platform APIs into each show's socials CSV")
    ap.add_argument("--show", nargs="+", default=sorted(SHOWS), choices=sorted(SHOWS),
                    help="Shows to sync (default: all; shows without a token are skipped)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    today = date.today()
    token_out = os.environ.get("TOKEN_OUT_DIR")
    failed = 0
    print("=" * 60 + f"\nSOCIAL SYNC · {today}\n" + "=" * 60)

    for show in args.show:
        cfg = SHOWS[show]
        path = os.path.join(ROOT, cfg["csv"])
        rows = read_rows(path)
        print(f"\n[{show.upper()}] {cfg['csv']}")
        changed = False

        if "instagram" in cfg:
            try:
                values, who, months, new_token, expires = sync_instagram(cfg["instagram"], rows, today,
                                                                       refresh=bool(token_out) and not args.dry_run)
                rows = upsert(rows, "INSTAGRAM", values)
                changed = True
                print(f"  ✓ Instagram {who} · months {', '.join(months)}")
                for (p, m), v in sorted(values.items(), reverse=True):
                    print(f"      {p} {m:<15} {v:>12,}")
                if new_token and token_out:
                    os.makedirs(token_out, exist_ok=True)
                    with open(os.path.join(token_out, cfg["instagram"]["env"]), "w") as f:
                        f.write(new_token)
                if expires:
                    print(f"      token good for another {int(expires) // 86400} days")
            except LookupError as e:     # account not connected yet — not an error
                print(f"  · Instagram: {e}")
            except Exception as e:       # one platform failing shouldn't stop the others
                failed += 1
                print(f"  ✗ Instagram: {e}")

        if changed and not args.dry_run:      # only touch files that actually got new data
            write_rows(path, rows)

    print("\n" + "=" * 60 + ("\nDry run — no files changed." if args.dry_run else "") )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()