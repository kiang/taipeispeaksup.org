#!/usr/bin/env python3
"""
Extract issues from cached stage files into daily CSV files.
Output: data/issues/{Y-m-d}.csv with columns: time, issue, nickname

Run crawler.py first to populate data/stage/.
"""

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
STAGE_DIR = DATA_DIR / "stage"
ISSUES_DIR = DATA_DIR / "issues"

TW = timezone(timedelta(hours=8))


def main():
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)

    stage_files = sorted(STAGE_DIR.glob("*.json"))
    if not stage_files:
        print("No stage files found. Run crawler.py first.")
        return

    print(f"Processing {len(stage_files):,} stage files...")

    # First pass: collect the best time for each queue_number.
    # Prefer the starts_at from non-replay entries (original submissions);
    # fall back to the earliest starts_at from replay entries.
    issues = {}

    for sf in stage_files:
        with open(sf) as f:
            data = json.load(f)

        for entry in data.get("schedule", []):
            qn = entry.get("queue_number")
            if not qn:
                continue

            starts_at = entry.get("starts_at", "")
            is_replay = entry.get("is_replay", False)

            if qn not in issues:
                issues[qn] = {
                    "starts_at": starts_at,
                    "is_replay": is_replay,
                    "content": (entry.get("content") or "").replace("\n", " "),
                    "display_name": entry.get("display_name", ""),
                }
            else:
                prev = issues[qn]
                if prev["is_replay"] and not is_replay:
                    prev["starts_at"] = starts_at
                    prev["is_replay"] = False
                elif prev["is_replay"] and is_replay and starts_at < prev["starts_at"]:
                    prev["starts_at"] = starts_at

    # Group by date
    daily = defaultdict(list)
    for qn, info in issues.items():
        if not info["starts_at"]:
            continue
        dt = datetime.fromisoformat(info["starts_at"]).astimezone(TW)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M:%S")
        daily[date_str].append({
            "time": time_str,
            "issue": info["content"],
            "nickname": info["display_name"],
        })

    for date_str in sorted(daily):
        rows = daily[date_str]
        rows.sort(key=lambda r: r["time"])
        path = ISSUES_DIR / f"{date_str}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["time", "issue", "nickname"])
            writer.writeheader()
            writer.writerows(rows)

    total = sum(len(v) for v in daily.values())
    print(f"Extracted {total:,} unique issues into {len(daily)} daily CSV files")
    for date_str in sorted(daily):
        print(f"  {date_str}.csv — {len(daily[date_str]):,} issues")


if __name__ == "__main__":
    main()
