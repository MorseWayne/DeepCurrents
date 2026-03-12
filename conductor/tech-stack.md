# Tech Stack: DeepCurrents (深流)

## 编程语言与核心环境
- **TypeScript**：核心开发语言，利用强类型特性确保复杂情报处理逻辑的稳健性。
- **Node.js**：异步驱动的运行时环境，适配高并发的资讯采集与处理场景。

## 数据基础设施与存储
- **SQLite (better-sqlite3)**：本地嵌入式数据库，用于存储全球资讯源、处理后的事件及生成的研报。
- **better-sqlite3**：高性能 Node.js 驱动，确保本地数据持久化的高效读写。

## 情报采集与处理管线
- **RSS Parser**：用于从 35+ 个全球顶级源中提取标准化 RSS 数据。
- **JSDOM & Mozilla Readability**：自动抓取并提取高质量的网页正文，填补 RSS 摘要的信息缺失。
- **Zod**：提供严密的数据 Schema 验证，确保在数据处理和 AI 推理前的结构完整性。

## AI 推理与分析逻辑
- **多智能体协作流 (Multi-Agent Pipeline)**：采用 Macro Analyst -> Sentiment Analyst -> Market Strategist 异步协作逻辑，实现深度宏观推演。
- **LLM Reasoning (OpenAI 兼容接口)**：核心 AI 引擎，驱动事件聚类、威胁分类、趋势检测及最终的研报合成。
- **Market Data Service**: 集成 `yfinance` (via Python 脚本)，为 AI 推理提供实时资产价格走势，辅助“预期差”分析。
- **自动评分引擎 (Scorer)**: 基于真实行情对历史预测进行事后验证与评分。

## 运维、调度与可观测性
- **Node-cron**：负责定时采集（CRON_COLLECT）、研报合成（CRON_REPORT）和数据清理（CRON_CLEANUP）。
- **Pino & Pino-pretty**：结构化日志系统，支持终端彩色输出与本地日志文件落盘。
- **Axios**：具备请求超时和重试逻辑合作的 HTTP 客户端。

---

## 🐍 提议的 Python 重写技术栈 (Proposed Python Stack)
*针对 100% Python 重写方案的选型映射*

| 组件 | Node.js / TypeScript | Python 替代方案 |
| :--- | :--- | :--- |
| **异步运行时** | Node.js Event Loop | `asyncio` |
| **网络请求** | `axios` / `rss-parser` | `aiohttp` (抓取) / `httpx` (API) |
| **并发控制** | `p-limit` | `asyncio.Semaphore` |
| **数据验证** | `Zod` | `Pydantic v2` |
| **数据库** | `better-sqlite3` | `aiosqlite` (异步) 或 `sqlite3` |
| **调度器** | `node-cron` | `APScheduler` (AsyncIOScheduler) |
| **分词/NLP** | `Intl.Segmenter` | `jieba` (中文) / `nltk` (英文) |
| **日志** | `Pino` | `structlog` 或 `loguru` |
| **AI 接口** | OpenAI SDK (JS) | OpenAI SDK (Python) |

