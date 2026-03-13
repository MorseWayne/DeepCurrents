# 🌊 DeepCurrents (深流)

**AI 驱动的全球情报聚合与宏观策略引擎**

> *新闻是水面上的浪花，趋势是深处的暗流。*

**[English](./README.en.md)** | 中文

DeepCurrents 是一个自动化的全球情报聚合与宏观研报生成系统。它从 `src/config/sources.py` 中配置的 **70+ 资讯源（当前 73 个）** 采集碎片化信息，经由 **article-first ingestion -> dedup -> event building -> ranking -> event-centric report orchestration** 主链路，将原始文章压缩为事件卡与主题卡，再通过 **Multi-Agent (多智能体)** 协作推理引擎生成结构化的每日宏观策略研报。

本项目专为宏观投资者、地缘政治分析师及需要从海量噪音中提取信号的专业人士打造。

---

## 📚 文档导航

- [docs/index.md](./docs/index.md): 当前文档入口与阅读顺序
- [docs/technical-design.md](./docs/technical-design.md): 当前系统架构与运行方式
- [docs/event-intelligence.md](./docs/event-intelligence.md): Event Intelligence 当前状态与边界
- [docs/iteration-plan.md](./docs/iteration-plan.md): 下一轮迭代优化计划
- [docs/archive/README.md](./docs/archive/README.md): 历史设计稿与 roadmap/backlog 归档

---

## ✨ 核心特性

- **多维聚合**: 整合 70+ 全球资讯源（当前 73 个），覆盖地缘政治、宏观经济、能源大宗、央行政策、网络安全等维度，4 级可信度分级（T1-T4）。
- **金融级多智能体协作**: 采用混合专家模型（MoE）架构，由 **Macro Analyst** (宏观专家)、**Sentiment Analyst** (情绪专家) 协同，经由 **Market Strategist** (首席策略官 CIO) 生成包含配对交易（Pair Trades）的策略初稿，最后由 **Risk Manager** (首席风险官 CRO) 完成逻辑挑战与审核。
- **深度宏观因子注入**: 自动集成 **VIX (波动率指数)**、**美债收益率曲线 (Yield Curve)** 等实时宏观锚点，为 AI 提供范式级别的定价背景。
- **金融资产精准映射**: 引入 LLM 驱动的实体富化，自动将模糊事件映射至具体标的 (Tickers/ETFs)，如 Brent, GC=F, SPY, QQQ 等。
- **正文增强采集**: 针对 T1/T2 级核心源实施激进的全文本提取流水线，配合 LLM 深度摘要（`llm_v1`），彻底告别短摘要带来的信息孤岛。
- **市场评分能力**: 已集成 `yfinance` 与 `PredictionScorer`，可对已落库预测进行回测评分（0-100 分）。

- **高可靠性**:
  - **article-first 去重**（exact / near / semantic），在文章入库后建立重复关系。
  - **事件归并与排序**，将碎片化文章压缩为可报告事件与主题。
  - **RSS 熔断器**，连续失败源自动冷却，防止级联故障。
  - **AI 回退链**，主/备提供商自动切换。
- **多通道分发**: 支持飞书富文本卡片和 Telegram Bot 双通道并行投递。

### ⚠️ 当前实现边界（请先了解）

- `AIService` 已使用 `json_object` 输出并增加 JSON 修复重试链路；极端情况下仍可能修复失败。
- `investmentTrends` 到 `predictions` 的自动落库优先使用 `src/config/asset_symbols.json` 映射；未命中时会自动搜索可用 symbol（仍可能因低置信度或超时而跳过）。
- `scorer` 默认采用演示窗口（预测后 10 秒可评分），生产环境建议改为更长窗口（例如 12h/24h）。

---

## 🚀 快速启动

### 前置要求

- **Python** >= 3.10
- **uv** (推荐) 或 pip
- **Docker Engine / Docker Desktop + docker compose**（推荐，用于本地拉起 PostgreSQL / Qdrant / Redis / RSSHub）
- 一个支持 OpenAI 兼容接口的 AI API Key
- Event Intelligence 运行时依赖:
  - PostgreSQL
  - Qdrant
  - Redis

### 1. 初始化环境

```bash
# 克隆仓库
git clone https://github.com/MorseWayne/DeepCurrents.git
cd DeepCurrents

# 使用 uv 极速安装依赖 (自动创建虚拟环境)
uv pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件（必填项）：

```env
# AI 配置
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_API_KEY=your_openai_api_key
AI_MODEL=gpt-4o

# Event Intelligence Runtime
EVENT_INTELLIGENCE_ENABLED=true
EVENT_INTELLIGENCE_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/deepcurrents
EVENT_INTELLIGENCE_QDRANT_URL=http://localhost:6333
EVENT_INTELLIGENCE_REDIS_URL=redis://localhost:6379/0

# 飞书 Webhook (可选)
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your_bot_id

# Telegram Bot (可选)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. 启动本地基础设施

```bash
# 本地开发模式：只启动基础设施，app 在宿主机运行
docker compose up -d postgres qdrant redis rsshub
```

### 4. 启动前检查

```bash
docker compose ps
```

宿主机模式下，至少确认以下地址可达：

- PostgreSQL: `localhost:5432`
- Qdrant: `localhost:6333`
- Redis: `localhost:6379`
- RSSHub: `localhost:1200`（可选，但强烈推荐）

### 5. 启动引擎

```bash
# 启动常驻调度引擎 (定时执行采集、研报、评分)
uv run -m src.main
```

若 `EVENT_INTELLIGENCE_ENABLED=false` 或相关存储未配置，采集与报告入口会 `fail-closed`，不会再回退到旧文章级链路。

**手动触发全流程并输出每日研报**:

```bash
uv run -m src.run_report                                    # 完整流程 (采集 + 生成 + 推送)
uv run -m src.run_report --no-push                          # 预览模式：不推送、不标记已报告
uv run -m src.run_report --report-only                      # 仅用已有数据生成（跳过采集）
uv run -m src.run_report --report-only --force              # 强制生成：忽略最近一次报告时间窗口
uv run -m src.run_report --json                             # 以 JSON 格式输出到终端
uv run -m src.run_report --output data/reports/today.md     # 写入文件
```

`uv run -m src.run_report --report-only` 只适用于数据库中已经存在 event-intelligence 数据的场景，不再依赖旧 SQLite 新闻缓存。
如需忽略最近一次报告时间窗口并基于现有数据强制重生成，可使用 `--force`。

---

## 🐳 运行模式与部署

当前正式本地部署只保留两条路径。

### 方式 A：宿主机开发模式

适用场景：

- 本地调试 Python 代码
- 需要频繁改动 `src/`
- 希望基础设施容器化，app 进程在宿主机运行

步骤：

```bash
# 1. 启动基础设施
docker compose up -d postgres qdrant redis rsshub

# 2. 确认容器正常
docker compose ps

# 3. 在宿主机运行 app
uv run -m src.main
```

如需手动生成研报：

```bash
uv run -m src.run_report
uv run -m src.run_report --no-push
uv run -m src.run_report --report-only
uv run -m src.run_report --report-only --force
```

宿主机模式下，`.env` 中应保持以下地址：

```env
EVENT_INTELLIGENCE_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/deepcurrents
EVENT_INTELLIGENCE_QDRANT_URL=http://localhost:6333
EVENT_INTELLIGENCE_REDIS_URL=redis://localhost:6379/0
RSSHUB_BASE_URL=http://localhost:1200
# 如需代理，宿主机模式继续使用本机回环地址
# HTTPS_PROXY=http://127.0.0.1:7890
```

### 方式 B：Compose 全栈模式

适用场景：

- 想直接拉起完整本地栈
- 不需要在宿主机上频繁调试 app 代码

步骤：

```bash
docker compose up -d --build
docker compose logs -f deep-currents
```

停止：

```bash
docker compose down
```

Compose 全栈模式下：

- `deep-currents` 容器会自动使用容器内地址
- `.env` 中可以继续保留 `localhost` 版本的宿主机地址
- 如需给容器代理出网，使用 `DOCKER_HTTPS_PROXY`，不要把 `127.0.0.1` 直接传进容器
- compose 会覆盖为：
  - `postgresql://postgres:postgres@postgres:5432/deepcurrents`
  - `http://qdrant:6333`
  - `redis://redis:6379/0`
  - `http://rsshub:1200`

Compose 代理示例：

```env
DOCKER_HTTPS_PROXY=http://host.docker.internal:7890
```

说明：

- `docker-compose.yml` 已为 `rsshub` 和 `deep-currents` 注入 `host.docker.internal:host-gateway`
- 在 Linux 上也可直接用宿主机局域网 IP 代替 `host.docker.internal`
- 采集器会自动让 `rsshub` / `localhost` / 私有网段地址绕过代理，避免容器内访问本地 RSSHub 时被错误送进代理

### 启动前必须知道的事

1. `EVENT_INTELLIGENCE_ENABLED=false` 时，系统不会回退旧文章级主链路。
2. 只配置 AI key、但不启动 PostgreSQL / Qdrant / Redis，采集和报告都会 fail-closed。
3. `RSSHUB_BASE_URL` 不是正式主链路的必填项，但对 Telegram / 中文扩展源强烈推荐。
4. `src/config/sources.py` 中 `is_rss_hub=True` 的源会自动从 `https://rsshub.app/...` 改写到 `RSSHUB_BASE_URL`。

---

## 🏗️ 架构概览

```
                     ┌────────────────────┐
                     │    RSS Sources     │
                     │   (70+ 全球源)     │
                     │  T1/T2/T3/T4 分级  │
                     └────────┬───────────┘
                              │ 每小时采集
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
│  │ (评分)   │               │ Briefs / Report Context │  │
│  └─────┬────┘               └────────────┬────────────┘  │
│        │                                  │              │
│        │          ┌──────────┐    ┌──────▼──────┐       │
│        └─────────▶│ Scorer   │◀──▶│ Multi-Agent │       │
│                   │ (自动评分)│    │ Orchestrator│       │
│                   └──────────┘    └──────┬──────┘       │
│                                           │              │
│                                     结构化研报            │
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

*注：`Multi-Agent Orchestrator` 默认从 `asset_symbols.json` 自动挑选一组 symbol 注入实时行情上下文（可通过 `AI_USE_REALTIME_MARKET_CONTEXT` 关闭）；`yfinance` 也用于评分模块。*

---

## 📅 任务调度

| 任务 | 默认 Cron | 模块 | 说明 |
| :--- | :--- | :--- | :--- |
| **数据采集** | `0 * * * *` | `collector` | 每小时扫描 RSS 源，执行 article-first 入库、特征提取、去重与事件更新 |
| **研报生成** | `0 8 * * *` | `engine` | 每天 08:00 基于事件卡与主题卡生成 event-centric 研报并推送 |
| **自动评分** | 每 4 小时 | `scorer` | 对 `predictions` 表中待评分记录做行情回测 |

---

## 📰 信息源

当前 `src/config/sources.py` 已配置 **73 个**信息源（会持续变化），包含：

- 原生 RSS 源（Reuters/AP/BBC/Fed/CISA 等）
- RSSHub 扩展源（Telegram 频道、中文财经/媒体、Twitter/X 用户等）
- 按 `tier=1..4` 与 `type`（wire/gov/market/intel/mainstream/other）进行质量标注
- 可通过 `RSSHUB_BASE_URL` 一键切换到自建 RSSHub


---

## 📁 项目结构

```
DeepCurrents/
├── src/
│   ├── main.py                 # 常驻引擎入口，处理任务调度
│   ├── engine.py               # 核心协调器，定义业务流
│   ├── run_report.py           # 命令行手动触发工具
│   ├── config/
│   │   ├── sources.py          # 70+ 信息源配置与分级
│   │   └── settings.py         # 集中配置管理 (Pydantic)
│   ├── services/
│   │   ├── collector.py                 # 异步并发 RSS 采集与 article-first ingestion
│   │   ├── article_repository.py        # 文章持久化边界
│   │   ├── article_feature_extractor.py # embedding / feature 持久化
│   │   ├── semantic_deduper.py          # exact / near / semantic dedup
│   │   ├── event_builder.py             # 文章归并为事件
│   │   ├── event_ranker.py              # 事件排序
│   │   ├── report_context_builder.py    # 事件/主题 brief 组装
│   │   ├── report_orchestrator.py       # event-centric 报告编排
│   │   ├── ai_service.py                # 共用 AI 能力与预测持久化
│   │   ├── prediction_repository.py     # SQLite prediction 存储
│   │   ├── scorer.py                    # 预测评分引擎 (回测逻辑)
│   │   └── notifier.py                  # 飞书/Telegram 通知推送
│   └── utils/
│       ├── tokenizer.py        # 多语言分词 (Jieba + 规则分词)
│       ├── market_data.py      # yfinance 行情集成接口
│       └── extractor.py        # 网页正文增强提取
├── tests/                      # 20+ 集成与单元测试用例
├── Dockerfile                  # 基于 uv 的极速构建镜像
└── docker-compose.yml          # 全栈编排 (DeepCurrents + RSSHub + Redis)
```

---

## 🧪 集成测试

使用 `pytest` 验证各组件的联通性与逻辑一致性：

```bash
uv run pytest                     # 运行全部测试
uv run pytest tests/test_collector.py   # 仅测试采集器
uv run pytest tests/test_report_orchestrator.py  # 仅测试 event-centric 报告编排
uv run pytest tests/test_scorer.py      # 仅测试评分系统
```

### 🛠️ 运维拨测工具 (Test Tools)

除了自动化测试，本项目提供了一个专为日常运维设计的拨测工具 `src/test_tools.py`，支持快速验证生产环境的各项连通性：

```bash
# 查看帮助
uv run python -m src.test_tools --help

# 并发验证所有 70+ 个信息源 (RSS/RSSHub) 的联通性
uv run python -m src.test_tools --rss

# 测试 AI (LLM) 服务是否可用且响应正常
uv run python -m src.test_tools --llm

# 发送测试研报到飞书和 Telegram (验证 Webhook 和 Bot 配置)
uv run python -m src.test_tools --feishu
uv run python -m src.test_tools --tg

# 测试 yfinance 行情数据抓取
uv run python -m src.test_tools --market

# 一键运行全量拨测
uv run python -m src.test_tools --all
```

### 💡 高级测试技巧

- **详细日志模式**: `uv run pytest -s` (输出测试中的 print 和 log 内容)。
- **失败即停止**: `uv run pytest -x` (遇到第一个失败的测试用例立即停止)。
- **运行特定测试**: `uv run pytest -k "collector"` (运行所有文件名或函数名包含 "collector" 的测试)。
- **跳过慢速测试**: 部分涉及 AI 生成的测试较慢，可以使用 `uv run pytest -m "not slow"` (如果配置了 marker)。

### 🌐 网络、代理与 Telegram 访问

由于 Telegram (Bot API 及 RSS 源) 在部分地区访问受限，请务必注意：

1.  **宿主机代理**: 宿主机直接运行 `uv run -m src.main` 或 `src.test_tools` 时，使用 `HTTPS_PROXY`。例如：`HTTPS_PROXY=http://127.0.0.1:7890`
2.  **容器代理**: `docker compose` 全栈模式下，使用 `DOCKER_HTTPS_PROXY`。例如：`DOCKER_HTTPS_PROXY=http://host.docker.internal:7890`
3.  **RSSHub 调优**: 
    - 公共实例 `rsshub.app` 对 Telegram/Twitter 抓取限制极严，经常返回 403。
    - **强烈建议自建**: 使用 `docker compose up -d postgres qdrant redis rsshub` 启动完整本地基础设施，至少保证 `rsshub + redis` 可用。
    - **配置指向**: 在 `.env` 中设置 `RSSHUB_BASE_URL=http://localhost:1200`，系统将自动完成 URL 替换。
4.  **地址语义**: `127.0.0.1` 在容器里指向容器自己，不是宿主机；因此不要把宿主机回环代理直接复用给 compose 容器。

---

## ⚙️ 核心参数调优

所有参数均在 `.env` 中配置，附带合理默认值：

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `EVENT_INTELLIGENCE_ENABLED` | `true` | 启用正式 event-centric 采集与报告主链路 |
| `EVENT_INTELLIGENCE_POSTGRES_DSN` | `postgresql://postgres:postgres@localhost:5432/deepcurrents` | 宿主机模式下的 PostgreSQL 地址 |
| `EVENT_INTELLIGENCE_QDRANT_URL` | `http://localhost:6333` | 宿主机模式下的 Qdrant 地址 |
| `EVENT_INTELLIGENCE_REDIS_URL` | `redis://localhost:6379/0` | 宿主机模式下的 Redis 地址 |
| `HTTPS_PROXY` | `""` | 宿主机运行 app / test_tools 时使用的代理地址 |
| `DOCKER_HTTPS_PROXY` | `""` | `docker compose` 容器使用的代理地址，推荐 `http://host.docker.internal:7890` |
| `RSSHUB_BASE_URL` | `http://localhost:1200` | 自建 RSSHub 地址 |
| `AI_MAX_CONTEXT_TOKENS` | `128000` | AI 上下文 Token 预算 |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.55` | 标题去重相似度阈值 |
| `RSS_CONCURRENCY` | `10` | 异步采集并发限制 |

---

## 📄 License

ISC | *Powered by DeepCurrents Intelligence Engine v2.2*
