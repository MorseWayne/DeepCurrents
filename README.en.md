# 🌊 DeepCurrents

**AI-Powered Global Intelligence & Macro Strategy Engine**

> *"News is the foam on the surface; trends are the currents deep below."*

English | [**中文**](./README.md)

DeepCurrents is an automated intelligence system that aggregates **35+ top-tier global news sources** (Reuters, Bloomberg, AP, BBC, CNBC, and more), classifies threats, clusters related events, detects trending signals — and synthesizes everything into **structured daily macro strategy reports** using Multi-Agent LLM reasoning.

---

## ✨ Highlights

- **Multi-Agent Orchestration**: Parallel reasoning by **Macro Analyst** (geopolitical/macro focus) and **Sentiment Analyst** (market tone), synthesized by a **Market Strategist** (CIO-level synthesis).
- **35+ curated sources** with 4-tier credibility scoring (T1–T4).
- **Real-time Market Ingestion**: Integrates `yfinance` to fetch live prices for Gold, Crude Oil, S&P 500, etc., for "Expectation Gap" analysis.
- **Prediction Feedback Loop**: Automatically records AI outlooks and triggers backtested scoring (0-100) after 24h based on actual price movements.
- **Async High Performance**: 100% Python 3.10+ architecture based on `asyncio` and `aiohttp` for massive parallel collection.
- **Multi-channel Delivery**: Rich-card notifications to Feishu (Lark) and Telegram Markdown.

---

## 🚀 Quick Start

### Prerequisites

- **Python** >= 3.10
- **uv** (Recommended) or pip
- An AI API key compatible with the OpenAI interface

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
# Edit .env and fill in AI_API_KEY, etc.
```

### 4. Run

```bash
uv run -m src.main
```

### 5. Test

```bash
uv run pytest
```

---

## 🏗️ Architecture

```
                     ┌────────────────────┐
                     │    RSS Sources     │
                     │   (35+ Global)     │
                     └────────┬───────────┘
                              │ Hourly Ingestion
                              ▼
┌──────────────────────────────────────────────────────┐
│              DeepCurrents Engine v2.2 (Python)       │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │Collector │─▶│ Circuit   │─▶│ SQLite + Fuzzy   │  │
│  │(aiohttp) │  │ Breaker   │  │ Deduplication    │  │
│  └──────────┘  └───────────┘  └────────┬─────────┘  │
│                                        │             │
│  ┌──────────┐  ┌───────────┐           │             │
│  │Classifier│  │ Clustering│◀──────────┤             │
│  │ (threat) │  │ (Union-Fn)│           │             │
│  └──────────┘  └─────┬─────┘           │             │
│  ┌──────────┐        │          ┌──────┴──────┐      │
│  │ yfinance │────────┴─────────▶│ Multi-Agent │      │
│  │ (market) │                   │ Pipeline    │      │
│  └─────┬────┘                   └──────┬──────┘      │
│        │                               │             │
│        │          ┌──────────┐      Structured       │
│        └─────────▶│ Scorer   │◀────────┴──────────┐  │
│                   │ (Backtest)│                   │  │
│                   └──────────┘             ┌─────▼─────┐
│                                            │  Notifier │
│                                            └─────┬─────┘
│                                                  │
│                                        ┌─────────┴─────────┐
│                                        ▼                   ▼
│                                     Feishu              Telegram
└──────────────────────────────────────────────────────┘
```

---

## 📅 Scheduling

| Task | Default Cron | Module | Description |
| :--- | :--- | :--- | :--- |
| **Collection** | `0 * * * *` | `collector` | Hourly scan all RSS sources, dedup and store |
| **Report** | `0 8 * * *` | `engine` | Daily synthesis and delivery |
| **Scoring** | Every 4h | `scorer` | Backtest past AI predictions against real prices |
| **Cleanup** | `0 3 * * *` | `db_service` | Purge expired data (default 30 days) |

---

## 🧪 Integration Testing

Use `pytest` to verify component connectivity and logical consistency:

```bash
uv run pytest                     # Run all tests
uv run pytest tests/test_collector.py   # Test collector only
uv run pytest tests/test_ai_service.py  # Test AI service only
uv run pytest tests/test_scorer.py      # Test scoring system only
```

### 🛠️ Diagnostic Test Tools

In addition to automated tests, this project provides a diagnostic tool `src/test_tools.py` designed for daily maintenance to quickly verify production connectivity:

```bash
# Show help
uv run python -m src.test_tools --help

# Concurrently verify connectivity for all 35+ sources (RSS/RSSHub)
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
    - **Self-Hosting Recommended**: Start a local instance via `docker compose up -d rsshub redis`.
    - **Configuration**: Set `RSSHUB_BASE_URL=http://localhost:1200` in `.env` to enable automatic URL rewriting.

---

## 🔧 Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Language** | Python 3.10+ | Core language |
| **Runtime** | asyncio | Non-blocking async runtime |
| **AI SDK** | OpenAI Python SDK | Multi-provider support + structured JSON |
| **Database** | aiosqlite | Async SQLite interaction |
| **Validation** | Pydantic v2 | Strict runtime type checking |
| **Scheduling** | APScheduler | Robust task management |
| **Logging** | Loguru | Modern structured logging |
| **NLP** | Jieba + NLTK | Multi-language tokenization |

---

## 📄 License

ISC

---

*Powered by DeepCurrents Intelligence Engine v2.2*
