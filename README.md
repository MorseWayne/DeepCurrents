# 🌊 DeepCurrents (深流)

**AI 驱动的全球情报聚合与宏观策略引擎**

> *新闻是水面上的浪花，趋势是深处的暗流。*

**[English](./README.en.md)** | 中文

DeepCurrents 是一个自动化的全球情报聚合与宏观研报生成系统。它从 35+ 个全球顶级资讯源（Reuters、Bloomberg、AP News、BBC、CNBC 等）中采集碎片化信息，经由威胁分类、事件聚类、趋势检测等多维分析管线，最终通过 **Multi-Agent (多智能体)** 协作推理引擎合成为结构化的每日宏观策略研报。

本项目专为宏观投资者、地缘政治分析师及需要从海量噪音中提取信号的专业人士打造。

---

## ✨ 核心特性

- **多维聚合**: 整合 35+ 全球顶级资讯源，覆盖地缘政治、宏观经济、能源大宗、央行政策、网络安全等维度，4 级可信度分级（T1-T4）。
- **多智能体协作**: 引入 **Macro Analyst** (地缘宏观专家) 与 **Sentiment Analyst** (市场情绪专家) 并行推理，由 **Market Strategist** (首席策略官) 汇总整合，提升研报深度。
- **实时行情注入**: 集成 `yfinance` 插件，自动获取黄金、原油、标普 500 等核心资产的实时价格，辅助 AI 进行逻辑与价格的“预期差”分析。
- **预测评分闭环**: 自动保存 AI 对资产趋势的研判，并在事后基于真实走势自动回测评分（0-100分），实现 AI 决策质量的持续量化。
- **异步高性能**: 全量 Python 3.10+ 重构，基于 `asyncio` 和 `aiohttp` 的非阻塞 I/O 设计，支撑大规模并发采集。
- **正文增强采集**: 对高优先级信源自动尝试网页正文提取（BeautifulSoup4），缓解 RSS 摘要过短导致的信息丢失。
- **高可靠性**:
  - **模糊标题去重**（trigram + Jaccard），有效合并同一事件的不同措辞报道。
  - **RSS 熔断器**，连续失败源自动冷却，防止级联故障。
  - **AI 回退链**，主/备提供商自动切换。
- **多通道分发**: 支持飞书富文本卡片和 Telegram Bot 双通道并行投递。

---

## 🚀 快速启动

### 前置要求

- **Python** >= 3.10
- **uv** (推荐) 或 pip
- 一个支持 OpenAI 兼容接口的 AI API Key

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

# 飞书 Webhook (可选)
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your_bot_id

# Telegram Bot (可选)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. 启动引擎

```bash
# 启动常驻调度引擎 (定时执行采集、研报、评分)
uv run -m src.main
```

**手动触发全流程并输出每日研报**:

```bash
uv run -m src.run_report                                    # 完整流程 (采集 + 生成 + 推送)
uv run -m src.run_report --no-push                          # 预览模式：不推送、不标记已报告
uv run -m src.run_report --report-only                      # 仅用已有数据生成（跳过采集）
uv run -m src.run_report --json                             # 以 JSON 格式输出到终端
uv run -m src.run_report --output data/reports/today.md     # 写入文件
```

---

## 🐳 运行模式与部署

DeepCurrents 支持两种运行模式，区别在于 `is_rss_hub` 标记的信息源（Telegram 频道、华尔街见闻、财联社等）如何获取数据：


| 模式               | 适用场景      | RSSHub 源行为                       |
| ---------------- | --------- | -------------------------------- |
| **直连模式**         | 快速测试、本地开发 | 直接访问 `rsshub.app` 公共实例（可能限速或不稳定） |
| **自建 RSSHub 模式** | 生产部署、稳定运行 | 通过 `RSSHUB_BASE_URL` 指向自建实例，更快更稳 |


### 模式 A：直连模式（无需 Docker）

不设置 `RSSHUB_BASE_URL`，所有 RSSHub 源直接走 `rsshub.app` 公共实例：

```bash
uv run -m src.run_report
uv run -m src.main
```

### 模式 B：自建 RSSHub 模式

**方式一：本地开发 — Docker 只跑 RSSHub，代码在宿主机运行**

```bash
# 启动 RSSHub + Redis
docker compose up -d rsshub redis

# 本地运行，指向 Docker 中的 RSSHub
RSSHUB_BASE_URL=http://localhost:1200 uv run -m src.run_report
RSSHUB_BASE_URL=http://localhost:1200 uv run -m src.main
```

也可以将 `RSSHUB_BASE_URL=http://localhost:1200` 写入 `.env` 文件，避免每次手动传入。

**方式二：生产部署 — Docker Compose 一键拉起完整栈**

```bash
docker compose up -d --build
docker compose logs -f deep-currents
```

Compose 模式下 `docker-compose.yml` 已预设 `RSSHUB_BASE_URL=http://rsshub:1200`（容器内网地址），无需额外配置。

```bash
docker compose down   # 停止并清理容器
```

### 单容器 Docker 部署（备用）

```bash
docker build -t deep-currents .
docker run -d \
  --name deep-currents \
  --env-file .env \
  -v deep-currents-data:/app/data \
  --restart unless-stopped \
  deep-currents
```

> **工作原理**：`src/config/sources.py` 中标记了 `is_rss_hub: True` 的源，URL 格式为 `https://rsshub.app/...`。当设置了 `RSSHUB_BASE_URL` 后，引擎会自动将 `rsshub.app` 替换为你指定的地址。未标记 `is_rss_hub` 的标准 RSS 源不受影响。

---

## 🏗️ 架构概览

```
                     ┌────────────────────┐
                     │    RSS Sources     │
                     │   (35+ 全球源)     │
                     │  T1/T2/T3/T4 分级  │
                     └────────┬───────────┘
                              │ 每小时采集
                              ▼
┌──────────────────────────────────────────────────────┐
│              DeepCurrents Engine v2.2 (Python)       │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │Collector │─▶│ Circuit   │─▶│ SQLite + 模糊去重 │  │
│  │(aiohttp) │  │ Breaker   │  │ (trigram+Jaccard) │  │
│  └──────────┘  └───────────┘  └────────┬─────────┘  │
│                                        │             │
│  ┌──────────┐  ┌───────────┐           │             │
│  │Classifier│  │ Clustering│◀──────────┤             │
│  │ (威胁)   │  │ (聚类)    │           │             │
│  └──────────┘  └─────┬─────┘           │             │
│  ┌──────────┐        │          ┌──────┴──────┐      │
│  │ yfinance │────────┴─────────▶│ Multi-Agent │      │
│  │ (行情)   │                   │ Pipeline    │      │
│  └─────┬────┘                   └──────┬──────┘      │
│        │                               │             │
│        │          ┌──────────┐      结构化研报       │
│        └─────────▶│ Scorer   │◀────────┴──────────┐  │
│                   │ (自动评分)│                   │  │
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

## 📅 任务调度

| 任务 | 默认 Cron | 模块 | 说明 |
| :--- | :--- | :--- | :--- |
| **数据采集** | `0 * * * *` | `collector` | 每小时扫描 RSS 源，去重入库 |
| **研报生成** | `0 8 * * *` | `engine` | 每天 08:00 合成情报，多智能体推理并推送 |
| **自动评分** | 每 4 小时 | `scorer` | 对历史预测进行真实行情回测评分 |
| **数据清理** | `0 3 * * *` | `db_service` | 每天 03:00 清理过期数据（默认保留 30 天） |

---

## 📰 信息源

当前已配置 **35 个**信息源，覆盖以下类别：


| 类别 | 代表源 | 数量 |
| :--- | :--- | :--- |
| 🌍 **地缘政治** | Reuters World, AP News, BBC World, Politico | 14 |
| 📈 **经济金融** | Bloomberg, Reuters Business, CNBC, FT | 8 |
| 🏛️ **政府央行** | Federal Reserve, White House, Pentagon | 3 |
| 🔬 **智库组织** | CrisisWatch, UN News, WHO, IAEA | 6 |
| ⛽ **能源大宗** | Oil & Gas Journal, World Nuclear News | 2 |
| 🔒 **网络科技** | CISA Advisories, MIT Tech Review | 2 |


---

## 📁 项目结构

```
DeepCurrents/
├── src/
│   ├── main.py                 # 常驻引擎入口，处理任务调度
│   ├── engine.py               # 核心协调器，定义业务流
│   ├── run_report.py           # 命令行手动触发工具
│   ├── config/
│   │   ├── sources.py          # 35+ 信息源配置与分级
│   │   └── settings.py         # 集中配置管理 (Pydantic)
│   ├── services/
│   │   ├── ai_service.py       # 多智能体推理流 (Macro/Sentiment/Strategist)
│   │   ├── db_service.py       # 异步 SQLite 交互与模糊去重算法
│   │   ├── collector.py        # 异步并发 RSS 采集
│   │   ├── classifier.py       # 威胁分类引擎 (关键词级联)
│   │   ├── clustering.py       # 新闻聚类引擎 (并查集)
│   │   ├── scorer.py           # 预测评分引擎 (回测逻辑)
│   │   └── notifier.py         # 飞书/Telegram 通知推送
│   └── utils/
│       ├── tokenizer.py        # 多语言分词 (Jieba + NLTK)
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
uv run pytest tests/test_ai_service.py  # 仅测试 AI 服务
uv run pytest tests/test_scorer.py      # 仅测试评分系统
```

### 🛠️ 运维拨测工具 (Test Tools)

除了自动化测试，本项目提供了一个专为日常运维设计的拨测工具 `src/test_tools.py`，支持快速验证生产环境的各项连通性：

```bash
# 查看帮助
uv run python -m src.test_tools --help

# 并发验证所有 35+ 个信息源 (RSS/RSSHub) 的联通性
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

1.  **推送代理**: 本系统已集成 `HTTPS_PROXY` 支持。如果 Telegram 推送失败，请在 `.env` 中配置代理地址（支持 HTTP/HTTPS/SOCKS5）。
2.  **RSSHub 调优**: 
    - 公共实例 `rsshub.app` 对 Telegram/Twitter 抓取限制极严，经常返回 403。
    - **强烈建议自建**: 使用 `docker compose up -d rsshub redis` 启动本地实例。
    - **配置指向**: 在 `.env` 中设置 `RSSHUB_BASE_URL=http://localhost:1200`，系统将自动完成 URL 替换。

---

## ⚙️ 核心参数调优

所有参数均在 `.env` 中配置，附带合理默认值：

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `HTTPS_PROXY` | `""` | 全局代理地址 (支持 http:// 或 socks5://) |
| `RSSHUB_BASE_URL` | `""` | 自建 RSSHub 地址 (例如 http://localhost:1200) |
| `AI_MAX_CONTEXT_TOKENS` | `16000` | AI 上下文 Token 预算 |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.55` | 标题去重相似度阈值 |
| `CLUSTER_SIMILARITY_THRESHOLD` | `0.3` | 新闻聚类 Jaccard 阈值 |
| `RSS_CONCURRENCY` | `10` | 异步采集并发限制 |
| `DATA_RETENTION_DAYS` | `30` | 数据库信息保留天数 |

---

## 📄 License

ISC | *Powered by DeepCurrents Intelligence Engine v2.2*
