# 🌊 DeepCurrents (深流)

**AI-Powered Macro Intelligence & Global Strategy Engine**

> "News is the foam on the surface; trends are the currents deep below."

DeepCurrents 是一个自动化的全球情报聚合与宏观研报生成系统。它借鉴了 `koala73/worldmonitor` 的顶级情报源筛选逻辑，通过 AI 深度合成，为专业投资者和宏观观察者提供每日定时的全球动态研判。

## 🌟 核心特性

- **多维聚合 (Multi-Source Aggregation)**: 整合全球顶级财经、政治、地缘资讯源（Reuters、Bloomberg、AP News 等），覆盖地缘政治、宏观经济、市场动态等多个维度。
- **深度合成 (Cognitive Synthesis)**: 不仅仅是摘要。利用 LLM 的推理能力，在海量碎片化信息中提取"主线"，并生成宏观经济影响分析。
- **投资视角 (Investment Oriented)**: 自动对全球大宗商品、股市、外汇等资产类别进行看涨/看跌研判并提供理由。
- **高可靠性 (Industrial Grade)**:
  - 采用 SQLite 进行持久化去重，确保报告不重复。
  - 内置并发控制（p-limit），保护 API 速率限制。
  - 结构化日志（Pino），实时监测引擎状态。
- **多通道分发 (Multi-Channel Notification)**: 支持飞书富文本卡片和 Telegram Bot 双通道投递专业排版的研报。

## 📁 项目结构

```
deep-currents/
├── src/
│   ├── monitor.ts              # 核心引擎入口，调度数据采集与研报生成
│   ├── test-tools.ts           # 集成测试工具，支持分类测试各组件联通性
│   ├── config/
│   │   └── sources.ts          # RSS 信息源配置（地缘政治/经济/特色源）
│   └── services/
│       ├── ai.service.ts       # LLM 深度分析服务，生成结构化研报
│       └── db.service.ts       # SQLite 数据持久化与去重服务
├── data/                       # 运行时自动创建，存放 intel.db
├── .env.example                # 环境变量模板
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

编辑 `.env` 文件：

```env
# AI 配置 (推荐使用 Groq, OpenRouter 或 OpenAI)
AI_API_URL=https://api.openai.com/v1/chat/completions
AI_API_KEY=your_openai_api_key
AI_MODEL=gpt-4o-mini

# 飞书 Webhook 地址
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/your_bot_id

# Telegram 配置 (可选)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 4. 启动引擎

```bash
npx ts-node src/monitor.ts
```

引擎启动后将自动执行：

1. **立即执行一次**数据采集
2. **每小时整点**自动抓取最新全球资讯
3. **每天 08:00**自动合成并投递每日研报

## 🧪 集成测试

提供独立的测试工具，用于验证各组件的联通性。支持按类别单独或组合测试。

```bash
# 运行全部测试
npx ts-node src/test-tools.ts

# 仅测试 RSS 信息源联通性
npx ts-node src/test-tools.ts rss

# 仅测试 LLM 服务
npx ts-node src/test-tools.ts llm

# 组合测试多个类别
npx ts-node src/test-tools.ts rss llm

# 测试飞书推送
npx ts-node src/test-tools.ts feishu

# 测试 Telegram 推送
npx ts-node src/test-tools.ts telegram

# 查看帮助
npx ts-node src/test-tools.ts --help
```

**可用测试类别：**

| 类别       | 说明                                   |
| ---------- | -------------------------------------- |
| `rss`      | 测试前 5 个 RSS 信息源的抓取联通性     |
| `llm`      | 测试 AI API 调用及 JSON 格式返回       |
| `feishu`   | 发送飞书测试消息，验证 Webhook 联通性  |
| `telegram` | 发送 Telegram 测试消息，验证 Bot 配置  |

## 📅 任务调度

| 任务         | Cron 表达式    | 说明                                             |
| ------------ | -------------- | ------------------------------------------------ |
| **数据采集** | `0 * * * *`    | 每小时整点扫描所有 RSS 源，新增条目入库并去重    |
| **研报生成** | `0 8 * * *`    | 每天 08:00 合成过去 24 小时全量情报，生成深度研报 |

## 🏗️ 架构概览

```
                     ┌───────────────┐
                     │  RSS Sources  │
                     │ (9+ 全球源)   │
                     └───────┬───────┘
                             │ 每小时采集
                             ▼
┌─────────────────────────────────────────┐
│           DeepCurrents Engine           │
│                                         │
│  ┌─────────┐   ┌────────┐   ┌───────┐  │
│  │Collector│──▶│ SQLite │──▶│  AI   │  │
│  │(p-limit)│   │  去重  │   │Service│  │
│  └─────────┘   └────────┘   └───┬───┘  │
│                                 │       │
│                          结构化研报     │
│                                 │       │
│  ┌──────────┐   ┌───────────┐   │       │
│  │  飞书卡片 │◀──│ Notifier  │◀──┘       │
│  └──────────┘   └─────┬─────┘           │
│  ┌──────────┐         │                 │
│  │ Telegram │◀────────┘                 │
│  └──────────┘                           │
└─────────────────────────────────────────┘
```

## 📊 研报输出格式

每日研报由 LLM 生成结构化 JSON，包含以下部分：

| 字段                 | 说明                                     |
| -------------------- | ---------------------------------------- |
| `executiveSummary`   | 一句话总结当日全球动态核心主线           |
| `globalEvents`       | 重大事件列表（地缘政治/货币政策等分类）  |
| `economicAnalysis`   | 宏观经济深度分析（至少 300 字）          |
| `investmentTrends`   | 资产配置研判（美股/黄金/原油/美债等）    |

研报通过飞书富文本卡片（深蓝色 indigo 品牌主题）投递，含完整 Markdown 排版。

## 📰 信息源

当前已配置的信息源分为三大类别：

**🌍 地缘政治 & 冲突**

- Reuters World、AP News、Financial Times World、Conflict News

**📈 经济 & 金融**

- Bloomberg Markets、Yahoo Finance、MarketWatch Top Stories、FRED Economic Release

**⚡ 特色源**

- GDELT Breaking News（全球事件实时追踪）

> 信息源可在 `src/config/sources.ts` 中自由扩展，支持任意标准 RSS 格式。

## 🔧 技术栈

| 组件     | 技术                    | 说明               |
| -------- | ----------------------- | ------------------ |
| 语言     | TypeScript              | 类型安全           |
| 运行时   | Node.js + ts-node       | 直接运行 TS        |
| AI       | OpenAI Compatible API   | 支持多家 LLM 服务  |
| 数据库   | SQLite (better-sqlite3) | 轻量高性能持久化   |
| RSS 解析 | rss-parser              | 标准 RSS/Atom 解析 |
| 调度     | node-cron               | 类 Crontab 调度    |
| 并发控制 | p-limit                 | 限制并发请求数     |
| 日志     | Pino + pino-pretty      | 结构化彩色日志     |
| HTTP     | Axios                   | HTTP 请求          |
| 校验     | Zod                     | 运行时类型校验     |

## 📄 License

ISC

---

*Powered by DeepCurrents Intelligence Engine v1.0.0*
