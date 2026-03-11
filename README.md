# 🌊 DeepCurrents (深流)

**AI-Powered Macro Intelligence & Global Strategy Engine**

> "News is the foam on the surface; trends are the currents deep below."

DeepCurrents 是一个自动化的全球情报聚合与宏观研报生成系统。它借鉴了 `koala73/worldmonitor` 的顶级情报源筛选逻辑，通过 AI 深度合成，为专业投资者和宏观观察者提供每日定时的全球动态研判。

## 🌟 核心特性

- **多维聚合 (Multi-Source Aggregation)**: 整合 30+ 全球顶级资讯源（Reuters、Bloomberg、AP News、BBC、CNBC 等），覆盖地缘政治、宏观经济、能源大宗、央行政策、网络安全等维度，4 级可信度分级（T1-T4）。
- **深度合成 (Cognitive Synthesis)**: 利用 LLM 推理，在碎片化信息中提取"主线"。新闻自动聚类为宏观事件，趋势关键词实时检测，多维上下文注入 AI 生成深度研报。
- **投资视角 (Investment Oriented)**: 自动对大宗商品、股市、外汇、债券等资产类别进行看涨/看跌研判，附带置信度评分和风险评估。
- **高可靠性 (Industrial Grade)**:
  - **模糊标题去重**（trigram + Jaccard 双重检测），有效合并同一事件的不同措辞报道。
  - **RSS 熔断器**，连续失败源自动冷却，防止级联故障。
  - **AI 回退链**，主/备提供商自动切换。
  - **通知重试**（指数退避），防止网络抖动导致研报丢失。
  - **Token 预算管理**，按信息优先级分配 LLM 上下文空间。
  - **优雅退出**（SIGTERM/SIGINT），安全关停所有定时任务。
- **多通道分发 (Multi-Channel Notification)**: 支持飞书富文本卡片和 Telegram Bot 双通道并行投递。
- **多语言支持**: 分词器基于 `Intl.Segmenter`，原生支持中文、日文、韩文标题的聚类和趋势检测。
- **全面可配置**: 所有阈值、调度时间、超时参数均可通过 `.env` 调整，无需改代码。

## 📁 项目结构

```
deep-currents/
├── src/
│   ├── monitor.ts              # 核心引擎入口，调度数据采集与研报生成
│   ├── test-tools.ts           # 集成测试工具，支持分类测试各组件联通性
│   ├── config/
│   │   ├── sources.ts          # RSS 信息源配置（分级、分类、宣传风险标注）
│   │   └── settings.ts         # 集中配置模块（所有参数从 .env 读取）
│   ├── services/
│   │   ├── ai.service.ts       # LLM 深度分析服务，Token 预算管理
│   │   ├── db.service.ts       # SQLite 持久化、模糊标题去重
│   │   ├── classifier.ts       # 威胁分类器（关键词级联 + 复合升级）
│   │   ├── clustering.ts       # 新闻聚类（Jaccard + 并查集）
│   │   ├── trending.ts         # 趋势关键词检测（滚动窗口 + 基线比对）
│   │   └── circuit-breaker.ts  # RSS 源熔断器
│   └── utils/
│       └── tokenizer.ts        # 多语言分词器（Intl.Segmenter）
├── data/                       # 运行时自动创建，存放 intel.db
├── Dockerfile                  # 两阶段构建，生产级 Docker 镜像
├── .dockerignore
├── .env.example                # 环境变量模板（含完整调优参数说明）
├── package.json
├── tsconfig.json
└── README.md
```

## 🚀 快速启动

### 前置要求

- **Node.js** >= 18.x
- **npm** >= 9.x
- 一个支持 OpenAI 兼容接口的 AI API Key（推荐 OpenAI、Groq 或 OpenRouter）

### 1. 克隆仓库

```bash
git clone https://github.com/your-username/deep-currents.git
cd deep-currents
```

### 2. 安装依赖

```bash
npm install
```

### 3. 配置环境变量

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

# AI 回退（可选，推荐配置不同提供商以提高可用性）
AI_FALLBACK_URL=https://api.groq.com/openai/v1/chat/completions
AI_FALLBACK_KEY=your_groq_api_key
AI_FALLBACK_MODEL=llama-3.1-70b-versatile

# 飞书 Webhook（可选）
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your_bot_id

# Telegram Bot（可选）
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

> 完整的可调优参数列表见 `.env.example`，包括 Cron 调度时间、去重阈值、Token 预算等 15+ 项配置。

### 4. 启动引擎

```bash
npm start
# 或: npx ts-node src/monitor.ts
```

引擎启动后将自动执行：

1. **立即执行一次**数据采集
2. **每小时整点**自动抓取最新全球资讯（可通过 `CRON_COLLECT` 配置）
3. **每天 08:00**自动合成并投递每日研报（可通过 `CRON_REPORT` 配置）
4. **每天 03:00**自动清理过期数据（可通过 `CRON_CLEANUP` 配置）

### 5. Docker 部署（可选）

```bash
docker build -t deep-currents .
docker run -d \
  --name deep-currents \
  --env-file .env \
  -v deep-currents-data:/app/data \
  --restart unless-stopped \
  deep-currents
```

## 🧪 集成测试

提供独立的测试工具，用于验证各组件的联通性。支持按类别单独或组合测试。

```bash
# 运行全部测试
npm test

# 仅测试 RSS 信息源联通性
npm run test:rss

# 仅测试 LLM 服务
npm run test:llm

# 组合测试多个类别
npx ts-node src/test-tools.ts rss llm

# 测试飞书/Telegram 推送
npm run test:feishu
npm run test:telegram

# 查看帮助
npx ts-node src/test-tools.ts --help
```

**可用测试类别：**

| 类别         | 说明                                   |
| ------------ | -------------------------------------- |
| `rss`        | 测试前 5 个 RSS 信息源的抓取联通性     |
| `classifier` | 测试威胁分类器                         |
| `clustering` | 测试新闻聚类                           |
| `trending`   | 测试趋势关键词检测                     |
| `llm`        | 测试 AI API 调用及 JSON 格式返回       |
| `feishu`     | 发送飞书测试消息，验证 Webhook 联通性  |
| `telegram`   | 发送 Telegram 测试消息，验证 Bot 配置  |

## 📅 任务调度

| 任务         | 默认 Cron     | 环境变量        | 说明                                             |
| ------------ | ------------- | --------------- | ------------------------------------------------ |
| **数据采集** | `0 * * * *`   | `CRON_COLLECT`  | 每小时整点扫描所有 RSS 源，新增条目入库并去重    |
| **研报生成** | `0 8 * * *`   | `CRON_REPORT`   | 每天 08:00 合成全量情报，生成深度研报            |
| **数据清理** | `0 3 * * *`   | `CRON_CLEANUP`  | 每天 03:00 清理过期数据（默认保留 30 天）        |

## 🏗️ 架构概览

```
                     ┌────────────────────┐
                     │    RSS Sources     │
                     │   (30+ 全球源)     │
                     │  T1/T2/T3/T4 分级  │
                     └────────┬───────────┘
                              │ 每小时采集
                              ▼
┌──────────────────────────────────────────────────────┐
│              DeepCurrents Engine v2.1                │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │Collector │─▶│ Circuit   │─▶│ SQLite + 模糊去重 │  │
│  │(p-limit) │  │ Breaker   │  │ (trigram+Jaccard) │  │
│  └──────────┘  └───────────┘  └────────┬─────────┘  │
│                                        │             │
│  ┌──────────┐  ┌───────────┐           │             │
│  │Classifier│  │ Clustering│◀──────────┤             │
│  │ (威胁)   │  │ (聚类)    │           │             │
│  └──────────┘  └─────┬─────┘           │             │
│  ┌──────────┐        │          ┌──────┴──────┐      │
│  │Trending  │────────┼─────────▶│ AI Service  │      │
│  │ (趋势)   │        │          │(Token 预算) │      │
│  └──────────┘        │          └──────┬──────┘      │
│                      │                 │             │
│                      │          结构化研报            │
│                      │                 │             │
│  ┌──────────┐  ┌─────┴─────┐          │             │
│  │  飞书卡片 │◀─│ Notifier  │◀─────────┘             │
│  └──────────┘  │(指数退避)  │                        │
│  ┌──────────┐  └─────┬─────┘                        │
│  │ Telegram │◀───────┘                              │
│  └──────────┘                                        │
└──────────────────────────────────────────────────────┘
```

## 📊 研报输出格式

每日研报由 LLM 生成结构化 JSON，包含以下部分：

| 字段                 | 说明                                                 |
| -------------------- | ---------------------------------------------------- |
| `executiveSummary`   | 一句话总结当日全球动态核心主线                       |
| `globalEvents`       | 重大事件列表（含事件类型、威胁等级标注）             |
| `economicAnalysis`   | 宏观经济深度分析（至少 300 字）                      |
| `investmentTrends`   | 资产配置研判（含置信度评分 0-100）                   |
| `trendingAlerts`     | 趋势告警（飙升关键词及其市场影响评估）               |
| `riskAssessment`     | 全球风险格局综合评估（200 字以上）                   |
| `sourceAnalysis`     | 信源质量特征和覆盖盲区分析（可选）                   |

研报通过飞书富文本卡片（深蓝色 indigo 品牌主题）投递，含完整 Markdown 排版。

## 📰 信息源

当前已配置 **31 个**信息源，覆盖以下类别：

| 类别         | 代表源                                         | 数量 |
| ------------ | ---------------------------------------------- | ---- |
| 🌍 地缘政治 | Reuters World、AP News、BBC World、Guardian     | 8    |
| 📈 经济金融 | Bloomberg、Reuters Business、CNBC、MarketWatch  | 6    |
| 🏛️ 政府央行 | Federal Reserve、FRED、White House、Pentagon     | 4    |
| 🔬 智库组织 | CrisisWatch、IAEA、UN News、Atlantic Council    | 5    |
| ⚡ 中东     | BBC Middle East、Guardian ME                    | 2    |
| 🌏 亚太     | BBC Asia、Nikkei Asia                           | 2    |
| ⛽ 能源     | Oil & Gas、Nuclear Energy                       | 2    |
| 🔒 网络安全 | CISA Advisories                                 | 1    |
| 📡 实时聚合 | GDELT Breaking News                             | 1    |

> 信息源可在 `src/config/sources.ts` 中自由扩展，支持任意标准 RSS 格式。每个源可配置分级（tier）、类型（type）和宣传风险（propagandaRisk）。

## 🔧 技术栈

| 组件         | 技术                    | 说明                                |
| ------------ | ----------------------- | ----------------------------------- |
| 语言         | TypeScript              | 类型安全                            |
| 运行时       | Node.js 18+ / ts-node   | 直接运行 TS                         |
| AI           | OpenAI Compatible API   | 支持多家 LLM 服务 + 回退链         |
| 数据库       | SQLite (better-sqlite3) | WAL 模式，轻量高性能持久化          |
| RSS 解析     | rss-parser              | 标准 RSS/Atom 解析                  |
| 调度         | node-cron               | 类 Crontab 调度                     |
| 并发控制     | p-limit                 | 限制并发请求数                      |
| 日志         | Pino + pino-pretty      | 结构化彩色日志                      |
| HTTP         | Axios                   | HTTP 请求                           |
| 校验         | Zod                     | 运行时类型校验                      |
| 分词         | Intl.Segmenter          | 多语言分词（中/日/韩/英）           |
| 容器化       | Docker                  | 两阶段构建，Alpine 镜像             |

## ⚙️ 可调优参数

所有参数均在 `.env` 中配置，附合理默认值：

| 参数                          | 默认值       | 说明                         |
| ----------------------------- | ------------ | ---------------------------- |
| `CRON_COLLECT`                | `0 * * * *`  | 数据采集频率                 |
| `CRON_REPORT`                 | `0 8 * * *`  | 研报生成时间                 |
| `CRON_CLEANUP`                | `0 3 * * *`  | 数据清理时间                 |
| `RSS_TIMEOUT_MS`              | `15000`      | 单源抓取超时（毫秒）        |
| `RSS_CONCURRENCY`             | `10`         | 并发抓取数                   |
| `CB_MAX_FAILURES`             | `3`          | 熔断触发失败次数             |
| `CB_COOLDOWN_MS`              | `300000`     | 熔断冷却时长（毫秒）        |
| `AI_TIMEOUT_MS`               | `90000`      | AI API 超时（毫秒）         |
| `AI_MAX_CONTEXT_TOKENS`       | `8000`       | AI 上下文 Token 预算         |
| `DEDUP_SIMILARITY_THRESHOLD`  | `0.55`       | 标题去重相似度阈值           |
| `DEDUP_HOURS_BACK`            | `24`         | 去重回溯时间窗口（小时）     |
| `REPORT_MAX_NEWS`             | `500`        | 单次研报最大新闻条数         |
| `DATA_RETENTION_DAYS`         | `30`         | 数据保留天数                 |
| `CLUSTER_SIMILARITY_THRESHOLD`| `0.3`        | 聚类 Jaccard 阈值            |
| `NOTIFY_MAX_RETRIES`          | `3`          | 推送失败最大重试次数         |
| `NOTIFY_BASE_DELAY_MS`        | `1000`       | 重试基础延迟（指数退避）     |

## 📄 License

ISC

---

*Powered by DeepCurrents Intelligence Engine v2.1*
