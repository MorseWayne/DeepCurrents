# 🌊 DeepCurrents

**AI-Powered Global Intelligence & Macro Strategy Engine**

> *"News is the foam on the surface; trends are the currents deep below."*

English | [**中文**](./README.md)

DeepCurrents is an automated intelligence system that aggregates **70+ global sources**, runs an **article-first ingestion -> dedup -> event building -> ranking -> event-centric report orchestration** pipeline, and synthesizes the resulting event cards into **structured daily macro strategy reports** using Multi-Agent LLM reasoning.

---

## ✨ Highlights

- **Multi-Agent Orchestration**: Parallel reasoning by **Macro Analyst** (geopolitical/macro focus) and **Sentiment Analyst** (market tone), synthesized by a **Market Strategist** (CIO-level synthesis).
- **70+ curated sources** with 4-tier credibility scoring (T1–T4).
- **Real-time Market Ingestion**: Integrates `yfinance` to fetch live prices for Gold, Crude Oil, S&P 500, etc., for "Expectation Gap" analysis.
- **Prediction Feedback Loop**: Automatically records AI outlooks and triggers backtested scoring (0-100) after 24h based on actual price movements.
- **Async High Performance**: 100% Python 3.10+ architecture based on `asyncio` and `aiohttp` for massive parallel collection.
- **Article-First Compression**: Exact / near / semantic dedup plus event building compress noisy article streams into reportable events.
- **Multi-channel Delivery**: Rich-card notifications to Feishu (Lark) and Telegram Markdown.

---

## 🚀 Quick Start

### Prerequisites

- **Python** >= 3.10
- **uv** (Recommended) or pip
- **Docker Engine / Docker Desktop + docker compose** (recommended for local PostgreSQL / Qdrant / Redis / RSSHub)
- An AI API key compatible with the OpenAI interface
- Event Intelligence runtime dependencies:
  - PostgreSQL
  - Qdrant
  - Redis

### 1. Clone

```bash
git clone https://github.com/your-username/DeepCurrents.git
cd DeepCurrents
```

### 2. Initialize Environment

We recommend using [uv](https://github.com/astral-sh/uv) for blazing fast dependency management:

```bash
# Install dependencies and create venv automatically
uv pip install -r requirements.txt
```

*Or use standard commands: `python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`*

### 3. Configure

Copy `.env.example` to `.env` and fill in your configuration:

```bash
cp .env.example .env
# Edit .env and fill in AI + Event Intelligence runtime settings
```

Minimum runtime settings:

```env
AI_API_KEY=your_openai_api_key
EVENT_INTELLIGENCE_ENABLED=true
EVENT_INTELLIGENCE_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/deepcurrents
EVENT_INTELLIGENCE_QDRANT_URL=http://localhost:6333
EVENT_INTELLIGENCE_REDIS_URL=redis://localhost:6379/0
```

If `EVENT_INTELLIGENCE_ENABLED=false`, collection and report entrypoints stay fail-closed and do not fall back to the old article-level pipeline.

### 4. Start Local Infrastructure

```bash
# Local development mode: infra in containers, app on the host
docker compose up -d postgres qdrant redis rsshub
docker compose ps
```

Host-mode defaults:

- PostgreSQL: `localhost:5432`
- Qdrant: `localhost:6333`
- Redis: `localhost:6379`
- RSSHub: `localhost:1200` (optional but strongly recommended)

### 5. Run

```bash
uv run -m src.main
```

Manual report generation:

```bash
uv run -m src.run_report
uv run -m src.run_report --no-push
uv run -m src.run_report --report-only
```

`uv run -m src.run_report --report-only` only works if event-intelligence data already exists in PostgreSQL.

### 6. Test

```bash
uv run pytest
```

---

## 🐳 Local Deployment Modes

DeepCurrents now has two supported local deployment paths.

### Mode A: Host Development

Use this when you want to edit Python code locally while keeping infrastructure containerized.

```bash
# 1. Start local infra
docker compose up -d postgres qdrant redis rsshub

# 2. Run the app on the host
uv run -m src.main
```

Your `.env` should keep host addresses:

```env
EVENT_INTELLIGENCE_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/deepcurrents
EVENT_INTELLIGENCE_QDRANT_URL=http://localhost:6333
EVENT_INTELLIGENCE_REDIS_URL=redis://localhost:6379/0
RSSHUB_BASE_URL=http://localhost:1200
```

### Mode B: Full Stack via Compose

Use this when you want a fully containerized local stack.

```bash
docker compose up -d --build
docker compose logs -f deep-currents
```

Stop everything:

```bash
docker compose down
```

In full-stack compose mode, the `deep-currents` container automatically overrides runtime addresses to service names:

- `postgresql://postgres:postgres@postgres:5432/deepcurrents`
- `http://qdrant:6333`
- `redis://redis:6379/0`
- `http://rsshub:1200`

### Important Runtime Behavior

1. If `EVENT_INTELLIGENCE_ENABLED=false`, collection and report entrypoints stay fail-closed.
2. If PostgreSQL / Qdrant / Redis are not reachable, the app will not fall back to the old article-level pipeline.
3. `RSSHUB_BASE_URL` is not required for the core runtime, but it is strongly recommended for Telegram / Chinese extension feeds.

---

## 🏗️ Architecture

```
                     ┌────────────────────┐
                     │    RSS Sources     │
                     │   (70+ Global)     │
                     └────────┬───────────┘
                              │ Hourly Ingestion
                              ▼
┌──────────────────────────────────────────────────────┐
│              DeepCurrents Engine v2.2 (Python)       │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────────┐   │
│  │Collector │─▶│ Circuit   │─▶│ Article Repository   │   │
│  │(aiohttp) │  │ Breaker   │  │ + Feature Extractor  │   │
│  └──────────┘  └───────────┘  └──────────┬───────────┘   │
│                                          │               │
│                           ┌──────────────▼─────────────┐ │
│                           │ Semantic Dedup + Event     │ │
│                           │ Builder + Enrichment       │ │
│                           └──────────────┬─────────────┘ │
│                                          │               │
│  ┌──────────┐               ┌────────────▼────────────┐  │
│  │ yfinance │──────────────▶│ Ranking / Evidence /    │  │
│  │ (market) │               │ Briefs / Report Context │  │
│  └─────┬────┘               └────────────┬────────────┘  │
│        │                                  │              │
│        │          ┌──────────┐    ┌──────▼──────┐       │
│        └─────────▶│ Scorer   │◀──▶│ Multi-Agent │       │
│                   │ (Backtest)│    │ Orchestrator│       │
│                   └──────────┘    └──────┬──────┘       │
│                                           │              │
│                                     Structured Report    │
│                                           ▼              │
│                                      ┌────┴────┐         │
│                                      │Notifier │         │
│                                      └────┬────┘         │
│                                           │              │
│                                 ┌─────────┴─────────┐    │
│                                 ▼                   ▼    │
│                              Feishu              Telegram
└──────────────────────────────────────────────────────┘
```

---

## 📅 Scheduling

| Task | Default Cron | Module | Description |
| :--- | :--- | :--- | :--- |
| **Collection** | `0 * * * *` | `collector` | Hourly article-first ingestion, feature extraction, dedup, and event updates |
| **Report** | `0 8 * * *` | `engine` | Daily event-centric synthesis and delivery |
| **Scoring** | Every 4h | `scorer` | Backtest past AI predictions against real prices |

---

## 🧪 Integration Testing

Use `pytest` to verify component connectivity and logical consistency:

```bash
uv run pytest                     # Run all tests
uv run pytest tests/test_collector.py   # Test collector only
uv run pytest tests/test_report_orchestrator.py  # Test event-centric report orchestration
uv run pytest tests/test_scorer.py      # Test scoring system only
```

### 🛠️ Diagnostic Test Tools

In addition to automated tests, this project provides a diagnostic tool `src/test_tools.py` designed for daily maintenance to quickly verify production connectivity:

```bash
# Show help
uv run python -m src.test_tools --help

# Concurrently verify connectivity for all 70+ sources (RSS/RSSHub)
uv run python -m src.test_tools --rss

# Test AI (LLM) service connectivity and response
uv run python -m src.test_tools --llm

# Send a test report to Feishu and Telegram (Verify Webhook/Bot config)
uv run python -m src.test_tools --feishu
uv run python -m src.test_tools --tg

# Test yfinance market data ingestion
uv run python -m src.test_tools --market

# Run all diagnostic tests at once
uv run python -m src.test_tools --all
```

### 💡 Advanced Testing Tips

- **Verbose Mode**: `uv run pytest -s` (Display prints and logs during tests).
- **Exit on First Failure**: `uv run pytest -x`.
- **Run Specific Tests**: `uv run pytest -k "collector"` (Matches test file or function names).
- **Skip Slow Tests**: For tests involving AI generation, use `uv run pytest -m "not slow"` (requires marker configuration).

### 🌐 Networking, Proxy & Telegram Access

Telegram (Bot API and RSS sources) might be restricted in some regions. Please note:

1.  **Notification Proxy**: This system has integrated `HTTPS_PROXY` support. If Telegram delivery fails, configure your proxy address (HTTP/HTTPS/SOCKS5 supported) in `.env`.
2.  **RSSHub Tuning**: 
    - The public instance `rsshub.app` has strict rate limits for Telegram/Twitter and often returns 403.
    - **Self-Hosting Recommended**: Start the local infra stack via `docker compose up -d postgres qdrant redis rsshub` and make sure at least `rsshub + redis` are healthy.
    - **Configuration**: Set `RSSHUB_BASE_URL=http://localhost:1200` in `.env` to enable automatic URL rewriting.

---

## 🔧 Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.10+ | Core language |
| **Runtime** | asyncio | Non-blocking async runtime |
| **AI SDK** | OpenAI Python SDK | Multi-provider support + structured JSON |
| **Primary Stores** | PostgreSQL + Qdrant + Redis | Event Intelligence runtime persistence, vector search, cache |
| **Prediction Store** | SQLite | Local `predictions` persistence |
| **Validation** | Pydantic v2 | Strict runtime type checking |
| **Scheduling** | APScheduler | Robust task management |
| **Logging** | Loguru | Modern structured logging |
| **NLP** | Jieba + NLTK | Multi-language tokenization |

---

## 📄 License

ISC

---

*Powered by DeepCurrents Intelligence Engine v2.2*
