#!/usr/bin/env python3
"""
Crawler for https://taipeispeaksup.org/
Fetches all issues (voices) from the public GCS feed bucket.

Data sources:
  - feed/v1/voices.json  — topic summaries + sample voices
  - feed/v1/heatmap.json — per-district aggregated stats
  - feed/v1/stage/*.json — individual voice entries in 60-second segments
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "taipei-speaks-up-feed-prod"
FEED_BASE = f"https://storage.googleapis.com/{BUCKET}/feed/v1"
GCS_API = f"https://storage.googleapis.com/storage/v1/b/{BUCKET}/o"

OUTPUT_DIR = Path(__file__).parent / "data"
STAGE_DIR = OUTPUT_DIR / "stage"
MAX_RETRIES = 3
RETRY_DELAY = 2


def fetch_json(url, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            if attempt < retries - 1:
                print(f"  Retry {attempt + 1}/{retries - 1} for {url}: {e}")
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise


def list_stage_files():
    """List all stage file names from the GCS bucket using the JSON API."""
    files = []
    page_token = None
    while True:
        url = f"{GCS_API}?prefix=feed/v1/stage/&delimiter=/&maxResults=1000"
        if page_token:
            url += f"&pageToken={page_token}"
        data = fetch_json(url)
        for item in data.get("items", []):
            files.append(item["name"])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        print(f"  Listed {len(files)} stage files so far...")
    return files


def download_stage_file(name):
    """Download a single stage JSON file and return its parsed content."""
    filename = name.split("/")[-1]
    cache_path = STAGE_DIR / filename
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    url = f"https://storage.googleapis.com/{BUCKET}/{name}"
    data = fetch_json(url)
    with open(cache_path, "w") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def extract_voices_from_stage(stage_data):
    """Extract individual voice entries from a stage segment file."""
    voices = []
    for entry in stage_data.get("schedule", []):
        voices.append({
            "queue_number": entry.get("queue_number"),
            "district": entry.get("district"),
            "topic": entry.get("topic"),
            "mood": entry.get("mood"),
            "content": entry.get("content"),
            "display_name": entry.get("display_name"),
            "is_replay": entry.get("is_replay", False),
            "segment_epoch": stage_data.get("segment_epoch"),
        })
    return voices


def crawl():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch summary feeds
    print("Fetching voices.json...")
    voices_summary = fetch_json(f"{FEED_BASE}/voices.json")
    with open(OUTPUT_DIR / "voices.json", "w") as f:
        json.dump(voices_summary, f, ensure_ascii=False, indent=2)
    print(f"  Topics: {len(voices_summary['topics'])}")
    total_issues = sum(t["count"] for t in voices_summary["topics"])
    print(f"  Total issues across topics: {total_issues:,}")

    print("\nFetching heatmap.json...")
    heatmap = fetch_json(f"{FEED_BASE}/heatmap.json")
    with open(OUTPUT_DIR / "heatmap.json", "w") as f:
        json.dump(heatmap, f, ensure_ascii=False, indent=2)
    print(f"  Districts: {len(heatmap['districts'])}")

    print("\nFetching live.json...")
    live = fetch_json(f"{FEED_BASE}/live.json")
    with open(OUTPUT_DIR / "live.json", "w") as f:
        json.dump(live, f, ensure_ascii=False, indent=2)
    print(f"  Published total: {live['counts']['published_total']:,}")

    # 2. List all stage segment files
    print("\nListing stage segment files...")
    stage_files = list_stage_files()
    print(f"  Found {len(stage_files):,} stage files")

    if not stage_files:
        print("No stage files found.")
        return

    # 3. Download and extract voices from each stage file
    print("\nDownloading stage files and extracting voices...")
    all_voices = []
    seen_queue_numbers = set()
    errors = 0

    for i, name in enumerate(stage_files):
        if (i + 1) % 500 == 0 or i == 0:
            print(f"  Processing {i + 1}/{len(stage_files)}...")
        try:
            stage_data = download_stage_file(name)
            voices = extract_voices_from_stage(stage_data)
            for v in voices:
                qn = v["queue_number"]
                if qn and qn not in seen_queue_numbers:
                    seen_queue_numbers.add(qn)
                    all_voices.append(v)
        except Exception as e:
            errors += 1
            if errors <= 10:
                print(f"  Error on {name}: {e}")
            elif errors == 11:
                print("  (suppressing further errors)")

    print(f"\n  Total stage files processed: {len(stage_files):,}")
    print(f"  Unique voices extracted: {len(all_voices):,}")
    print(f"  Errors: {errors}")

    # 4. Sort by queue number and save
    all_voices.sort(key=lambda v: v.get("queue_number") or 0)

    output_path = OUTPUT_DIR / "all_voices.json"
    with open(output_path, "w") as f:
        json.dump(all_voices, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(all_voices):,} voices to {output_path}")

    # 5. Also save as CSV for convenience
    csv_path = OUTPUT_DIR / "all_voices.csv"
    import csv
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "queue_number", "district", "topic", "mood",
            "content", "display_name", "is_replay", "segment_epoch",
        ])
        writer.writeheader()
        writer.writerows(all_voices)
    print(f"Saved CSV to {csv_path}")

    # 6. Print summary
    print("\n=== Summary ===")
    print(f"Total unique voices: {len(all_voices):,}")
    districts = {}
    topics = {}
    for v in all_voices:
        d = v.get("district", "unknown")
        t = v.get("topic", "unknown")
        districts[d] = districts.get(d, 0) + 1
        topics[t] = topics.get(t, 0) + 1

    print("\nBy district:")
    for d, count in sorted(districts.items(), key=lambda x: -x[1]):
        print(f"  {d}: {count:,}")

    print("\nBy topic:")
    for t, count in sorted(topics.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count:,}")


if __name__ == "__main__":
    start = time.time()
    crawl()
    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s")
