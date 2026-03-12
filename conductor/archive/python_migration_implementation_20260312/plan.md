# Implementation Plan: Full Python Migration Implementation

## Phase 1: 环境准备与目录重构 (Preparation & Scaffolding) [checkpoint: e66be59]
- [x] Task: 重组目录结构 ab4781e
    - [x] 将现有 `src/` 移动至 `src_ts/` (备份)
    - [x] 创建新的 Python `src/` 目录并初始化 `__init__.py`
- [x] Task: 初始化依赖管理 1b211e5
    - [x] 创建 `requirements.txt` 或 `pyproject.toml`
    - [x] 安装核心依赖：`aiohttp`, `pydantic-settings`, `aiosqlite`, `openai`, `jieba`, `nltk`, `loguru`, `apscheduler`
- [x] Task: Conductor - User Manual Verification 'Preparation' (Protocol in workflow.md)

## Phase 2: 基础工具与配置迁移 (Core Utils & Config) [checkpoint: 06f55ef]
- [x] Task: 实现配置管理与日志系统 7f295bf
    - [x] 编写 `src/config/settings.py` (映射 `.env` 到 Pydantic BaseSettings)
    - [x] 配置 `loguru` 结构化日志
- [x] Task: 迁移多语言分词工具 25a4423
    - [x] 编写 `src/utils/tokenizer.py` (集成 `jieba` 与 `nltk`)
    - [x] 编写测试验证中英文分词的一致性
- [x] Task: Conductor - User Manual Verification 'Core Utils' (Protocol in workflow.md)

## Phase 3: 数据存储层迁移 (Data Layer) [checkpoint: e4487a1]
- [x] Task: 重写数据库服务 `db_service.py` 6071a87
    - [x] 初始化 `raw_news` 与 `predictions` 表 Schema
    - [x] 实现异步数据库操作 (aiosqlite)
    - [x] 移植模糊标题去重逻辑 (Trigram + Jaccard)
- [x] Task: 编写数据库逻辑测试 6071a87
    - [x] 验证数据存取、去重阈值判定
- [x] Task: Conductor - User Manual Verification 'Data Layer' (Protocol in workflow.md)

## Phase 4: 采集与分析管线迁移 (Collector & Pipeline) [checkpoint: 7d6d9e2]
- [x] Task: 实现异步 RSS 采集器 28bebee
    - [x] 移植 `RSSCircuitBreaker` 熔断逻辑
    - [x] 实现并发限制的 `Collector`
- [x] Task: 移植威胁分类与聚类引擎 86f2915
    - [x] 转换关键词级联分类规则
    - [x] 实现基于并查集的新闻聚类逻辑
- [x] Task: 编写管线集成测试 86f2915
    - [x] 模拟抓取流程，验证分类与聚类正确性
- [x] Task: Conductor - User Manual Verification 'Pipeline' (Protocol in workflow.md)

## Phase 5: AI 推理与评分系统迁移 (Intelligence & Scorer) [checkpoint: 126ca69]
- [x] Task: 重构多智能体 AI 服务 2b3ebef
    - [x] 迁移 `Macro Analyst`, `Sentiment`, `Market Strategist` 的 Prompt
    - [x] 实现基于 `asyncio.gather` 的并行推理流
- [x] Task: 移植自动评分与行情集成 79d177c
    - [x] 整合 `yfinance` 库调用
    - [x] 重写 `PredictionScorer`
- [x] Task: Conductor - User Manual Verification 'Intelligence' (Protocol in workflow.md)

## Phase 6: 任务调度、推送与交付 (Orchestration & Finalization)
- [x] Task: 实现主入口与 Cron 调度 bfc4a6d
    - [x] 编写 `src/main.py`
    - [x] 使用 `APScheduler` 配置采集、研报、清理任务
- [x] Task: 移植推送通知器 (Feishu/Telegram) e5572de
    - [x] 移植富文本卡片模板和 Markdown 渲染逻辑
- [x] Task: 最终全流程回归验证与文档更新 25a4423
    - [x] 运行 Python 版本全流程，验证输出质量
    - [x] 更新 `README.md` 中的启动指令
- [x] Task: Conductor - User Manual Verification 'Finalization' (Protocol in workflow.md)
