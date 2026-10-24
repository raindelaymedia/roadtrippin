"""
YouTube views DURING a period, per video, for everything posted since a content cutoff.
Shared by the Fanatics delivery reports (RT and SR).

Method (agreed Oct 2026): a report period counts every view that happened in the period
on any channel video published on/after the show's content cutoff — RT 2025-10-01,
SR 2026-09-01. Those videos all carry the Fanatics integration. Older back catalog is
excluded. Views are additive month to month (no double counting), and the long tail of
earlier deal content keeps counting, the same way the social platforms are measured.

    from yt_period_views import uploads_since, period_views
    vids = uploads_since(youtube, CHANNEL_ID, "2026-09-01")         # metadata, newest first
    views = period_views(yta, [v["id"] for v in vids], start, end)   # {video_id: views in [start, end]}

Needs the channel owner's OAuth (YouTube Analytics). Analytics data lags ~2 days, so a
report for a period that just ended should be run a few days after it closes.
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
BATCH = 200          # video IDs per Analytics query


def _secs(iso):
    m = re.match(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def et_date(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ET).date().isoformat()


def uploads_since(youtube, channel_id, cutoff):
    """Every upload published on/after `cutoff` (YYYY-MM-DD, Eastern), newest first:
    id, title, published, secs, lifetime_views, thumb, url."""
    ch = youtube.channels().list(part="contentDetails", id=channel_id).execute(num_retries=3)
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    out, seen, page = [], set(), None
    while True:
        resp = youtube.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=50,
                                            pageToken=page).execute(num_retries=3)
        ids = [it["contentDetails"]["videoId"] for it in resp.get("items", [])]
        if not ids:
            break
        det = youtube.videos().list(part="contentDetails,snippet,statistics", id=",".join(ids)).execute(num_retries=3)
        oldest = None
        for v in det.get("items", []):
            if v["id"] in seen:
                continue
            seen.add(v["id"])
            pub = et_date(v["snippet"]["publishedAt"])
            oldest = pub if oldest is None else min(oldest, pub)
            if pub < cutoff:
                continue
            out.append({
                "id": v["id"], "title": v["snippet"]["title"], "published": pub,
                "secs": _secs(v["contentDetails"].get("duration")),
                "lifetime_views": int(v["statistics"].get("viewCount", 0)),
                "thumb": f"https://i.ytimg.com/vi/{v['id']}/maxresdefault.jpg",
                "url": f"https://youtu.be/{v['id']}",
            })
        page = resp.get("nextPageToken")
        if not page or (oldest and oldest < cutoff):
            break
    return out


def period_views(yta, video_ids, start, end):
    """Views that happened in [start, end] for each video — {video_id: views}.
    Videos with no views in the period are returned as 0."""
    ids = list(dict.fromkeys(video_ids))
    out = {i: 0 for i in ids}
    for i in range(0, len(ids), BATCH):
        batch = ids[i:i + BATCH]
        resp = yta.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end),
                                   metrics="views", dimensions="video", filters="video==" + ",".join(batch),
                                   sort="-views", maxResults=BATCH).execute(num_retries=3)
        for vid, views in resp.get("rows", []) or []:
            out[vid] = int(views)
    return out


def playlist_video_ids(youtube, playlist_id):
    ids, page = set(), None
    while True:
        r = youtube.playlistItems().list(part="contentDetails", playlistId=playlist_id, maxResults=50,
                                         pageToken=page).execute(num_retries=3)
        ids |= {it["contentDetails"]["videoId"] for it in r.get("items", [])}
        page = r.get("nextPageToken")
        if not page:
            return ids
