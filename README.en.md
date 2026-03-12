# 🌊 DeepCurrents

**AI-Powered Global Intelligence & Macro Strategy Engine**

> *"News is the foam on the surface; trends are the currents deep below."*

English | [**中文**](./README.md)

DeepCurrents is an automated intelligence system that aggregates **35+ top-tier global news sources** (Reuters, Bloomberg, AP, BBC, CNBC, and more), classifies threats, clusters related events, detects trending signals — and synthesizes everything into **structured daily macro strategy reports** using LLM reasoning.

Built for macro investors, geopolitical analysts, and anyone who needs to cut through noise to find the signal.

---

## ✨ Highlights

- **35+ curated sources** across geopolitics, macro economics, energy, central banks, cybersecurity — with 4-tier credibility scoring (T1–T4)
- **Multi-Agent Collaboration**: Orchestrates **Macro Analyst** (geopolitical/macro focus), **Sentiment Analyst** (market tone focus), and **Market Strategist** (CIO-level synthesis) for superior report depth.
- **Real-time Market Ingestion**: Integrates `yfinance` to fetch live prices for Gold, Crude Oil, S&P 500, etc., enabling AI to perform "Expectation Gap" analysis.
- **Prediction Feedback Loop**: Automatically records AI asset outlooks and triggers backtested scoring (0-100) after 24h based on actual price movements.
- **Fuzzy deduplication** — trigram Dice + word Jaccard similarity catches the same story reported differently across outlets, powered by inverted index for speed
- **News clustering** — fragments auto-group into macro events via Union-Find, picking the most authoritative source as the cluster headline
- **Trend detection** — rolling-window keyword spike detection with 7-day baseline comparison and cross-source validation
- **Threat classification** — cascading keyword rules with composite escalation (e.g., military keywords + geopolitical target → auto-upgrade to CRITICAL)
- **Full-text extraction** — Mozilla Readability enriches T1/T2 sources beyond RSS summaries
- **Token budget management** — intelligently allocates LLM context: 70% news, 15% clusters, 15% trends, filling by priority until budget exhausted
- **Circuit breaker** — failing sources auto-cool-down with configurable thresholds, preventing cascade failures
- **AI fallback chain** — primary → backup LLM provider auto-switch with timeout handling
- **Notification retry** — exponential backoff delivery to Feishu (Lark) and Telegram in parallel (`Promise.allSettled`)
- **Multi-language tokenization** — native CJK support via `Intl.Segmenter` for Chinese, Japanese, Korean headline clustering and trend detection
- **RSSHub-ready** — non-standard sources (Telegram channels, etc.) via RSSHub with self-hosted instance support
- **Docker-ready** — one-command deploy with Docker Compose (DeepCurrents + RSSHub + Redis)
- **Fully configurable** — 15+ tunable parameters via `.env`, zero code changes needed

---

## 🚀 Quick Start

### Prerequisites

- **Node.js** >= 18.x
- **npm** >= 9.x
- An AI API key compatible with the OpenAI interface (OpenAI, Groq, OpenRouter, etc.)

### 1. Clone

```bash
git clone https://github.com/your-username/DeepCurrents.git
cd DeepCurrents
```

### 2. Install

```bash
npm install
```

### 3. Configure

Copy `.env.example` to `.env` and fill in your configuration:

```bash
cp .env.example .env
```

Edit `.env` (required fields):

```env
# AI Configuration
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_API_KEY=your_openai_api_key
AI_MODEL=gpt-4o

# AI Fallback (optional, recommended for availability)
AI_FALLBACK_URL=https://api.groq.com/openai/v1/chat/completions
AI_FALLBACK_KEY=your_groq_api_key
AI_FALLBACK_MODEL=llama-3.1-70b-versatile

# Feishu / Lark Webhook (optional)
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your_bot_id

# Telegram Bot (optional)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

> See `.env.example` for the full list of 15+ tunable parameters including cron schedules, dedup thresholds, token budgets, and more.

### 4. Run

```bash
npm start
```

After startup, the engine will automatically:

1. **Immediately** run a data collection cycle
2. **Hourly** ingest the latest global news (configurable via `CRON_COLLECT`)
3. **Daily at 08:00** synthesize and deliver the macro strategy report (configurable via `CRON_REPORT`)
4. **Daily at 03:00** clean up expired data (configurable via `CRON_CLEANUP`)

**Manual one-shot report** (collect → analyze → generate → deliver):

```bash
npm run report                                    # Full pipeline
npm run report -- --no-push                       # Preview: skip delivery
npm run report -- --report-only                   # Use existing data only (skip collection)
npm run report -- --json                          # JSON output
npm run report -- --output data/reports/today.md  # Write to file
npm run report -- --help                          # Show help
```

> Logs go to stderr, reports to stdout. Redirect with: `npm run report > report-$(date +%Y%m%d).md`

---

## 🐳 Deployment Modes

DeepCurrents supports two modes, differing in how `isRssHub`-flagged sources (Telegram channels, etc.) fetch data:

| Mode | Use Case | RSSHub Behavior |
|------|----------|-----------------|
| **Direct** | Quick test, local dev | Uses public `rsshub.app` instance (may be rate-limited) |
| **Self-hosted RSSHub** | Production | Uses `RSSHUB_BASE_URL` for stability and speed |

### Mode A: Direct (No Docker Required)

Leave `RSSHUB_BASE_URL` unset — all RSSHub sources will use the public `rsshub.app` instance:

```bash
npm run report
npm start
```

### Mode B: Self-hosted RSSHub

**Option 1: Local dev — Docker for RSSHub only, code runs on host**

```bash
docker compose up -d rsshub redis

RSSHUB_BASE_URL=http://localhost:1200 npm run report
RSSHUB_BASE_URL=http://localhost:1200 npm start
```

You can also add `RSSHUB_BASE_URL=http://localhost:1200` to your `.env` file.

**Option 2: Production — Full stack via Docker Compose**

```bash
docker compose up -d --build
docker compose logs -f deep-currents
```

The `docker-compose.yml` pre-configures `RSSHUB_BASE_URL=http://rsshub:1200` (internal network address), no extra setup needed.

```bash
docker compose down   # Stop and clean up
```

### Standalone Docker (Alternative)

```bash
docker build -t deep-currents .
docker run -d \
  --name deep-currents \
  --env-file .env \
  -v deep-currents-data:/app/data \
  --restart unless-stopped \
  deep-currents
```

> **How it works**: Sources marked `isRssHub: true` in `src/config/sources.ts` have URLs like `https://rsshub.app/...`. When `RSSHUB_BASE_URL` is set, the engine auto-replaces `rsshub.app` with your specified host. Standard RSS sources are unaffected.

---

## 🏗️ Architecture

```
              ┌─────────────────────┐
              │    RSS Sources      │
              │  (35+, tiered T1-T4)│
              └────────┬────────────┘
                       │  Hourly collection
                       ▼
┌──────────────────────────────────────────────────┐
│            DeepCurrents Engine v2.1              │
│                                                  │
│  Collector ──► Circuit Breaker ──► SQLite        │
│  (p-limit)     (auto cooldown)    (WAL mode)     │
│                                      │           │
│  Fuzzy Dedup ◄───────────────────────┤           │
│  (trigram + Jaccard inverted index)  │           │
│                                      ▼           │
│  Classifier ──► Clustering ──► Trending          │
│  (threat)       (Union-Find)   (spike detection) │
│                      │                           │
│                      ▼                           │
│               Multi-Agent Pipeline               │
│          (Macro + Sentiment + yfinance)          │
│                      │                           │
│                      ▼                           │
│               Market Strategist                  │
│          (Synthesis + Prediction Scoring)         │
│                      │                           │
│                      ▼                           │
│  Feishu ◄──── Notifier ────► Telegram            │
│  (rich card)  (exp. backoff)  (Markdown)         │
└──────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
DeepCurrents/
├── src/
│   ├── monitor.ts              # Core engine: scheduling, collection, reporting
│   ├── run-report.ts           # One-shot report CLI
│   ├── test-tools.ts           # Integration test harness
│   ├── test-sources.ts         # Full source verification
│   ├── config/
│   │   ├── sources.ts          # RSS source definitions (tier, type, risk)
│   │   └── settings.ts         # Centralized config (all params from .env)
│   ├── services/
│   │   ├── ai.service.ts       # LLM analysis with token budget management
│   │   ├── db.service.ts       # SQLite persistence & fuzzy title dedup
│   │   ├── classifier.ts       # Threat classifier (cascading + escalation)
│   │   ├── clustering.ts       # News clustering (Jaccard + Union-Find)
│   │   ├── trending.ts         # Trend detection (rolling window + baseline)
│   │   └── circuit-breaker.ts  # RSS source circuit breaker
│   └── utils/
│       ├── tokenizer.ts        # Multi-language tokenizer (Intl.Segmenter)
│       └── extractor.ts        # Full-text extraction (Readability)
├── data/                       # Runtime: intel.db (auto-created)
├── Dockerfile                  # Multi-stage Alpine build
├── docker-compose.yml          # Full stack orchestration
├── .env.example                # Config template with all parameters
├── package.json
├── tsconfig.json
└── README.md
```

---

## 📊 Report Format

The daily report is structured JSON generated by the LLM, containing:

| Field | Description |
|-------|-------------|
| `executiveSummary` | One-line summary of the day's global macro narrative |
| `globalEvents` | Major events with event type and threat level annotations |
| `economicAnalysis` | In-depth macro economic analysis (300+ words) |
| `investmentTrends` | Asset allocation signals with confidence scores (0–100) |
| `trendingAlerts` | Surging keywords with market impact assessment |
| `riskAssessment` | Global risk landscape evaluation (200+ words) |
| `sourceAnalysis` | Source quality and coverage gap analysis (optional) |

Reports are delivered via Feishu (Lark) rich cards and Telegram Markdown in parallel.

---

## 📰 Sources

Currently **35 sources** configured (standard RSS + RSSHub), covering:

| Category | Representative Sources | Count |
|----------|----------------------|-------|
| 🌍 Geopolitics | Reuters World, AP News, BBC World, Politico, TASS | 14 |
| 📈 Economics & Finance | Bloomberg, Reuters Business, CNBC, FT, gCaptain | 8 |
| 🏛️ Government | Federal Reserve, White House, Pentagon | 3 |
| 🔬 Think Tanks | CrisisWatch, UN News, WHO, Atlantic Council, IAEA | 6 |
| 🌏 Asia-Pacific | BBC Asia, Nikkei Asia | 2 |
| ⛽ Energy | Oil & Gas, Nuclear Energy | 2 |
| 🔒 Cyber & Tech | CISA Advisories, MIT Tech Review | 2 |

> Sources are fully extensible in `src/config/sources.ts`. Each source supports `tier`, `type`, `propagandaRisk`, and `isRssHub` flags.

---

## 🧪 Testing

A built-in test harness verifies component connectivity. Run individually or combined:

```bash
npm test                # Run all tests
npm run test:rss        # RSS source connectivity
npm run test:llm        # LLM API
npm run test:verify     # Full source verification
npm run test:feishu     # Feishu notification
npm run test:telegram   # Telegram notification
```

| Category | Description |
|----------|-------------|
| `rss` | Test top 5 RSS source connectivity |
| `test:verify` | Full source verification (connectivity + content) |
| `classifier` | Threat classifier |
| `clustering` | News clustering |
| `trending` | Trend keyword detection |
| `llm` | AI API call + JSON response validation |
| `feishu` | Feishu webhook connectivity |
| `telegram` | Telegram bot connectivity |

---

## 📅 Scheduling

| Task | Default Cron | Env Var | Description |
|------|-------------|---------|-------------|
| **Collection** | `0 * * * *` | `CRON_COLLECT` | Hourly scan all RSS sources, dedup and store |
| **Report** | `0 8 * * *` | `CRON_REPORT` | Daily synthesis and delivery |
| **Cleanup** | `0 3 * * *` | `CRON_CLEANUP` | Purge expired data (default 30 days) |

---

## 🔧 Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | TypeScript | Type safety |
| Runtime | Node.js 18+ / ts-node | Direct TS execution |
| AI | OpenAI Compatible API | Multi-provider support + fallback chain |
| Database | SQLite (better-sqlite3) | WAL mode, lightweight persistence |
| RSS | rss-parser | Standard RSS/Atom parsing |
| Scheduling | node-cron | Crontab-like scheduling |
| Concurrency | p-limit | Request throttling |
| Logging | Pino + pino-pretty | Structured colored logs |
| HTTP | Axios | HTTP client |
| Validation | Zod | Runtime type validation |
| Tokenization | Intl.Segmenter | CJK + English tokenization |
| Container | Docker | Multi-stage Alpine build |

---

## ⚙️ Configuration

All parameters configurable via `.env` with sensible defaults:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CRON_COLLECT` | `0 * * * *` | Collection frequency |
| `CRON_REPORT` | `0 8 * * *` | Report generation schedule |
| `CRON_CLEANUP` | `0 3 * * *` | Data cleanup schedule |
| `RSS_TIMEOUT_MS` | `15000` | Per-source fetch timeout (ms) |
| `RSS_CONCURRENCY` | `10` | Concurrent fetch limit |
| `CB_MAX_FAILURES` | `3` | Circuit breaker failure threshold |
| `CB_COOLDOWN_MS` | `300000` | Circuit breaker cooldown (ms) |
| `AI_TIMEOUT_MS` | `90000` | AI API timeout (ms) |
| `AI_MAX_CONTEXT_TOKENS` | `8000` | LLM context token budget |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.55` | Title dedup similarity threshold |
| `DEDUP_HOURS_BACK` | `24` | Dedup lookback window (hours) |
| `REPORT_MAX_NEWS` | `500` | Max news items per report |
| `DATA_RETENTION_DAYS` | `30` | Data retention period (days) |
| `CLUSTER_SIMILARITY_THRESHOLD` | `0.3` | Clustering Jaccard threshold |
| `NOTIFY_MAX_RETRIES` | `3` | Notification max retry attempts |
| `NOTIFY_BASE_DELAY_MS` | `1000` | Retry base delay (exponential backoff) |

---

## 🗺️ Roadmap

**Completed (v2.2):**

- [x] Multi-Agent Pipeline (Macro/Sentiment/Strategist)
- [x] yfinance Market Data Integration
- [x] Prediction Accuracy Scorer
- [x] Tiered sources & circuit breaker fault tolerance
- [x] Threat classification pipeline
- [x] News clustering (fragments → macro events)
- [x] Trend keyword detection
- [x] AI fallback chain
- [x] Telegram delivery
- [x] Fuzzy title deduplication
- [x] Token budget management
- [x] Notification retry with exponential backoff
- [x] Externalized configuration
- [x] Graceful shutdown
- [x] Docker deployment
- [x] CJK tokenization

**Planned:**

- [ ] Semantic dedup (embedding-based vector similarity)
- [ ] Auto-translation for foreign language sources
- [ ] Sentiment index tracking
- [ ] Custom watchlist keywords
- [ ] Email subscription
- [ ] Observability (Prometheus metrics + health check API)
- [ ] Historical report archiving & quality review

---

## 📄 License

ISC

---

*Powered by DeepCurrents Intelligence Engine v2.1*
