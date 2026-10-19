"""
SR — copy the Schultz-side manual inputs back from the shared repo
==================================================================
Manual SR numbers (X, YouTube engaged views, Jordan's X …) are entered on the shared dashboard
(raindelaymedia/The-Schultz-Report), so they live in its schultz_report/data_sr/socials_sr.csv.
The daily workflow checks that repo out to _shared/ and runs this before the SR dashboard build, so
RDM's socials_sr.csv (and the Fanatics report) see the same numbers.

Rows for API-synced platforms (API_PLATFORMS) are never taken from the shared file — RDM owns those.
For every other row the shared value wins.

    python master/shows/schultz_report/pull_shared_inputs_sr.py [path/to/shared/socials_sr.csv]
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
OURS = os.path.join(HERE, "data_sr", "socials_sr.csv")
SHARED = os.path.join(ROOT, "_shared", "schultz_report", "data_sr", "socials_sr.csv")
API_PLATFORMS = {"INSTAGRAM", "TIKTOK"}      # keep in step with sync_socials.py (sr) and rdm_data.RDM_PLATFORMS


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    shared = sys.argv[1] if len(sys.argv) > 1 else SHARED
    if not os.path.exists(shared):
        print(f"No shared socials file at {shared} — nothing to pull")
        return
    ours = read(OURS)
    key = lambda r: (r["period"].strip(), r["platform"].strip().upper(), r["metric"].strip().upper())
    index = {key(r): r for r in ours}
    changed = []
    for r in read(shared):
        k = key(r)
        if k[1] in API_PLATFORMS or not (r.get("value") or "").strip():
            continue
        if k not in index:
            index[k] = {"period": k[0], "platform": k[1], "metric": k[2], "value": r["value"].strip()}
            changed.append((k, None, r["value"].strip()))
        elif index[k]["value"].strip() != r["value"].strip():
            changed.append((k, index[k]["value"], r["value"].strip()))
            index[k]["value"] = r["value"].strip()
    if not changed:
        print("Shared manual inputs: already in step")
        return
    rows = sorted(index.values(), key=lambda r: r["period"], reverse=True)
    with open(OURS, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["period", "platform", "metric", "value"], lineterminator="\r\n")
        w.writeheader()
        w.writerows({k: r[k] for k in ("period", "platform", "metric", "value")} for r in rows)
    for (p, pl, m), old, new in changed:
        print(f"  {p} {pl:<10} {m:<22} {old if old is not None else '—':>10} → {new}")
    print(f"✓ {len(changed)} manual value(s) pulled from the shared repo")


if __name__ == "__main__":
    main()
