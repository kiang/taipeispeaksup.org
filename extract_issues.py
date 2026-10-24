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

    seen = set()
    daily = defaultdict(list)

    for sf in stage_files:
        with open(sf) as f:
            data = json.load(f)

        epoch = data.get("segment_epoch", 0)
        dt = datetime.fromtimestamp(epoch, tz=TW)
        time_str = dt.strftime("%H:%M:%S")
        date_str = dt.strftime("%Y-%m-%d")

        for entry in data.get("schedule", []):
            qn = entry.get("queue_number")
            if not qn or qn in seen:
                continue
            seen.add(qn)
            daily[date_str].append({
                "time": time_str,
                "issue": (entry.get("content") or "").replace("\n", " "),
                "nickname": entry.get("display_name", ""),
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
