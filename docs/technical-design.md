# DeepCurrents (深流) 技术设计文档

**版本**: v2.2 (Python)
**状态**: Event-centric 主链路已落地
**定位**: AI 驱动的全球情报聚合与宏观策略研报引擎
**配套文档**: [index.md](./index.md) | [event-intelligence.md](./event-intelligence.md) | [iteration-plan.md](./iteration-plan.md) | [archive/README.md](./archive/README.md)

---

## 1. 系统概述

DeepCurrents 从多源 RSS / RSSHub 信息流中抓取文章，执行 article-first ingestion、特征抽取、cheap/semantic dedup、事件归并、事件排序与 evidence 选择，再通过多智能体 LLM 流程生成每日结构化研报，并投递到飞书与 Telegram。

当前正式实现已经不再使用旧 `raw_news -> classifier -> clustering -> generate_daily_report()` 文章级主链路。

---

## 2. 代码架构（Python 主链路）

### 2.1 入口与调度

- 入口: `src/main.py`
- 调度器: `APScheduler.AsyncIOScheduler`
- 默认任务:
  - 数据采集: `CRON_COLLECT`（默认 `0 * * * *`）
  - 报告生成: `CRON_REPORT`（默认 `0 8 * * *`）
  - 自动评分: 固定 interval 4 小时

说明:

- 采集与报告入口均依赖 Event Intelligence runtime。
- 当 runtime 未启用或未成功启动时，采集与报告入口都保持 fail-closed，不再回退旧文章级链路。

### 2.2 业务编排层

- 编排器: `src/engine.py` (`DeepCurrentsEngine`)
- 责任:
  - 启动 prediction repository 与 Event Intelligence runtime
  - 装配 ingestion wiring 与 report wiring
  - 触发首轮采集与评分
  - 调度 event-centric 报告生成与通知

### 2.3 采集层

- 模块: `src/services/collector.py`
- 技术: `aiohttp` + `feedparser` + `asyncio.Semaphore`
- 正式链路:
  - `collector`
  - `article_normalizer`
  - `article_repository`
  - `article_feature_extractor`
  - `semantic_deduper`
  - `event_builder`
  - `event_enrichment`
- 关键机制:
  - 按信源 tier 优先抓取
  - T1/T2 信源尝试正文提取（`src/utils/extractor.py`）
  - 熔断器（`src/services/circuit_breaker.py`）按源级别计数失败并冷却
  - ingestion wiring 不可用时直接 skip，不写 legacy SQLite

### 2.4 存储与事件层

- 运行时存储:
  - PostgreSQL: 文章、事件、brief、report run、evaluation labels 等结构化数据
  - Qdrant: embedding / 向量检索
  - Redis: cache / runtime support
- 预测存储:
  - `src/services/prediction_repository.py`
  - 使用 SQLite 管理 `predictions` 表
- 文本相似度工具:
  - `src/utils/text_similarity.py`
  - 提供 trigram / Jaccard / Dice，供 `semantic_deduper.py` 与 `event_builder.py` 复用

### 2.5 排序与上下文构建层

- 事件查询: `src/services/event_query_service.py`
- 事件排序: `src/services/event_ranker.py`
- 证据选择: `src/services/evidence_selector.py`
- 事件总结: `src/services/event_summarizer.py`
- 主题总结: `src/services/theme_summarizer.py`
- 报告上下文构建: `src/services/report_context_builder.py`

目标:

- 从事件层压缩得到可报告的 `event briefs` 与 `theme briefs`
- 让 AI 读事件卡，而不是文章列表

### 2.6 AI 生成层 (金融级多智能体流水线)

- **报告编排**: `src/services/report_orchestrator.py`
- **角色协作流 (Phase 3 辩论机制)**:
  1. **MacroAnalyst (V2)**: 识别宏观传导逻辑、政策意图与预期差 (Surprise)。
  2. **SentimentAnalyst (V2)**: 识别市场情绪底色、筹码分布与 Risk-on/off 状态。
  3. **MarketStrategist (CIO V2)**: 整合各方信息，产出包含**配对交易 (Pair Trades)**、**全球大盘综述 (Equity Overview)** 与**场景推演 (Scenario Analysis)** 的策略初稿。
  4. **RiskManager (CRO)**: 对 CIO 初稿执行逻辑挑战，确保合规性、中立性并强化尾部风险提示。
- **决策支持**:
  - **宏观因子注入**: 自动集成 VIX (波动率)、US10Y-2Y (收益率曲线) 等实时信号。
  - **资产精准映射**: LLM 驱动的 Ticker/ETF 映射 (如 Brent, GC=F, SPY)。
- **AIService 核心责任**:
  - Provider window / input budget 动态计算。
  - JSON 修复与金融 Schema 强制归一化。
  - 预测持久化与策略回测打标。


### 2.7 报告追溯与评估层

- 报告追溯: `src/services/report_run_tracker.py`
- 评估 runner: `src/services/evaluation_runner.py`
- 反馈闭环:
  - `src/services/feedback_repository.py`
  - `src/services/feedback_service.py`

能力:

- 保存 `report_runs` 与 `report_event_links`
- 回放任意一次 event-centric 报告 trace
- 对 duplicate / same-event / top-N relevance 做统一评估
- 将 report-centric review 写入 `evaluation_labels`

### 2.8 评分与推送层

- 评分: `src/services/scorer.py`
  - 轮询 `predictions` 中 `pending` 记录
  - 获取当前价格并按方向与涨跌幅打分
  - 更新 `status=scored`
- 推送: `src/services/notifier.py`
  - 飞书卡片（`aiohttp`）
  - Telegram Bot（`httpx`，支持代理）
  - 通道并行、指数退避、单通道失败不阻塞其他通道

---

## 3. 配置体系

- 文件: `src/config/settings.py`
- 来源: `.env` + 环境变量
- 核心配置组:
  - 采集并发/超时
  - 熔断参数
  - AI 主备提供商
  - Event Intelligence runtime 连接参数
  - 推送重试与代理
  - 日志输出

关键说明:

- `EVENT_INTELLIGENCE_ENABLED=true` 时，必须配置 PostgreSQL、Qdrant、Redis 连接。
- 未启用 runtime 时，采集和报告不会回退到旧文章级路径。
- 宿主机直接运行时使用 `HTTPS_PROXY`；compose 容器出网代理单独使用 `DOCKER_HTTPS_PROXY`。
- 采集器会让 `rsshub`、`localhost`、私有网段等本地目标绕过代理，避免容器内访问本地 RSSHub 时被错误转发。

---

## 4. 测试与质量现状

- 测试目录: `tests/`
- 当前重点覆盖:
  - 采集 article-first 顺序与 fail-closed 语义
  - engine report wiring
  - report orchestrator
  - prediction repository / scorer
  - evaluation runner
  - feedback loop

注意:

- `src/test_tools.py` 是运维拨测脚本，不参与正式主链路测试。

---

## 5. 运行与部署

### 5.1 本地运行

```bash
uv pip install -r requirements.txt
cp .env.example .env
docker compose up -d postgres qdrant redis rsshub
uv run -m src.main
```

### 5.2 手动报告命令

```bash
uv run -m src.run_report
uv run -m src.run_report --report-only --no-push
uv run -m src.run_report --json
```

说明:

- `--report-only` 仅适用于 PostgreSQL 中已存在 event-intelligence 数据的场景。

### 5.3 Compose 全栈

```bash
docker compose up -d --build
docker compose logs -f deep-currents
```

代理说明:

- 宿主机模式代理: `HTTPS_PROXY=http://127.0.0.1:7890`
- compose 容器代理: `DOCKER_HTTPS_PROXY=http://host.docker.internal:7890`
- `docker-compose.yml` 已为 `rsshub` 和 `deep-currents` 注入 `host.docker.internal:host-gateway`

### 5.4 运行前提

正式主链路需要:

- OpenAI-compatible AI API
- PostgreSQL
- Qdrant
- Redis

---

## 6. 已知限制

1. Event Intelligence runtime 未配置时，系统不会回退旧文章级链路。
2. 评分窗口仍为演示参数:
   - 当前默认“预测后 10 秒即可评分”，生产环境建议改为 12h/24h 或按资产波动率配置。
3. 资产类别解析仍存在边界:
   - 自动搜索 symbol 受外部行情搜索结果质量影响，建议持续扩充 `asset_symbols.json`。

---

*Last aligned with codebase on 2026-03-13.*
