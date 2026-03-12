# DeepCurrents: Full Python Rewrite Migration Plan

## 1. 迁移目标
将 DeepCurrents 引擎从 TypeScript/Node.js 完全迁移至 Python 3.10+。消除多语言维护负担，利用 Python 在 AI/数据分析领域的生态优势（如原生集成 `yfinance`, `pandas`, `langchain`）。

## 2. 模块重写优先级与方案对齐

### Phase A: 核心基础设施 (Foundations)
*   **配置管理**: `dotenv` + `pydantic-settings` 替代现有 `config/settings.ts`。
*   **日志系统**: 使用 `loguru` 或 `structlog` 实现带颜色的结构化日志。
*   **数据库**: 使用 `sqlite3` 标准库或 `aiosqlite`。由于是新项目，直接按原 Schema 重建。

### Phase B: 数据收集与分析管线 (Collector & Pipeline)
*   **Collector**: `aiohttp` + `asyncio.Semaphore` 替代 `axios` + `p-limit`。
*   **RSS 解析**: `feedparser` 替代 `rss-parser`。
*   **全文提取**: `trafilatura` 或 `goose3` 替代 `Mozilla Readability`。
*   **威胁分类 (`Classifier`)**: 移植现有的关键词匹配逻辑，利用 Python 正则表达式 `re`。
*   **模糊去重**: 使用 Python 原生 `set` 实现 Jaccard，`collections.Counter` 实现 n-gram。

### Phase C: AI 推理与多智能体协作 (Intelligence)
*   **AI 接口**: 使用 `openai` Python SDK。
*   **多智能体**: 使用原生 `asyncio.gather` 实现并行推理（Macro/Sentiment），由 `MarketStrategist` 整合。
*   **数据模型**: 使用 `Pydantic` 替代 `Zod`。

### Phase D: 调度与通知 (Ops & Delivery)
*   **调度**: `APScheduler` (AsyncIOScheduler) 替代 `node-cron`。
*   **行情集成**: 直接调用 `yfinance` 库，不再需要 `child_process`。
*   **通知**: `httpx` 发送 Webhook。

## 3. 分阶段实施策略 (Strangler Fig 模式)
由于目前项目较小，建议采用 **“影子重写”** 策略：
1.  **Step 1**: 在 `python/` 目录下建立完整的 Python 项目结构。
2.  **Step 2**: 逐个重写模块，每个模块配齐相应的单元测试（`pytest`）。
3.  **Step 3**: 编写一个主集成测试，比对 Python 抓取结果与 Node.js 抓取结果的一致性。
4.  **Step 4**: 整体切换，删除 `src/` (TS) 目录。

## 4. 风险控制
*   **I/O 阻塞**: 必须坚持使用 `aiohttp` 等异步库，避免在 `asyncio` 循环中进行阻塞式调用（如同步 `requests`）。
*   **分词一致性**: Python 的 `jieba` 与 JS 的 `Intl.Segmenter` 分词结果可能存在细微差异，需在聚类测试中进行微调。

## 5. 结论
**高度可行且建议立即执行。** 
Python 重写将使项目代码量减少约 30%，性能相当，且极大地降低了 AI 逻辑与数据工具（yfinance）之间的交互复杂性。
