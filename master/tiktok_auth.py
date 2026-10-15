"""
RDM — TikTok account connection (Login Kit / Display API)
=========================================================
Connects a TikTok account to the Rain Delay Media analytics app so its exact video
views and account stats can be read. Read-only scopes: user.info.basic, user.info.stats,
video.list.

  1. link      python master/tiktok_auth.py link js
               → prints an approval link. Send it to the account owner; they log in to
                 TikTok, tap Authorize, and land on master/tiktok_auth.html with a code.
  2. exchange  python master/tiktok_auth.py exchange js <code>
               → swaps the code (valid a few minutes) for a refresh token, saved to
                 master/config_socials.py as TT_TOKEN_JS. Never printed.
  3. test      python master/tiktok_auth.py test js
               → shows which account is connected + its latest videos with exact views.
     status    python master/tiktok_auth.py status
               → every connected account and whether its connection still works.
  4. views     python master/tiktok_auth.py views sr <tiktok url or video id> [...]
               → exact views / likes / comments / shares for specific videos. Each video must be
                 read with ITS OWN account's connection (SR videos with sr, Jordan's with js).
     In code:  from tiktok_auth import video_stats;  video_stats("sr", ["7693209430162230541", ...])

Accounts are short labels: js (@realjordanschultz), sr (Schultz Report), rt, gt …
Needs TT_CLIENT_KEY and TT_CLIENT_SECRET in master/config_socials.py (gitignored).
Refresh tokens last ~365 days; TikTok may hand back a new one on each refresh, so this
script writes the latest one back to config_socials.py.
"""

import argparse
import importlib.util
import os
import re
import sys
import urllib.parse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "config_socials.py")
REDIRECT_URI = "https://raindelaymedia.github.io/roadtrippin/master/tiktok_auth.html"
SCOPES = "user.info.basic,user.info.stats,video.list"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
API = "https://open.tiktokapis.com/v2"


def config():
    spec = importlib.util.spec_from_file_location("config_socials", CONFIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def save_token(name, value):
    """Set NAME = "value" in config_socials.py (replace if present, else add under the TikTok section)."""
    text = open(CONFIG, encoding="utf-8").read()
    line = f'{name} = "{value}"'
    pat = re.compile(rf"^{re.escape(name)}\s*=.*$", re.M)
    if pat.search(text):
        text = pat.sub(line, text)
    elif "#TIKTOK TOKENS" in text:
        i = text.index("\n", text.index("#TIKTOK TOKENS")) + 1
        text = text[:i] + line + "\n" + text[i:]
    else:
        text = text.rstrip("\n") + "\n\n" + line + "\n"
    with open(CONFIG, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def token_name(account):
    return f"TT_TOKEN_{account.upper()}"


def exchange(cfg, data):
    r = requests.post(TOKEN_URL, data={"client_key": cfg.TT_CLIENT_KEY, "client_secret": cfg.TT_CLIENT_SECRET, **data},
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    j = r.json()
    if "access_token" not in j:
        raise SystemExit(f"TikTok token error: {j.get('error_description') or j.get('error') or j}")
    return j


def access_token(cfg, account):
    """Refresh token → access token (and save the newest refresh token)."""
    refresh = getattr(cfg, token_name(account), None)
    if not refresh:
        raise SystemExit(f"No {token_name(account)} in config_socials.py — run: link {account}, then exchange {account} <code>")
    j = exchange(cfg, {"grant_type": "refresh_token", "refresh_token": refresh})
    if j.get("refresh_token") and j["refresh_token"] != refresh:
        save_token(token_name(account), j["refresh_token"])
    return j["access_token"]


def api(tok, method, path, **kw):
    r = requests.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {tok}"}, timeout=30, **kw)
    j = r.json()
    err = j.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise SystemExit(f"TikTok API {path}: {err.get('code')} — {err.get('message')}")
    return j.get("data", {})


def video_id(url_or_id):
    m = re.search(r"(\d{15,25})", str(url_or_id))
    return m.group(1) if m else None


def video_stats(account, ids):
    """Exact stats for specific videos owned by `account`: {video_id: {views, likes, comments, shares, title, created}}.
    Videos that aren't this account's (or are deleted/private) are simply missing from the result."""
    cfg = config()
    tok = access_token(cfg, account)
    ids = [i for i in dict.fromkeys(video_id(x) for x in ids) if i]
    out = {}
    for i in range(0, len(ids), 20):                    # video/query takes up to 20 IDs
        vids = api(tok, "POST", "/video/query/",
                   params={"fields": "id,title,create_time,view_count,like_count,comment_count,share_count"},
                   json={"filters": {"video_ids": ids[i:i + 20]}}).get("videos", [])
        for v in vids:
            out[v["id"]] = {"views": v.get("view_count"), "likes": v.get("like_count"),
                            "comments": v.get("comment_count"), "shares": v.get("share_count"),
                            "title": v.get("title") or "", "created": v.get("create_time")}
    return out


def main():
    ap = argparse.ArgumentParser(description="Connect a TikTok account to the RDM analytics app")
    ap.add_argument("step", choices=["link", "exchange", "test", "status", "views"])
    ap.add_argument("account", nargs="?", help="short label, e.g. js, sr, rt, gt")
    ap.add_argument("code", nargs="*", help="exchange: the authorization code · views: video URLs or IDs")
    args = ap.parse_args()
    cfg = config()
    for k in ("TT_CLIENT_KEY", "TT_CLIENT_SECRET"):
        if not getattr(cfg, k, None):
            raise SystemExit(f"Add {k} to master/config_socials.py first")

    if args.step == "status":
        names = sorted(n for n in dir(cfg) if n.startswith("TT_TOKEN_") and getattr(cfg, n))
        if not names:
            print("No TikTok accounts connected yet. Start with: python master/tiktok_auth.py link sr")
            return
        for n in names:
            acct = n[len("TT_TOKEN_"):].lower()
            try:
                tok = access_token(cfg, acct)
                u = api(tok, "GET", "/user/info/", params={"fields": "display_name,follower_count,video_count"}).get("user", {})
                print(f"  ✓ {acct:<4} {u.get('display_name', '?'):<24} {u.get('follower_count', 0):>9,} followers · {u.get('video_count', 0):,} videos")
            except SystemExit as e:
                print(f"  ✗ {acct:<4} {e}")
        return
    if not args.account:
        raise SystemExit("Which account? e.g. python master/tiktok_auth.py link sr")

    if args.step == "link":
        q = urllib.parse.urlencode({"client_key": cfg.TT_CLIENT_KEY, "scope": SCOPES, "response_type": "code",
                                    "redirect_uri": REDIRECT_URI, "state": args.account.lower()})
        print(f"Approval link for '{args.account}' — send to the account owner (they must be added to the sandbox):\n")
        print(f"{AUTH_URL}?{q}\n")
        print("They'll land on the RDM page with a code. Then run:")
        print(f"  python master/tiktok_auth.py exchange {args.account} <code>")
        return

    if args.step == "exchange":
        if not args.code:
            raise SystemExit("Paste the code from the return page: exchange <account> <code>")
        code = urllib.parse.unquote(args.code[0].strip())
        j = exchange(cfg, {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI})
        save_token(token_name(args.account), j["refresh_token"])
        scopes = j.get("scope", "")
        print(f"✓ Connected '{args.account}' · saved {token_name(args.account)} to config_socials.py")
        print(f"  scopes granted: {scopes}")
        missing = set(SCOPES.split(",")) - set(scopes.split(","))
        if missing:
            print(f"  ⚠ missing scopes: {', '.join(sorted(missing))} — re-check the app's scopes and re-authorize")
        cfg = config()

    if args.step == "views":
        if not args.code:
            raise SystemExit("Give video URLs or IDs: views <account> <url> [<url> ...]")
        stats = video_stats(args.account, args.code)
        for x in args.code:
            vid = video_id(x)
            st = stats.get(vid)
            if st:
                print(f"  {vid}  views {st['views']:>9,}  likes {st['likes']:>7,}  comments {st['comments']:>5,}  "
                      f"shares {st['shares']:>5,}  {st['title'][:45]}")
            else:
                print(f"  {vid or x}  not found — not this account's video, or deleted/private")
        return

    tok = access_token(cfg, args.account)
    user = api(tok, "GET", "/user/info/", params={
        "fields": "open_id,display_name,follower_count,likes_count,video_count"}).get("user", {})
    print(f"\nAccount: {user.get('display_name')} · "
          f"{user.get('follower_count', 0):,} followers · {user.get('likes_count', 0):,} likes · {user.get('video_count', 0):,} videos")
    vids = api(tok, "POST", "/video/list/",
               params={"fields": "id,title,create_time,view_count,like_count,comment_count,share_count,share_url"},
               json={"max_count": 5}).get("videos", [])
    print("Latest videos (exact counts):")
    for v in vids:
        print(f"  {v['id']}  views {v.get('view_count', 0):>9,}  likes {v.get('like_count', 0):>7,}  "
              f"comments {v.get('comment_count', 0):>5,}  {(v.get('title') or '')[:50]}")


if __name__ == "__main__":
    sys.exit(main())
