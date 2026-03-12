# Implementation Plan: Full Python Migration Implementation

## Phase 1: 环境准备与目录重构 (Preparation & Scaffolding)
- [ ] Task: 重组目录结构
    - [ ] 将现有 `src/` 移动至 `src_ts/` (备份)
    - [ ] 创建新的 Python `src/` 目录并初始化 `__init__.py`
- [ ] Task: 初始化依赖管理
    - [ ] 创建 `requirements.txt` 或 `pyproject.toml`
    - [ ] 安装核心依赖：`aiohttp`, `pydantic-settings`, `aiosqlite`, `openai`, `jieba`, `nltk`, `loguru`, `apscheduler`
- [ ] Task: Conductor - User Manual Verification 'Preparation' (Protocol in workflow.md)

## Phase 2: 基础工具与配置迁移 (Core Utils & Config)
- [ ] Task: 实现配置管理与日志系统
    - [ ] 编写 `src/config/settings.py` (映射 `.env` 到 Pydantic BaseSettings)
    - [ ] 配置 `loguru` 结构化日志
- [ ] Task: 迁移多语言分词工具
    - [ ] 编写 `src/utils/tokenizer.py` (集成 `jieba` 与 `nltk`)
    - [ ] 编写测试验证中英文分词的一致性
- [ ] Task: Conductor - User Manual Verification 'Core Utils' (Protocol in workflow.md)

## Phase 3: 数据存储层迁移 (Data Layer)
- [ ] Task: 重写数据库服务 `db_service.py`
    - [ ] 初始化 `raw_news` 与 `predictions` 表 Schema
    - [ ] 实现异步数据库操作 (aiosqlite)
    - [ ] 移植模糊标题去重逻辑 (Trigram + Jaccard)
- [ ] Task: 编写数据库逻辑测试
    - [ ] 验证数据存取、去重阈值判定
- [ ] Task: Conductor - User Manual Verification 'Data Layer' (Protocol in workflow.md)

## Phase 4: 采集与分析管线迁移 (Collector & Pipeline)
- [ ] Task: 实现异步 RSS 采集器
    - [ ] 移植 `RSSCircuitBreaker` 熔断逻辑
    - [ ] 实现并发限制的 `Collector`
- [ ] Task: 移植威胁分类与聚类引擎
    - [ ] 转换关键词级联分类规则
    - [ ] 实现基于并查集的新闻聚类逻辑
- [ ] Task: 编写管线集成测试
    - [ ] 模拟抓取流程，验证分类与聚类正确性
- [ ] Task: Conductor - User Manual Verification 'Pipeline' (Protocol in workflow.md)

## Phase 5: AI 推理与评分系统迁移 (Intelligence & Scorer)
- [ ] Task: 重构多智能体 AI 服务
    - [ ] 迁移 `Macro Analyst`, `Sentiment`, `Market Strategist` 的 Prompt
    - [ ] 实现基于 `asyncio.gather` 的并行推理流
- [ ] Task: 移植自动评分与行情集成
    - [ ] 整合 `yfinance` 库调用
    - [ ] 重写 `PredictionScorer`
- [ ] Task: Conductor - User Manual Verification 'Intelligence' (Protocol in workflow.md)

## Phase 6: 任务调度、推送与交付 (Orchestration & Finalization)
- [ ] Task: 实现主入口与 Cron 调度
    - [ ] 编写 `src/main.py`
    - [ ] 使用 `APScheduler` 配置采集、研报、清理任务
- [ ] Task: 移植推送通知器 (Feishu/Telegram)
    - [ ] 移植富文本卡片模板和 Markdown 渲染逻辑
- [ ] Task: 最终全流程回归验证与文档更新
    - [ ] 运行 Python 版本全流程，验证输出质量
    - [ ] 更新 `README.md` 中的启动指令
- [ ] Task: Conductor - User Manual Verification 'Finalization' (Protocol in workflow.md)
