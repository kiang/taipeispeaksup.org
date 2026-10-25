#!/usr/bin/env python3
"""
Generate a report from all crawled issues.

1. Stats & keyword analysis (no LLM)
2. Per-topic LLM summarization via local Ollama (gemma4)
3. Final synthesis into a Markdown report
"""

import csv
import json
import re
import sys
import time
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import jieba

DATA_DIR = Path(__file__).parent / "data"
STAGE_DIR = DATA_DIR / "stage"
REPORT_DIR = DATA_DIR / "report"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma4:e4b-128k"

TW = timezone(timedelta(hours=8))

STOP_WORDS = set(
    "的 了 是 在 有 我 不 人 都 也 就 要 會 可以 能 很 這 那 讓 被 把 跟 和 與 "
    "及 或 但 還 到 從 給 用 對 為 上 下 中 大 小 多 少 好 一 二 三 四 五 六 七 八 九 十 "
    "個 些 每 各 其 他 她 它 們 你 您 自己 什麼 怎麼 這個 那個 如何 是否 可否 "
    "希望 覺得 認為 應該 請 市長 台北 台北市 臺北 臺北市 問題 建議 ".split()
)

TOPIC_NAMES = {
    "交通": "traffic", "環境": "environment", "城市修繕": "repair",
    "教育": "education", "勞工": "labor", "育兒": "childcare",
    "文化": "culture", "公共安全": "safety", "食安": "foodsafety",
    "長照": "eldercare", "體育": "sports", "經濟": "economy",
    "醫療": "medical", "觀光": "tourism", "治安": "publicorder",
    "市政": "cityadmin", "外交": "diplomacy", "其他": "other",
}


def load_all_issues():
    """Load all unique issues from stage files, preferring non-replay entries."""
    issues = {}
    for sf in sorted(STAGE_DIR.glob("*.json")):
        with open(sf) as f:
            data = json.load(f)
        for e in data.get("schedule", []):
            qn = e.get("queue_number")
            if not qn:
                continue
            is_replay = e.get("is_replay", False)
            if qn not in issues or (issues[qn]["is_replay"] and not is_replay):
                issues[qn] = {
                    "queue_number": qn,
                    "district": e.get("district", ""),
                    "topic": e.get("topic", ""),
                    "mood": e.get("mood", ""),
                    "content": (e.get("content") or "").replace("\n", " ").strip(),
                    "display_name": e.get("display_name", ""),
                    "starts_at": e.get("starts_at", ""),
                    "is_replay": is_replay,
                }
    return list(issues.values())


def keyword_analysis(issues_by_topic):
    """Run jieba segmentation and return top keywords per topic."""
    results = {}
    for topic, issues in issues_by_topic.items():
        words = Counter()
        for issue in issues:
            segs = jieba.cut(issue["content"])
            for w in segs:
                w = w.strip()
                if len(w) >= 2 and w not in STOP_WORDS and not re.match(r"^[\d\s\W]+$", w):
                    words[w] += 1
        results[topic] = words.most_common(30)
    return results


def stats_analysis(all_issues):
    """Compute aggregate statistics."""
    by_topic = defaultdict(list)
    by_district = defaultdict(list)
    by_mood = Counter()
    by_date = Counter()

    for issue in all_issues:
        by_topic[issue["topic"]].append(issue)
        by_district[issue["district"]].append(issue)
        by_mood[issue["mood"]] += 1
        if issue["starts_at"]:
            try:
                dt = datetime.fromisoformat(issue["starts_at"]).astimezone(TW)
                by_date[dt.strftime("%Y-%m-%d")] += 1
            except ValueError:
                pass

    return {
        "total": len(all_issues),
        "by_topic": {t: len(v) for t, v in by_topic.items()},
        "by_district": {d: len(v) for d, v in by_district.items()},
        "by_mood": dict(by_mood),
        "by_date": dict(sorted(by_date.items())),
        "issues_by_topic": dict(by_topic),
    }


def ollama_generate(prompt, temperature=0.3):
    """Call local Ollama API."""
    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 131072},
    }).encode()
    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read())
    return result.get("response", "")


def summarize_topic(topic_name, issues, keywords):
    """Ask LLM to summarize one topic's issues."""
    kw_str = "、".join(w for w, _ in keywords[:20])

    # Batch issues - take all if under 800, otherwise sample evenly
    if len(issues) <= 800:
        batch = issues
    else:
        step = len(issues) / 800
        batch = [issues[int(i * step)] for i in range(800)]

    issues_text = "\n".join(
        f"- {iss['content']}" for iss in batch if iss["content"]
    )

    prompt = f"""你是一位分析台北市民意見的研究員。以下是台北市民透過「市長你給我聯好了」平台提交的「{topic_name}」類別意見，共 {len(batch)} 則（總共 {len(issues)} 則）。

高頻關鍵詞：{kw_str}

請用繁體中文分析這些意見，產出以下內容：
1. **主要訴求**（列出 5-10 個最常見的具體訴求，每個附上約出現比例）
2. **熱點地點**（如果有反覆提到的具體地點、路段、設施）
3. **民眾情緒**（整體情緒傾向與代表性的表達方式）
4. **代表性意見**（引用 3-5 則最具代表性的原文）

意見列表：
{issues_text}

請直接輸出分析結果，不要重述任務說明。"""

    return ollama_generate(prompt)


def synthesize_report(topic_summaries, stats):
    """Final synthesis across all topics."""
    summaries_text = ""
    for topic, summary in topic_summaries.items():
        count = stats["by_topic"].get(topic, 0)
        summaries_text += f"\n### {topic}（{count:,} 則）\n{summary}\n"

    mood_str = "、".join(f"{m}: {c:,}" for m, c in sorted(stats["by_mood"].items(), key=lambda x: -x[1]))
    district_str = "、".join(f"{d}: {c:,}" for d, c in sorted(stats["by_district"].items(), key=lambda x: -x[1]))

    prompt = f"""你是一位撰寫市政分析報告的研究員。以下是台北市「市長你給我聽好了」平台 {stats['total']:,} 則市民意見的各類別分析摘要。

整體統計：
- 情緒分布：{mood_str}
- 行政區分布：{district_str}

各類別分析：
{summaries_text}

請用繁體中文撰寫一份完整的總結報告，包含：
1. **摘要**（200字內，最關鍵的發現）
2. **市民最關注的五大議題**（跨類別歸納）
3. **各行政區特色**（哪些區有獨特的關注焦點）
4. **情緒分析**（市民的整體態度與期望）
5. **政策建議**（根據民意歸納出 5-8 項具體施政方向）

請直接輸出報告，格式使用 Markdown。"""

    return ollama_generate(prompt, temperature=0.2)


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    print("Loading all issues from stage files...")
    all_issues = load_all_issues()
    print(f"  Loaded {len(all_issues):,} unique issues")

    # Stats
    print("\nComputing statistics...")
    stats = stats_analysis(all_issues)
    with open(REPORT_DIR / "stats.json", "w") as f:
        json.dump({k: v for k, v in stats.items() if k != "issues_by_topic"},
                  f, ensure_ascii=False, indent=2)

    # Keywords
    print("Running keyword analysis...")
    jieba.setLogLevel(20)
    keywords = keyword_analysis(stats["issues_by_topic"])
    with open(REPORT_DIR / "keywords.json", "w") as f:
        json.dump({t: kws for t, kws in keywords.items()}, f, ensure_ascii=False, indent=2)

    print("\nStats summary:")
    print(f"  Total issues: {stats['total']:,}")
    for topic, count in sorted(stats["by_topic"].items(), key=lambda x: -x[1]):
        kws = "、".join(w for w, _ in keywords.get(topic, [])[:5])
        print(f"  {topic}: {count:,}  top words: {kws}")

    # LLM summarization per topic
    print("\n--- LLM Summarization ---")
    topic_summaries = {}

    # Check for cached summaries
    cache_path = REPORT_DIR / "topic_summaries.json"
    cached = {}
    if cache_path.exists():
        with open(cache_path) as f:
            cached = json.load(f)
        print(f"  Found {len(cached)} cached topic summaries")

    topics_sorted = sorted(stats["issues_by_topic"].keys(),
                           key=lambda t: -len(stats["issues_by_topic"][t]))

    for i, topic in enumerate(topics_sorted):
        issues = stats["issues_by_topic"][topic]
        kws = keywords.get(topic, [])

        if topic in cached:
            print(f"  [{i+1}/{len(topics_sorted)}] {topic} ({len(issues):,}) — cached")
            topic_summaries[topic] = cached[topic]
            continue

        print(f"  [{i+1}/{len(topics_sorted)}] {topic} ({len(issues):,}) — calling Ollama...")
        t0 = time.time()
        try:
            summary = summarize_topic(topic, issues, kws)
            topic_summaries[topic] = summary
            # Save incrementally
            with open(cache_path, "w") as f:
                json.dump({**cached, **topic_summaries}, f, ensure_ascii=False, indent=2)
            elapsed = time.time() - t0
            print(f"    Done in {elapsed:.0f}s")
        except Exception as e:
            print(f"    Error: {e}")
            topic_summaries[topic] = f"(分析失敗: {e})"

    # Final synthesis
    print("\nGenerating final synthesis report...")
    t0 = time.time()
    synthesis = synthesize_report(topic_summaries, stats)
    print(f"  Done in {time.time() - t0:.0f}s")

    # Write final report
    report_path = REPORT_DIR / "report.md"

    report = f"""# 台北市民意見分析報告

> 資料來源：[市長你給我聽好了](https://taipeispeaksup.org/)
> 分析日期：{datetime.now(TW).strftime('%Y-%m-%d')}
> 總意見數：{stats['total']:,} 則

---

{synthesis}

---

## 附錄：各類別詳細分析

"""
    for topic in topics_sorted:
        count = len(stats["issues_by_topic"][topic])
        kws = "、".join(w for w, _ in keywords.get(topic, [])[:10])
        report += f"### {topic}（{count:,} 則）\n\n"
        report += f"**高頻關鍵詞：** {kws}\n\n"
        report += topic_summaries.get(topic, "(無分析)") + "\n\n---\n\n"

    with open(report_path, "w") as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    start = time.time()
    main()
    print(f"\nTotal time: {time.time() - start:.0f}s")
