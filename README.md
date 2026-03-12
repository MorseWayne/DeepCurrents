# 🌊 DeepCurrents (深流)

**AI 驱动的全球情报聚合与宏观策略引擎**

> *新闻是水面上的浪花，趋势是深处的暗流。*

**[English](./README.en.md)** | 中文

DeepCurrents 是一个自动化的全球情报聚合与宏观研报生成系统。它从 35+ 个全球顶级资讯源中采集碎片化信息，经由威胁分类、事件聚类、趋势检测等多维分析管线，最终通过多智能体协作推理引擎合成为结构化的每日宏观策略研报。

---

## ✨ 核心特性

- **多智能体协作**: 引入 **Macro Analyst** (地缘宏观专家) 与 **Sentiment Analyst** (市场情绪专家) 并行推理，由 **Market Strategist** (首席策略官) 汇总整合，提升研报深度。
- **实时行情注入**: 集成 `yfinance` 插件，自动获取黄金、原油、标普 500 等核心资产的实时价格，辅助 AI 进行逻辑与价格的“预期差”分析。
- **预测评分闭环**: 自动保存 AI 对资产趋势的研判，并在事后基于真实走势自动回测评分（0-100分），实现 AI 决策质量的持续量化。
- **异步高性能**: 全量 Python 3.10+ 重构，基于 `asyncio` 和 `aiohttp` 的非阻塞 I/O 设计，支撑大规模并发采集。
- **高可靠性**:
  - **模糊标题去重**（trigram + Jaccard），有效合并同一事件的不同措辞报道。
  - **RSS 熔断器**，连续失败源自动冷却，防止级联故障。
  - **AI 回退链**，主/备提供商自动切换。
- **多通道分发**: 支持飞书富文本卡片和 Telegram Bot 双通道并行投递。

---

## 🚀 快速启动

### 前置要求

- **Python** >= 3.10
- **uv** (强烈推荐) 或 pip
- 一个支持 OpenAI 兼容接口的 AI API Key

### 1. 初始化环境

```bash
# 克隆仓库
git clone https://github.com/your-username/DeepCurrents.git
cd DeepCurrents

# 使用 uv 极速安装依赖 (自动创建虚拟环境)
uv pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 填写 AI_API_KEY, FEISHU_WEBHOOK 等
```

### 3. 启动引擎

```bash
# 启动常驻调度引擎
uv run -m src.main

# 或者：手动触发一次全流程并输出研报
uv run -m src.run_report
```

---

## 🐳 运行模式与部署

DeepCurrents 支持两种运行模式，区别在于 `is_rss_hub` 标记的源如何获取数据。

| 模式 | 适用场景 | 说明 |
| :--- | :--- | :--- |
| **直连模式** | 快速测试 | 直接访问 `rsshub.app` 公共实例 |
| **自建 RSSHub 模式** | 生产部署 | 通过 `RSSHUB_BASE_URL` 指向自建实例，更稳定 |

### Docker Compose 一键部署 (推荐)

```bash
# 拉起 DeepCurrents + RSSHub + Redis
docker compose up -d --build
```

---

## 🧪 集成测试

使用 `pytest` 验证各组件的联通性与逻辑一致性：

```bash
uv run pytest                     # 运行全部测试
uv run pytest tests/test_collector.py   # 仅测试采集器
uv run pytest tests/test_ai_service.py  # 仅测试 AI 服务
```

---

## 📅 任务调度

| 任务 | 默认频率 | 模块 | 说明 |
| :--- | :--- | :--- | :--- |
| **数据采集** | 每小时整点 | `collector` | 扫描 RSS 源，去重入库 |
| **研报生成** | 每天 08:00 | `engine` | 合成情报，多智能体推理并推送 |
| **自动评分** | 每 4 小时 | `scorer` | 对历史预测进行真实行情回测 |
| **数据清理** | 每天 03:00 | `db_service` | 清理过期数据（默认保留 30 天） |

---

## ⚙️ 核心参数调优

所有参数均在 `.env` 中配置：

| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `AI_MAX_CONTEXT_TOKENS` | `16000` | AI 上下文 Token 预算 |
| `DEDUP_SIMILARITY_THRESHOLD` | `0.55` | 标题去重相似度阈值 |
| `RSS_CONCURRENCY` | `10` | 异步采集并发数 |
| `DATA_RETENTION_DAYS` | `30` | 数据库信息保留天数 |

---

## 📁 项目结构 (v2.2 Python)

```
DeepCurrents/
├── src/
│   ├── main.py                 # 常驻引擎入口
│   ├── engine.py               # 核心协调器
│   ├── run_report.py           # 命令行触发工具
│   ├── services/
│   │   ├── ai_service.py       # 多智能体推理流
│   │   ├── db_service.py       # 异步 SQLite 与模糊去重
│   │   ├── collector.py        # 异步 RSS 采集器
│   │   └── scorer.py           # 预测评分引擎
│   └── utils/
│       ├── tokenizer.py        # 多语言分词 (Jieba)
│       └── market_data.py      # yfinance 行情集成
├── tests/                      # 单元与集成测试
├── Dockerfile                  # 基于 uv 的极速构建镜像
└── docker-compose.yml          # 全栈编排
```

---

## 🗺️ 路线图

**已完成 (v2.2):**
- ✅ 100% Python 异步架构迁移
- ✅ 多智能体协作推理 (Macro/Sentiment/Strategist)
- ✅ `yfinance` 实时行情集成与 AI 预期差分析
- ✅ 自动化预测评分系统 (Scorer)
- ✅ 飞书富文本卡片 & Telegram 双通道推送

**规划中:**
- ⏳ 语义去重 (基于 Embedding 向量相似度)
- ⏳ 多语言自动翻译 (接入翻译模型)
- ⏳ 情绪指数历史曲线跟踪

---

## 📄 License
ISC | *Powered by DeepCurrents Intelligence Engine v2.2*
