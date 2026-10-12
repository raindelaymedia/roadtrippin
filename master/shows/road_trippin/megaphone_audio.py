"""
Megaphone audio for the dashboards (RT + GT, FR later).

Reads the monthly Megaphone file (megaphone_monthly.csv / girls_tripp/megaphone_monthly_gt.csv,
filled from the pasted Megaphone screens — see claude.md) so a dashboard build always
shows the latest paste, without re-running the tracker.

    audio = load(path)                  # {"months": [...oldest-first], "rows": {YYYY-MM: {...}}}
    apply_to_extract(d, audio)          # downloads / streams / per-episode in the extract dict
    a = series(audio, eps_by_month)     # lists aligned to audio["months"] + the latest month
"""

import csv
import os

# Columns that are left 0 when a month has no value (time and reach) — shown as blank, not 0
_OPTIONAL = {"plays", "reach_dl", "reach_plays", "reach_st", "cons_hrs", "avg_min",
             "watch_hrs", "listen_hrs", "avg_watch", "avg_listen"}


def _num(v):
    try:
        return float(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def load(path):
    rows = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                m = (r.get("MONTH") or "").strip()[:7]
                if not m:
                    continue
                g = lambda k: _num(r.get(k))
                row = {
                    "downloads": int(g("TOTAL DOWNLOADS") or g("DOWNLOADS")),
                    "streams": int(g("TOTAL STREAMS") or g("STREAMS")),
                    "plays": int(g("TOTAL STARTS")),
                    "reach_dl": int(g("UNIQUE LISTENERS FROM DOWNLOADS")),
                    "reach_plays": int(g("UNIQUE LISTENERS FROM STARTS")),
                    "reach_st": int(g("UNIQUE LISTENERS FROM STREAMS")),
                    "cons_hrs": round(g("TOTAL CONSUMPTION TIME") / 60, 1),       # stored in minutes
                    "avg_min": round(g("AVG CONSUMPTION TIME"), 1),
                    "watch_hrs": round(g("TOTAL FOREGROUND TIME") / 60, 1),
                    "listen_hrs": round(g("TOTAL BACKGROUND TIME") / 60, 1),
                    "avg_watch": round(g("AVG FOREGROUND TIME"), 2),
                    "avg_listen": round(g("AVG BACKGROUND TIME"), 2),
                }
                row = {k: (None if k in _OPTIONAL and not v else v) for k, v in row.items()}
                row["delivery"] = row["downloads"] + row["streams"]
                row["reach"] = ((row["reach_dl"] or 0) + (row["reach_st"] or 0)) or None
                t = (row["watch_hrs"] or 0) + (row["listen_hrs"] or 0)
                row["watch_pct"] = round(row["watch_hrs"] / t, 4) if t and row["watch_hrs"] else None
                rows[m] = row
    return {"months": sorted(rows), "rows": rows}


def apply_to_extract(d, audio, months_key="months"):
    """Overwrite the tracker's downloads / streams with the Megaphone file (the paste is
    the source of truth) and recompute per-episode downloads. Months not in the file
    keep whatever the tracker had."""
    for i, m in enumerate(d[months_key]):
        r = audio["rows"].get(m)
        if not r:
            continue
        d["l_total"][i] = r["downloads"]
        d["spotify"][i] = r["streams"]
        ep = d["l_eps"][i] if i < len(d["l_eps"]) else None
        d["l_perep"][i] = round(r["downloads"] / ep) if ep else None


def series(audio, eps_by_month=None):
    """Every metric as a list aligned to audio['months'] (oldest-first), plus a summary
    of the latest month and the month before it."""
    eps_by_month = eps_by_month or {}
    months = audio["months"]
    rows = audio["rows"]
    keys = ["downloads", "streams", "delivery", "plays", "reach", "reach_dl", "reach_st",
            "cons_hrs", "avg_min", "watch_hrs", "listen_hrs", "watch_pct"]
    out = {k: [rows[m][k] for m in months] for k in keys}
    out["months"] = months
    out["eps"] = [eps_by_month.get(m) for m in months]
    out["perep"] = [round(rows[m]["downloads"] / e) if e else None for m, e in zip(months, out["eps"])]
    out["latest"] = months[-1] if months else None
    out["prev"] = months[-2] if len(months) > 1 else None
    return out
