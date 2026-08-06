#!/usr/bin/env python3
"""
check_sub_attribution.py — Diagnostic for the Live vs VOD growth analysis.

Central question: does the sum of video-attributed subscribersGained actually
add up to the channel's total subscribersGained? If a large share of subs come
in WITHOUT a clearly-attributed video (channel-page visits, Community posts,
search, cross-promo, etc.), then the video-level model systematically
undercounts real growth — which would explain why the "Live-continuation"
scenario keeps predicting far below the actual (Control) subscriber rate no
matter how well the per-content-type math is calibrated.

For each month in the two eras, this pulls:
  A) channel-level subscribersGained   (no video dimension — the true total)
  B) sum of subscribersGained across all videos, by video dimension
     (what our attribution model can "see")
and reports the coverage ratio B/A. A ratio well under 1.0 means a big chunk
of subscriber growth is not video-attributable, and the model's absolute
numbers should be read as "video-driven subs only," not total growth.

Run from master/shows/road_trippin/:
    python check_sub_attribution.py
"""

import sys
from datetime import datetime

try:
    from googleapiclient.discovery import build
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
except ImportError:
    print("Missing deps. pip install google-api-python-client google-auth-oauthlib")
    sys.exit(1)

try:
    from config import YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, YT_CHANNEL_ID as CHANNEL_ID
except ImportError:
    print("config.py not found — run from master/shows/road_trippin/")
    sys.exit(1)

# The two analysis windows, month by month.
MONTHS = [
    # VOD era
    ("2025-07-01", "2025-07-31"), ("2025-08-01", "2025-08-31"),
    ("2025-09-01", "2025-09-30"), ("2025-10-01", "2025-10-31"),
    ("2025-11-01", "2025-11-30"), ("2025-12-01", "2025-12-31"),
    # Live era
    ("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28"),
    ("2026-03-01", "2026-03-31"), ("2026-04-01", "2026-04-30"),
    ("2026-05-01", "2026-05-31"), ("2026-06-01", "2026-06-30"),
]


def analytics_client():
    creds = Credentials(
        token=None, refresh_token=YT_REFRESH_TOKEN,
        client_id=YT_CLIENT_ID, client_secret=YT_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("youtubeAnalytics", "v2", credentials=creds)


def channel_total_subs(analytics, start, end):
    """subscribersGained for the whole channel, no video dimension — the true total."""
    resp = analytics.reports().query(
        ids=f"channel=={CHANNEL_ID}", startDate=start, endDate=end,
        metrics="subscribersGained,subscribersLost",
    ).execute()
    rows = resp.get("rows", [])
    if not rows:
        return 0, 0
    return rows[0][0], rows[0][1]


def video_attributed_subs(analytics, start, end):
    """Sum of subscribersGained across videos, by video dimension — what the
    attribution model can see. The video-dimension report returns at most the
    top 200 videos (it doesn't support paging past that), which is more than
    enough here: subscriber gains are heavily concentrated in the top videos,
    so the long tail beyond 200 contributes negligibly to the sum. Returns the
    top-200 sum plus a flag so the caller knows if the cap was actually hit."""
    resp = analytics.reports().query(
        ids=f"channel=={CHANNEL_ID}", startDate=start, endDate=end,
        metrics="subscribersGained,subscribersLost",
        dimensions="video", sort="-subscribersGained",
        maxResults=200,
    ).execute()
    rows = resp.get("rows", [])
    gained_total = sum(r[1] for r in rows)
    lost_total = sum(r[2] for r in rows)
    capped = len(rows) >= 200
    return gained_total, lost_total, len(rows), capped


def main():
    print("=" * 74)
    print("SUBSCRIBER ATTRIBUTION COVERAGE CHECK")
    print("=" * 74)
    print("Comparing channel-total subscribersGained vs. the sum attributable to")
    print("individual videos. Coverage < 1.0 = growth the video model can't see.\n")

    analytics = analytics_client()

    print(f"{'Month':<10}{'Channel total':>15}{'Video-attributed':>18}{'Coverage':>11}")
    print("-" * 74)

    era_totals = {"VOD": [0, 0], "LIVE": [0, 0]}  # [channel, attributed]
    any_capped = False
    for start, end in MONTHS:
        month = start[:7]
        ch_gained, ch_lost = channel_total_subs(analytics, start, end)
        vid_gained, vid_lost, n, capped = video_attributed_subs(analytics, start, end)
        any_capped = any_capped or capped
        cov = (vid_gained / ch_gained) if ch_gained else 0
        flag = " *" if capped else ""
        print(f"{month:<10}{ch_gained:>15,}{vid_gained:>18,}{cov:>10.1%}{flag}")

        era = "VOD" if month < "2026-01" else "LIVE"
        era_totals[era][0] += ch_gained
        era_totals[era][1] += vid_gained

    print("-" * 74)
    for era in ["VOD", "LIVE"]:
        ch, vid = era_totals[era]
        cov = (vid / ch) if ch else 0
        print(f"{era + ' era':<10}{ch:>15,}{vid:>18,}{cov:>10.1%}")

    grand_ch = sum(era_totals[e][0] for e in era_totals)
    grand_vid = sum(era_totals[e][1] for e in era_totals)
    print("-" * 74)
    print(f"{'OVERALL':<10}{grand_ch:>15,}{grand_vid:>18,}{(grand_vid/grand_ch if grand_ch else 0):>10.1%}")
    print()
    if any_capped:
        print("  * month hit the 200-video report cap — its attributed sum is a")
        print("    slight UNDERCOUNT (true coverage marginally higher than shown).")
        print()
    print("Interpretation:")
    print("  ~100%  → video attribution captures essentially all growth; model")
    print("           absolute numbers are trustworthy as total growth.")
    print("  <<100% → a large share of subs are non-video-attributed; the model's")
    print("           absolute numbers reflect video-driven subs only, and the gap")
    print("           to the Control (actual) rate is expected, not a model error.")


if __name__ == "__main__":
    main()