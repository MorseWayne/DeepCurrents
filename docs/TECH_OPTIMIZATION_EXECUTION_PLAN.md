# DeepCurrents 技术优化实施计划

**版本**: v1.0  
**状态**: 待执行  
**依据文档**: `docs/TECH_OPTIMIZATION_ANALYSIS.md`  
**代码基线**: `src/` Python 主链路  
**基线日期**: 2026-03-12  
**本地验证基线**: `uv run pytest -q` -> `29 passed`

---

## 1. 文档目的

本文档不是方向性分析，而是将优化分析报告落成一个可执行的改造计划。目标是回答下面四个问题：

1. 先改什么，后改什么。
2. 每一项具体改哪些代码和数据结构。
3. 如何验证改动有效且不破坏现有闭环。
4. 如何在任意阶段中止或回滚，而不是推倒重来。

---

## 2. 改造目标

本轮计划的总目标分为四层：

1. 提升入库数据质量。
2. 提升事件聚合质量与上下文利用效率。
3. 提升信源权重与研究闭环的可计算性。
4. 为后续语义能力、历史召回和平台化演进建立基础设施。

对应到当前代码，优先级排序如下：

1. 先修数据入口和数据结构。
2. 再修排序、聚类和评分逻辑。
3. 再引入语义能力。
4. 最后升级 Agent 编排和研究评估体系。

---

## 3. 执行原则

### 3.1 不推倒现有闭环

当前 `collector -> db -> clustering -> ai -> notifier -> scorer` 主链路已可运行，因此所有改动必须满足：

1. 默认仍可生成研报。
2. 任一增强能力都允许配置开关关闭。
3. 旧数据在未回填完成前不能阻塞主流程。

### 3.2 先引入迁移能力，再扩表

当前 SQLite 初始化逻辑集中在 `src/services/db_service.py`，尚无正式 schema migration 机制。后续 `predictions` 和历史聚类表都需要扩表，因此必须先补一个最小可用迁移层。

### 3.3 先保留规则链路，再加语义链路

现有标题去重、威胁分类、Jaccard 聚类都不先进，但稳定、便宜、可解释。语义能力应先作为第二层，不应一上来替换全部规则逻辑。

### 3.4 每个阶段都必须带测试和回滚点

每个阶段交付必须包含：

1. 单元测试或集成测试。
2. 配置开关。
3. 可观察指标。
4. 明确的回滚方式。

---

## 4. 当前基线与主要约束

### 4.1 代码基线

当前关键模块如下：

- `src/services/collector.py`: RSS 拉取、去重、正文增强、入库。
- `src/services/db_service.py`: SQLite 表结构、标题缓存、预测存储。
- `src/services/classifier.py`: threat classification。
- `src/services/clustering.py`: token Jaccard + union-find 聚类。
- `src/services/ai_service.py`: 多 Agent 调用、JSON 修复、预测落库。
- `src/services/scorer.py`: 启发式方向评分。
- `src/utils/extractor.py`: `BeautifulSoup` 正文提取。
- `src/config/settings.py`: 配置入口。
- `src/config/sources.py`: 信源元数据。

### 4.2 当前约束

1. 数据库是 SQLite，适合轻量迁移，不适合一次性引入重型依赖。
2. 代码测试已覆盖 `db/collector/engine/ai/scorer`，适合做增量重构。
3. 当前没有统一的指标系统，因此阶段性效果验证要先依赖日志、测试和 SQL 抽样。
4. AI 输出结构已经受 `Pydantic` 约束，但预测字段仍然偏薄，评分体系无法细化。

---

## 5. 总体实施顺序

建议按 6 个阶段推进：

| 阶段 | 目标 | 建议周期 | 发布方式 |
| --- | --- | --- | --- |
| Phase 0 | 补迁移与观测基础 | 2-3 天 | 小版本 |
| Phase 1 | 完成 P0 数据质量改造 | 1-2 周 | 小版本 |
| Phase 2 | 完成信源权重与预测闭环重构 | 1 周 | 小版本 |
| Phase 3 | 引入语义去重与语义聚类 | 2-4 周 | 灰度开关 |
| Phase 4 | 建立历史事件缓存与结构化事件层 | 1-2 周 | 小版本 |
| Phase 5 | 升级 Agent 编排与研究评估体系 | 2 周+ | 独立里程碑 |

如果资源有限，最小可落地范围是执行到 Phase 2。

---

## 6. Phase 0: 基础设施先行

### 6.1 目标

在不改变业务行为的前提下，为后续扩表、回填、灰度发布提供基础设施。

### 6.2 任务拆分

#### 任务 P0-1: 引入最小数据库迁移机制

目标：

- 解决当前 `CREATE TABLE IF NOT EXISTS` 无法可靠演进 schema 的问题。

改动建议：

1. 新增 `schema_migrations` 或 `app_meta` 表，记录版本号。
2. 在 `DBService.connect()` 后执行一次 `run_migrations()`。
3. 抽出迁移逻辑到新文件，例如：
   - `src/services/migrations.py`
4. 提供以下能力：
   - 检测列是否存在。
   - 为旧表 `ALTER TABLE ADD COLUMN`。
   - 为新增索引做幂等创建。

代码触点：

- `src/services/db_service.py`
- `src/services/migrations.py`（新增）
- `tests/test_db_service.py`

验收标准：

1. 旧数据库可直接启动，不报错。
2. 旧数据不丢失。
3. 新列能被成功补齐。

回滚方式：

- 保留旧字段与旧查询；若迁移层异常，可临时回退到旧查询逻辑并关闭新功能开关。

#### 任务 P0-2: 增加结构化观测点

目标：

- 为后续判断“改动是否真的有效”提供最小观测能力。

改动建议：

1. 在采集阶段输出：
   - `new_count`
   - `url_dedup_count`
   - `title_dedup_count`
   - `extract_success_count`
   - `extract_fallback_count`
2. 在报告阶段输出：
   - `cluster_count`
   - `avg_cluster_size`
   - `report_news_count`
3. 在评分阶段输出：
   - `pending_count`
   - `scored_count`
   - `skipped_due_to_horizon_count`

代码触点：

- `src/services/collector.py`
- `src/engine.py`
- `src/services/scorer.py`

验收标准：

1. 日志中能看到每次运行的关键计数。
2. 不引入额外外部依赖。

---

## 7. Phase 1: 数据入口质量改造

### 7.1 目标

将 threat classification 和正文抽取前移到采集入库阶段，使数据库中的记录从“原始新闻”升级为“带基础分析的新闻对象”。

### 7.2 任务拆分

#### 任务 P1-1: threat classification 前移入库

目标：

- 所有新入库新闻在写入时就具备可用的 `threat_level / threat_category / threat_confidence`。

改动建议：

1. 在 `src/services/collector.py` 中，完成正文提取后调用 `classify_threat(title, final_content)`。
2. 将 threat 结果写入 `DBService.save_news(..., meta=...)`。
3. 在 `src/engine.py` 中不再默认重新分类，改为：
   - 优先使用 `raw_news` 已存 threat 字段。
   - 仅对 threat 为空或默认值的旧数据做兜底分类。
4. 补一个一次性回填入口，建议新增：
   - `src/run_backfill_threats.py`
5. 回填策略：
   - 仅扫描最近 `N` 天且 `threat_level='info'` 且 `threat_confidence=0.3` 的记录。
   - 幂等执行。

建议新增配置：

- `COLLECT_CLASSIFY_ON_INGEST=true`
- `REPORT_RECLASSIFY_MISSING_ONLY=true`
- `BACKFILL_THREAT_BATCH_SIZE=200`

代码触点：

- `src/services/collector.py`
- `src/services/classifier.py`
- `src/services/db_service.py`
- `src/engine.py`
- `src/config/settings.py`
- `tests/test_collector.py`
- `tests/test_engine.py`
- `tests/test_db_service.py`

测试补充：

1. 新入库新闻自动带上 threat 字段。
2. `engine.generate_and_send_report()` 对已有 threat 的新闻不重复分类。
3. 回填脚本对旧数据有效，且重复执行不报错。

验收标准：

1. 新新闻入库时 threat 字段命中率为 100%。
2. 报告排序不再依赖运行时二次 threat 计算。
3. 旧数据在回填前后均可正常生成报告。

回滚方式：

- 关闭 `COLLECT_CLASSIFY_ON_INGEST`，恢复报告阶段分类。

#### 任务 P1-2: 用 `trafilatura` 替换当前正文抽取主路径

目标：

- 提高 T1/T2 信源的正文质量，减少导航、版权、模板噪音。

改动建议：

1. `requirements.txt` 增加 `trafilatura`。
2. 重构 `src/utils/extractor.py` 为双层策略：
   - 第一层：`trafilatura.extract()`。
   - 第二层：保留当前 `BeautifulSoup` 回退逻辑。
3. 统一返回结构，建议补充可选字段：
   - `method`
   - `content_length`
4. 对提取失败和低质量结果加阈值判断：
   - 低于最小字数时继续回退。

建议新增配置：

- `EXTRACTOR_USE_TRAFILATURA=true`
- `EXTRACTOR_MIN_CONTENT_CHARS=200`
- `EXTRACTOR_FULLTEXT_SOURCE_MAX_TIER=2`

代码触点：

- `src/utils/extractor.py`
- `src/services/collector.py`
- `src/config/settings.py`
- `tests/test_collector.py`
- 建议新增 `tests/test_extractor.py`

测试补充：

1. `trafilatura` 成功时优先返回正文。
2. `trafilatura` 失败时回退到 `BeautifulSoup` 逻辑。
3. 对无正文页面返回 `None` 或短文本回退，不阻塞采集。

验收标准：

1. 高优先级信源抽取成功率提升。
2. 提取内容平均长度提升，且模板噪声下降。
3. 采集总耗时无明显恶化。

回滚方式：

- 关闭 `EXTRACTOR_USE_TRAFILATURA`。

#### 任务 P1-3: 统一 threat 与正文增强的入库回归测试

目标：

- 确保 Phase 1 改动不会破坏采集闭环。

改动建议：

1. 增加一个从 RSS entry 到 `save_news()` 的集成测试。
2. 断言以下字段已完整写入：
   - `content`
   - `source_tier`
   - `source_type`
   - `threat_level`
   - `threat_category`
   - `threat_confidence`

代码触点：

- `tests/test_collector.py`
- 可新增 `tests/test_pipeline.py` 场景

验收标准：

1. Phase 1 完成后，采集链路相关测试全部通过。

---

## 8. Phase 2: 信源权重与研究闭环重构

### 8.1 目标

将现有信源画像转成可计算特征，并扩展预测数据结构，使排序、研报解释和评分不再停留在简单启发式层面。

### 8.2 任务拆分

#### 任务 P2-1: 引入 source credibility / evidence score

目标：

- 把 `tier + type + propaganda_risk + state_affiliated + source_count` 变成统一分值。

改动建议：

1. 新增模块：
   - `src/services/evidence_service.py`
2. 提供两个核心函数：
   - `score_source(source_name) -> float`
   - `score_cluster_evidence(cluster) -> float`
3. 评分建议：
   - `tier` 为主权重。
   - `propaganda_risk` 做负向修正。
   - `state_affiliated` 标记不必一刀切减分，但需要附加风险标签。
   - `source_count` 做正向确认加权。
4. 在 `ClusteredEvent` 中新增：
   - `evidenceScore`
   - `riskTags`
5. 调整聚类排序逻辑：
   - 先看 threat。
   - 再看 evidenceScore。
   - 再看 `lastUpdated`。
6. 在 AI 上下文中加入 `evidenceScore` 和来源解释，支持更好的 `sourceAnalysis`。

建议新增配置：

- `EVIDENCE_SCORE_ENABLED=true`
- `EVIDENCE_PROPAGANDA_PENALTY=0.15`
- `EVIDENCE_MULTI_SOURCE_BONUS=0.10`

代码触点：

- `src/config/sources.py`
- `src/services/clustering.py`
- `src/services/ai_service.py`
- `src/services/evidence_service.py`（新增）
- `tests/test_pipeline.py`
- 建议新增 `tests/test_evidence_service.py`

测试补充：

1. T1 wire 高于 T3 blog。
2. 高 `propaganda_risk` 会被降权。
3. 多源确认 cluster 会得到加分。
4. 排序稳定且可解释。

验收标准：

1. 聚类输出中可见 `evidenceScore`。
2. AI 上下文包含来源质量说明。
3. source analysis 不再只是 prompt 文本，而是有结构化输入支撑。

回滚方式：

- 关闭 `EVIDENCE_SCORE_ENABLED`，恢复旧排序。

#### 任务 P2-2: 扩展 `predictions` schema

目标：

- 让预测从“方向提示”升级为“可评估研究对象”。

建议扩展字段：

- `time_horizon`
- `confidence`
- `target_price`
- `target_condition`
- `invalidation_condition`
- `linked_report_date`
- `linked_cluster_id`
- `evaluation_due_at`
- `notes_json` 或 `score_breakdown_json`

改动建议：

1. 通过迁移机制扩展 `predictions` 表。
2. 对 `DailyReport.InvestmentTrend` 增加可选字段。
3. 调整 `src/services/prompts.py`，要求 Strategist 输出更完整的预测结构。
4. `AIService._persist_predictions()` 兼容旧输出和新输出：
   - 旧字段缺失时写默认值。
   - `evaluation_due_at` 由 `time_horizon` 或默认配置推导。
5. 可选增强：
   - 新增 `prediction_evaluations` 表，用于保存多次评分结果，而不是覆盖式更新。

建议新增配置：

- `PREDICTION_DEFAULT_HORIZON_HOURS=24`
- `PREDICTION_ENABLE_MULTI_EVAL=true`

代码触点：

- `src/services/db_service.py`
- `src/services/ai_service.py`
- `src/services/prompts.py`
- `src/config/settings.py`
- `tests/test_db_service.py`
- `tests/test_ai_service.py`

测试补充：

1. 旧版 `investmentTrends` 仍可落库。
2. 新版带 `confidence / timeframe / target_price` 的预测可正确写入。
3. 迁移前已有数据不丢失。

验收标准：

1. 新预测对象能表达“多长时间、为什么、目标是什么、何时失效”。
2. 老版本报告输出不阻塞入库。

#### 任务 P2-3: 重构 scorer 为“按 horizon 评分”

目标：

- 从 10 秒演示打分，升级为按预测期限和目标条件评估。

改动建议：

1. 评分前先检查 `evaluation_due_at`。
2. 支持按 `prediction_type + target_price + confidence + horizon` 计算评分。
3. 最低可实现方案：
   - `directional_accuracy`
   - `return_pct`
   - `target_hit`
   - `confidence_adjusted_score`
4. 若引入 `prediction_evaluations` 表：
   - `predictions` 仅保留当前状态与摘要分。
   - 详细评分写入 `prediction_evaluations`。

建议新增配置：

- `SCORER_MIN_EVAL_SECONDS`
- `SCORER_USE_HORIZON=true`
- `SCORER_NEUTRAL_BAND_PCT=0.2`

代码触点：

- `src/services/scorer.py`
- `src/services/db_service.py`
- `src/config/settings.py`
- `tests/test_scorer.py`

测试补充：

1. 未到期预测不会被评分。
2. 已到期 bullish/bearish/neutral 均能被正确评分。
3. 有 `target_price` 时可计算 target hit。
4. 多次评分结果不会覆盖历史明细。

验收标准：

1. scorer 不再依赖固定 10 秒窗口。
2. 评分结果能说明命中的是方向、收益还是目标价。

回滚方式：

- 关闭 `SCORER_USE_HORIZON`，恢复旧逻辑。

---

## 9. Phase 3: 语义去重与语义聚类

### 9.1 目标

将当前“规则模糊去重 + 两两比较聚类”升级为“规则第一层 + 语义第二层”的双层架构。

### 9.2 实施原则

1. 不立即移除现有标题模糊去重。
2. 先对小规模集合做 embedding，不立即引入外部向量库。
3. 先灰度启用，再默认开启。

### 9.3 任务拆分

#### 任务 P3-1: 引入 embedding 服务与本地缓存

目标：

- 为语义去重、语义聚类、历史召回提供统一 embedding 能力。

改动建议：

1. 新增模块：
   - `src/services/embedding_service.py`
2. 依赖：
   - `sentence-transformers`
3. 初始实现不引入 Qdrant，先做本地缓存。
4. 缓存策略建议：
   - 文本标准化后生成 hash。
   - 将 `hash -> vector` 存在 SQLite 新表或本地文件缓存。
5. 首个版本仅对标题或 `title + short_summary` 建 embedding。

建议新增配置：

- `SEMANTIC_ENABLED=false`
- `SEMANTIC_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2`
- `SEMANTIC_EMBED_BATCH_SIZE=32`

代码触点：

- `src/services/embedding_service.py`（新增）
- `src/services/db_service.py` 或新增 embedding cache 表
- `src/config/settings.py`
- 建议新增 `tests/test_embedding_service.py`

验收标准：

1. 同一标题重复计算时命中缓存。
2. embedding 失败不阻塞主流程。

#### 任务 P3-2: 二级语义去重

目标：

- 在 URL 去重、标题规则去重之后，再增加语义近邻去重。

改动建议：

1. 采集路径保持：
   - URL 去重
   - 标题规则去重
   - 语义去重
2. 语义去重只对规则未命中的候选执行。
3. 初始候选窗口建议限制为最近 `N` 小时或最近 `N` 条标题。
4. 相似度超阈值时标记为语义重复并跳过入库。

建议新增配置：

- `SEMANTIC_DEDUP_ENABLED=false`
- `SEMANTIC_DEDUP_THRESHOLD=0.84`
- `SEMANTIC_DEDUP_HOURS_BACK=48`

代码触点：

- `src/services/collector.py`
- `src/services/db_service.py`
- `src/services/embedding_service.py`
- `tests/test_collector.py`
- `tests/test_db_service.py`

测试补充：

1. 改写标题能命中语义重复。
2. 规则未命中但语义高度相近的标题会被拦截。
3. 明显不同的标题不会误杀。

验收标准：

1. 重复新闻进入上下文的比例下降。
2. 误杀率可控。

回滚方式：

- 关闭 `SEMANTIC_DEDUP_ENABLED`。

#### 任务 P3-3: 语义图聚类

目标：

- 让跨语言、改写标题、后续进展报道拥有更稳定的 cluster。

改动建议：

1. 保留当前 lexical 聚类作为 fallback。
2. 新增语义聚类路径：
   - 计算 embedding
   - 基于 cosine similarity 建近邻图
   - 使用 union-find 或小规模社区算法合并
3. 初版不必追求复杂算法，优先选择：
   - KNN graph + threshold + union-find
4. 先在 `cluster_news()` 中按配置分支实现，不拆出过度复杂的 DAG。

建议新增配置：

- `SEMANTIC_CLUSTER_ENABLED=false`
- `SEMANTIC_CLUSTER_THRESHOLD=0.80`
- `SEMANTIC_CLUSTER_TOP_K=8`

代码触点：

- `src/services/clustering.py`
- `src/services/embedding_service.py`
- `src/config/settings.py`
- `tests/test_pipeline.py`
- 建议新增 `tests/test_clustering_semantic.py`

测试补充：

1. 同事件改写标题被聚到一起。
2. 不同事件不会因共享少量关键词被错误合并。
3. 小规模数据运行耗时可接受。

验收标准：

1. cluster 数量下降但信息覆盖不下降。
2. 平均 cluster 质量提升。

---

## 10. Phase 4: 历史事件缓存与结构化事件层

### 10.1 目标

把“当天新闻聚合”升级为“当天事件 + 历史类比 + 结构化事件对象”。

### 10.2 任务拆分

#### 任务 P4-1: 持久化历史 cluster

目标：

- 将当前一次性 cluster 结果沉淀为后续可检索的历史对象。

改动建议：

1. 新增表：
   - `event_clusters`
2. 最小字段建议：
   - `id`
   - `report_date`
   - `primary_title`
   - `summary`
   - `threat_level`
   - `evidence_score`
   - `source_count`
   - `first_seen`
   - `last_seen`
   - `embedding_model`
   - `embedding_blob` 或引用键
3. 在报告生成完成后持久化当天 cluster 快照。

代码触点：

- `src/services/db_service.py`
- `src/engine.py`
- `src/services/clustering.py`

验收标准：

1. 每次生成报告后，历史 cluster 可被查询。

#### 任务 P4-2: 历史相似事件召回

目标：

- 在生成策略研报前，为 Agent 提供历史类比案例。

改动建议：

1. 新增检索函数：
   - `find_similar_clusters(current_cluster, top_k=3)`
2. 初版使用本地 embedding cache 和 SQLite 存储。
3. 只有当本地规模变大后，才考虑引入 `Qdrant`。
4. 在 `AIService.generate_daily_report()` 中，将历史类比作为 Strategist 的附加上下文，而不是替换现有新闻上下文。

建议新增配置：

- `HISTORY_RECALL_ENABLED=false`
- `HISTORY_RECALL_TOP_K=3`

代码触点：

- `src/services/ai_service.py`
- `src/services/embedding_service.py`
- `src/services/db_service.py`
- 建议新增 `tests/test_history_recall.py`

验收标准：

1. Strategist 输入中可见历史相似事件。
2. 无历史数据时流程不报错。

#### 任务 P4-3: 增加结构化事件抽取层

目标：

- 将 cluster 的自由文本表示升级为标准事件对象。

建议事件结构：

- `who`
- `action`
- `target`
- `where`
- `when`
- `confidence`
- `sources`

改动建议：

1. 新增：
   - `src/services/event_normalizer.py`
2. 初版可以是规则 + 轻量 LLM 混合，而不是全量依赖 LLM。
3. `AIService` 优先消费事件对象列表，再消费原始 cluster 文本。

代码触点：

- `src/services/event_normalizer.py`（新增）
- `src/services/ai_service.py`
- `src/services/clustering.py`
- 建议新增 `tests/test_event_normalizer.py`

验收标准：

1. 生成层输入不再只是新闻堆积文本。
2. 事件对象缺失时仍可回退到现有 cluster 上下文。

---

## 11. Phase 5: Agent 编排与研究评估体系升级

### 11.1 目标

降低手工 prompt orchestration 成本，并将预测评分升级为长期可比较的研究评估体系。

### 11.2 任务拆分

#### 任务 P5-1: 先抽象 provider 适配层，再类型化 Agent

目标：

- 避免直接在 `AIService.call_agent()` 上继续叠加复杂逻辑。

改动建议：

1. 先把 provider 调用抽到单独模块，例如：
   - `src/services/llm_provider.py`
2. 抽象统一接口：
   - `call(messages, model, json_mode, timeout)`
3. 记录每次 agent 调用的元信息：
   - provider
   - model
   - latency
   - retry_count
4. 在此基础上再决定是否引入：
   - `PydanticAI`
   - `LiteLLM`
5. 本轮建议优先级：
   - 先 provider 抽象
   - 再考虑 `PydanticAI`
   - 暂不引入 `LangGraph`

代码触点：

- `src/services/ai_service.py`
- `src/services/llm_provider.py`（新增）
- `tests/test_ai_service.py`

验收标准：

1. AI 调用逻辑与业务编排逻辑解耦。
2. provider 主备切换逻辑可单独测试。

#### 任务 P5-2: 建立研究评估体系

目标：

- 从单一打分升级为可比较的研究质量体系。

建议指标：

- `directional_accuracy`
- `excess_return`
- `horizon_hit_rate`
- `target_hit_rate`
- `calibration`
- `conviction_weighted_score`

改动建议：

1. 若已引入 `prediction_evaluations`，在该表上累计统计。
2. 增加按日期、Agent、信源组合的聚合查询。
3. 后续可以补日报级、Agent 级、source mix 级对比看板。

代码触点：

- `src/services/scorer.py`
- `src/services/db_service.py`
- 可新增 `src/services/research_metrics.py`

验收标准：

1. 能回答“哪个 Agent 输出更可靠”。
2. 能回答“哪些信源组合提升了预测质量”。

---

## 12. 建议新增配置项清单

建议在 `src/config/settings.py` 中逐步增加以下配置，而不是把所有逻辑硬编码：

- `COLLECT_CLASSIFY_ON_INGEST`
- `REPORT_RECLASSIFY_MISSING_ONLY`
- `BACKFILL_THREAT_BATCH_SIZE`
- `EXTRACTOR_USE_TRAFILATURA`
- `EXTRACTOR_MIN_CONTENT_CHARS`
- `EXTRACTOR_FULLTEXT_SOURCE_MAX_TIER`
- `EVIDENCE_SCORE_ENABLED`
- `EVIDENCE_PROPAGANDA_PENALTY`
- `EVIDENCE_MULTI_SOURCE_BONUS`
- `PREDICTION_DEFAULT_HORIZON_HOURS`
- `PREDICTION_ENABLE_MULTI_EVAL`
- `SCORER_USE_HORIZON`
- `SCORER_MIN_EVAL_SECONDS`
- `SEMANTIC_ENABLED`
- `SEMANTIC_MODEL_NAME`
- `SEMANTIC_DEDUP_ENABLED`
- `SEMANTIC_DEDUP_THRESHOLD`
- `SEMANTIC_CLUSTER_ENABLED`
- `SEMANTIC_CLUSTER_THRESHOLD`
- `HISTORY_RECALL_ENABLED`
- `HISTORY_RECALL_TOP_K`

原则：

1. 默认关闭高成本语义特性。
2. 默认开启低风险数据质量特性。

---

## 13. 建议新增测试清单

当前已有测试基础不错，但要支撑这轮改造，建议补以下测试文件：

- `tests/test_extractor.py`
- `tests/test_evidence_service.py`
- `tests/test_embedding_service.py`
- `tests/test_clustering_semantic.py`
- `tests/test_history_recall.py`
- `tests/test_event_normalizer.py`

现有测试需扩展的文件：

- `tests/test_db_service.py`
- `tests/test_collector.py`
- `tests/test_engine.py`
- `tests/test_ai_service.py`
- `tests/test_scorer.py`
- `tests/test_pipeline.py`

每个阶段完成前的最低要求：

1. 新增逻辑必须有对应测试。
2. 全量 `uv run pytest -q` 必须保持通过。

---

## 14. 推荐迭代节奏

如果按单人或小团队节奏推进，建议按以下顺序执行：

### Sprint 1

1. Phase 0 全部完成。
2. Phase 1 的 threat 前移完成。

### Sprint 2

1. `trafilatura` 正文抽取完成。
2. Phase 2 的 evidence score 完成。

### Sprint 3

1. `predictions` schema 扩展。
2. scorer 改为 horizon 驱动。

### Sprint 4

1. embedding service 完成。
2. 语义去重灰度上线。

### Sprint 5

1. 语义聚类完成。
2. 历史 cluster 持久化完成。

### Sprint 6

1. 历史事件召回完成。
2. 结构化事件层完成。
3. 评估是否进入 Agent 编排重构。

---

## 15. 风险点与应对

### 风险 1: SQLite 演进失控

应对：

- 先做 migration 层。
- 扩表优先于重表。
- 新功能字段允许为空。

### 风险 2: 语义能力拖慢主链路

应对：

- 默认关闭。
- 先做缓存。
- 只在规则未命中时调用语义层。

### 风险 3: AI 输出结构升级导致落库失败

应对：

- 新字段全部可选。
- `_persist_predictions()` 兼容旧 schema。
- JSON 修复链路保留。

### 风险 4: 抽取质量提升不明显

应对：

- 保留 `BeautifulSoup` fallback。
- 加入提取方法与成功率日志。
- 针对 T1/T2 样本手工抽查。

### 风险 5: 评分逻辑变复杂后难解释

应对：

- 保留 score breakdown。
- 将方向命中、目标命中、收益命中拆开记录。

---

## 16. 最小可交付版本定义

若需要快速交付一个真正有价值的中间版本，建议以以下内容作为第一里程碑：

1. 引入 migration 机制。
2. threat classification 前移入库。
3. `trafilatura` 替换正文抽取主路径。
4. evidence score 进入 cluster 排序。
5. `predictions` 增加 `time_horizon / confidence / linked_report_date / evaluation_due_at`。
6. scorer 按 `evaluation_due_at` 评分。

这个版本完成后，项目就会从“能跑通闭环”升级为“数据结构更完整、排序更合理、评分更可信”的版本。

---

## 17. 本计划对应的推荐实施顺序

最终建议直接按下面顺序实施：

1. `migrations`
2. `threat on ingest`
3. `trafilatura extractor`
4. `evidence score`
5. `predictions/scorer refactor`
6. `embedding cache`
7. `semantic dedup`
8. `semantic clustering`
9. `historical recall`
10. `event normalization`
11. `provider abstraction`
12. `research evaluation`

这个顺序的核心原因是：

1. 先补底层数据与 schema，收益最确定。
2. 再补输入质量和排序质量，直接提升日报质量。
3. 再做语义能力，避免在脏数据上加复杂度。
4. 最后做平台化，避免过早工程化。

---

*Last aligned with codebase on 2026-03-12.*
