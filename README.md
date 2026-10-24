# 市長你給我聽好了 (Taipei Speaks Up) Crawler

Crawler for [taipeispeaksup.org](https://taipeispeaksup.org/) — a civic participation platform where Taipei residents submit issues and suggestions to the city government through LINE.

## Data Sources

The site publishes data as static JSON files on a public Google Cloud Storage bucket (`taipei-speaks-up-feed-prod`). Three feed types are available:

| Feed | URL | Description |
|------|-----|-------------|
| `voices.json` | `feed/v1/voices.json` | Topic summaries with counts and sample voices (4 per topic, 6 per district) |
| `heatmap.json` | `feed/v1/heatmap.json` | Per-district aggregated stats: issue counts, visitor counts, top mood, topic breakdown |
| `live.json` | `feed/v1/live.json` | Real-time counters: submissions today, total published, cumulative participants |
| `stage/*.json` | `feed/v1/stage/{epoch}.json` | Individual voice entries in 60-second segments, used for the stage visualization |

### Stats (as of 2026-10-24)

- **70,888** total published issues
- **37,830** cumulative participants
- **12** districts (all Taipei administrative districts)
- **18** topic categories
- **~43,000** stage segment files covering ~30 days

### Topic Categories

| Code | Name | Count |
|------|------|-------|
| environment | 環境 | 16,289 |
| traffic | 交通 | 15,398 |
| repair | 城市修繕 | 6,585 |
| education | 教育 | 3,756 |
| labor | 勞工 | 2,755 |
| childcare | 育兒 | 2,512 |
| culture | 文化 | 2,345 |
| safety | 公共安全 | 1,704 |
| foodsafety | 食安 | 1,316 |
| eldercare | 長照 | 1,107 |
| sports | 體育 | 1,050 |
| economy | 經濟 | 914 |
| medical | 醫療 | 829 |
| tourism | 觀光 | 781 |
| publicorder | 治安 | 598 |
| cityadmin | 市政 | 5,766 |
| diplomacy | 外交 | 295 |
| other | 其他 | 6,888 |

### Districts

中正 (Zhongzheng), 大同 (Datong), 萬華 (Wanhua), 信義 (Xinyi), 南港 (Nangang), 內湖 (Neihu), 大安 (Daan), 中山 (Zhongshan), 松山 (Songshan), 士林 (Shilin), 北投 (Beitou), 文山 (Wenshan)

## Voice Data Schema

Each voice entry extracted from stage files contains:

```json
{
  "queue_number": 33200,
  "district": "neihu",
  "topic": "環境",
  "mood": "worried",
  "content": "台北市舊宗路及堤頂大道中間的污水處理廠周邊持續發出惡臭這個問題是否能夠解決？",
  "display_name": "內湖代表 洪榮震（若妍家城爸爸）",
  "is_replay": true,
  "segment_epoch": 1790263800
}
```

| Field | Description |
|-------|-------------|
| `queue_number` | Unique issue number |
| `district` | Taipei district (English code) |
| `topic` | Topic category (Chinese) |
| `mood` | Submitter mood: `angry`, `worried`, `caring`, `hopeful`, `positive` |
| `content` | The issue text |
| `display_name` | Submitter display name |
| `is_replay` | Whether this is a replayed entry on the stage |
| `segment_epoch` | Unix timestamp of the stage segment |

## Usage

```bash
python3 crawler.py
```

Output is saved to `data/`:

- `data/voices.json` — topic summaries
- `data/heatmap.json` — district heatmap data
- `data/live.json` — live counters
- `data/all_voices.json` — all unique voices extracted from stage segments
- `data/all_voices.csv` — same data in CSV format
- `data/stage/` — cached raw stage segment files

Re-runs skip already-downloaded stage files (cached in `data/stage/`).

## Notes

- The stage feed contains voices shown on the animated "stage" visualization — these are replayed samples, not all 70K+ submissions. The full dataset is only accessible through the LINE submission system.
- The public feed refreshes every 5 minutes for voices and every 30 seconds for live counters.
- No authentication is required; all data is publicly accessible.

## License

Data belongs to the Taipei City Government / taipeispeaksup.org.
