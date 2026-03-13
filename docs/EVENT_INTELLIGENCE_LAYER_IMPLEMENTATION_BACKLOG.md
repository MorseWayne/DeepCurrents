# Event Intelligence Layer 实施 Backlog

**版本**: v1.0  
**状态**: 可按 Batch 直接执行  
**来源文档**: `docs/superpowers/specs/2026-03-13-event-intelligence-layer-design.md`、`docs/EVENT_INTELLIGENCE_LAYER_ROADMAP.md`  
**适用范围**: `src/` Python 主链路  
**建议执行单位**: 1 ticket = 1 个可独立合并的 PR

---

## 0. 开发进度

- 更新时间: 2026-03-13
- 当前批次: `Batch 5`
- 已完成:
  1. `EIL-000`：已落地 `tests/fixtures/event_intelligence/`、`tests/evaluation/fixture_loader.py`、`tests/test_event_intelligence_fixture_loader.py`，固定三类评估样本并提供可重复加载入口。
  2. `EIL-001`：已在 `src/config/settings.py` 增加 Event Intelligence runtime 配置项，在 `src/services/event_intelligence_bootstrap.py` 建立最小 bootstrap 骨架，并接入 `src/engine.py` / `src/run_report.py` 的共享启动路径。
  3. `EIL-002`：已完成 `src/services/postgres_store.py`、`src/services/vector_store.py`、`src/services/cache_service.py` 的最小 async 接入层，并在 `src/services/event_intelligence_bootstrap.py` 中补齐超时、重试、健康检查、幂等启动和部分启动失败清理逻辑；同时更新 `.env.example`、`requirements.txt` 和相关测试。
  4. `EIL-003`：已新增 `src/services/schema_bootstrap.py`，完成 12 张核心表及索引/外键的 PostgreSQL 初始化，并接入 `src/services/event_intelligence_bootstrap.py` 的统一启动路径；同时补齐 `tests/test_schema_bootstrap.py` 与启动失败清理测试。
  5. `EIL-004`：已新增 `src/services/article_repository.py`、`src/services/event_repository.py`、`src/services/brief_repository.py`、`src/services/report_repository.py`，补齐 article / event / brief / report 四类 repository 的最小 CRUD 与查询边界，并通过 `tests/test_event_intelligence_repositories.py` 固化 SQL 与序列化契约。
  6. `EIL-101`：已新增 `src/services/article_models.py`，落地 `ArticleRecord` 标准化文章模型、最小字段校验以及 `from_mapping()` / `from_repository_row()` / `to_article_payload()` / `to_feature_seed()` helper，并通过 `tests/test_article_models.py` 与 repository 契约测试固定序列化行为。
  7. `EIL-102`：已新增 `src/services/article_normalizer.py`，落地 URL canonicalization、标题/正文清洗、时间标准化、语言识别、exact hash / simhash 生成，并通过 `tests/test_article_normalizer.py` 固定 collector 风格输入与中英文样本行为。
  8. `EIL-103`：已新增 `src/services/article_feature_extractor.py`，打通 `ArticleRecord.to_feature_seed()` -> embedding / entities / keywords / quality score 生成 -> `article_features` 写入，并在 `src/services/vector_store.py` 增加 Qdrant collection ensure / point upsert 能力；同时补齐 `tests/test_article_feature_extractor.py` 与 `tests/test_event_intelligence_stores.py` 的契约测试。
  9. `EIL-104`：已将 `src/services/collector.py` 的采集主路径切换为 `collector -> article_normalizer -> article_repository -> article_feature_extractor`，并在写入成功后通过 legacy mirror 兼容写入旧 `raw_news`；同时补齐 `tests/test_collector.py` 对 article-first 顺序、feature failure 容错和 legacy mirror failure 容错的集成验证。
  10. `EIL-105`：已新增 `src/services/semantic_deduper.py`，完成 cheap dedup（exact + near）与 semantic dedup 两段式流程，并将 exact / near / semantic 关系幂等写入 `article_dedup_links`；同时通过 `tests/test_semantic_deduper.py` 与 collector 集成测试固定 article-first 顺序和 dedup 容错行为。
  11. `EIL-201`：已在 `src/services/event_builder.py` 落地事件候选检索与“加入已有事件 / 创建新事件”分流主路径，完成 `events` / `event_members` 写入与计数字段维护，并通过 `tests/test_event_builder.py` 固化 article-to-event 映射契约。
  12. `EIL-202`：已新增 `src/services/event_state_machine.py`，并在 `src/services/event_builder.py` 中接入 embedding / 实体 / 区域 / 时间 / 冲突规则的多信号合并判定、`new|active|updated|escalating|stabilizing|resolved|dormant` 状态机和 `event_state_transitions` 审计写入；同时补齐 `tests/test_event_state_machine.py`、`tests/test_event_builder.py` 与 `tests/test_engine.py` 的迁移与接线测试。
  13. `EIL-203`：已新增 `src/services/event_enrichment.py`，完成从 `event_members + articles + article_features + event_state_transitions` 聚合 regions / entities / assets / market channels / supporting sources / contradicting sources，并将 enrichment 写回 `events.primary_region`、`events.event_type` 与 `events.metadata.enrichment`；同时在 `src/services/collector.py` / `src/engine.py` 接入事件增强主路径，并补齐 `tests/test_event_enrichment.py`、`tests/test_collector.py` 与 `tests/test_engine.py` 的聚合与接线测试。
  14. `EIL-204`：已新增 `src/services/event_query_service.py`，统一提供事件列表查询、时间线回放和调试视图，并复用 `event_enrichment`、`event_state_transitions`、`article_dedup_links` 与 `event_scores` 生成结构化输出；同时在 `src/services/event_repository.py` 补齐 `list_event_scores()`，并通过 `tests/test_event_query_service.py` 与 repository 回归测试固定查询契约。
  15. `EIL-301`：已新增 `src/services/event_ranker.py`，完成 `threat_score / market_impact_score / novelty_score / corroboration_score / source_quality_score / velocity_score / uncertainty_score` 七维规则版打分、`macro_daily` 总分聚合和 `event_scores` 持久化，并通过 `tests/test_event_ranker.py` 固化高影响事件优先、单源冲突事件降权和分数写入契约。
  16. `EIL-302`：已新增 `src/services/scoring_profiles.py`，将 `macro_daily / risk_daily / strategy_am` 三套 scoring profile 从 `event_ranker` 中抽离，并把 explainability 收敛为 `profile / dimension_scores / weighted_contributions / top_drivers / risk_flags / event_facts` 的稳定结构；同时补齐 `tests/test_event_ranker.py`，验证不同 profile 下排序差异可复现、解释结构完整、未知 profile 明确报错。
  17. `EIL-303`：已新增 `src/services/evidence_selector.py`，完成文章级 evidence package 选择器，按高 Tier、独立信源、数字/政策信号和覆盖多样性为事件压缩 supporting / contradicting 证据，并在有冲突叙事时保留反方证据位；同时补齐 `tests/test_evidence_selector.py`，验证去冗余、冲突保留和按排序结果批量生成证据包的契约。
  18. `EIL-601`：已新增 `src/services/metrics.py`，建立 ingestion / ranking / evidence / report 四阶段指标汇总与结构化日志 helper，并在 `collector`、`event_ranker`、`evidence_selector`、`ai_service`、`engine` 接入运行时指标输出；同时补齐 `tests/test_metrics.py` 及相关服务测试，固定压缩率、单源比例、冲突保留率和 report budget 指标契约。
  19. `EIL-401`：已新增 `src/services/event_summarizer.py`，完成规则版 `event_brief` 生成与持久化，把 `event_query_service + evidence_selector + event_ranker` 的结构化输出收敛为稳定事件卡 schema，并写入 `event_briefs`；同时补齐 `tests/test_event_summarizer.py`，验证字段结构、冲突保留和 ranked briefs 顺序契约。
  20. `EIL-402`：已新增 `src/services/theme_summarizer.py`，基于固定 taxonomy 和 `region:*` 补充桶，将 ranked `event_brief` 聚合为规则版 `theme_brief`，并写入 `theme_briefs`；同时补齐 `tests/test_theme_summarizer.py`，验证主题归类、区域桶生成、结构化输出和无匹配主题时的失败契约。
  21. `EIL-403`：已新增 `src/services/report_context_builder.py`，完成 event/theme brief 驱动的 report context 组装、预算裁剪和多样性约束，并输出结构化 `context_package` 与 prompt-ready 文本块；同时补齐 `tests/test_report_context_builder.py`，验证预算紧张时的主题优先裁剪、事件轻量降级、同主题/同区域去挤占和服务层接线契约。
  22. `EIL-404`：已新增 `src/services/context_quota_policy.py`，将 `macro_daily / risk_daily / strategy_am` 三套上下文预算与多样性上限从 `report_context_builder` 中抽离；同时扩展 `src/utils/market_data.py`，新增结构化 `market_context` snapshot 与渲染 helper，并让 `report_context_builder` 支持 policy 驱动的预算分配、region theme 上限和结构化市场上下文渲染。
  23. `EIL-501`：已新增 `src/services/report_models.py`，将 `DailyReport` 及其相关输出模型从 `ai_service.py` 中抽离，并补充 `MacroAnalystOutput`、`SentimentAnalystOutput` 两个 v2 agent 输出 schema；同时重写 `src/services/prompts.py`，新增 event-centric Prompt v2 和 3 个输入拼装 helper，并保持旧 prompt 常量与 `ai_service` 顶层导出兼容。
  24. `EIL-502`：已新增 `src/services/report_orchestrator.py`，把 event-centric report flow 从 `ai_service.py` 中拆成独立 orchestrator，统一编排 context builder、Prompt v2、多智能体调用、strategist 输入 guard、JSON 解析、指标回写和预测持久化；同时保留 `AIService.generate_daily_report()` 作为兼容旧文章级入口，并补齐 `tests/test_report_orchestrator.py` 验证新主路径。
  25. `EIL-503`：已新增 `src/services/report_run_tracker.py`，将 `report_runs` 与 `report_event_links` 的落库、trace 回放与最新报告追溯封装为独立 service；同时扩展 `src/services/report_repository.py` 增加 `list_report_runs()`，让 `report_orchestrator` 在 event-centric 报告生成成功后自动写回报告元信息、事件链接和状态变化追溯，并补齐 tracker / repository / orchestrator 三层测试。
- 下一步:
  1. `EIL-504`：重接 engine / run_report / 调度入口，彻底切出旧文章级报告路径。
  2. `EIL-602`：补齐统一回归评估 runner，为报告栈重接后的质量回归准备固定基线。
  3. `EIL-603`：引入人工反馈与标注闭环，把 report trace 反接到后续调优链路。

---

## 1. 文档目的

本文档把 Event Intelligence Layer 的设计文档和路线图进一步压缩为可执行 backlog，用于指导后续逐模块实施。

它回答三个问题:

1. 先做哪些 ticket，后做哪些 ticket。
2. 每个模块需要交付什么、依赖什么、验收到什么程度。
3. 哪些 ticket 可以并行，哪些必须串行。

---

## 2. 使用规则

### 2.1 Ticket 粒度

1. 每张 ticket 尽量控制为 1 个 PR。
2. 单元测试、集成测试、日志埋点和必要文档更新默认包含在 ticket 内，不单独拆票。
3. 若某 ticket 明显超过 3 天实现量，应继续细分，而不是硬做成超大 PR。

### 2.2 执行顺序

1. 优先按 Batch 顺序推进。
2. 同一 Batch 内，只有在依赖满足时才并行。
3. 不允许跳过 foundation 直接实现上层摘要或 prompt。

### 2.3 完成定义

任一 ticket 只有同时满足以下条件才算完成:

1. 代码已落地到目标模块。
2. 验收标准全部满足。
3. 对应测试已补齐并通过。
4. 关键日志或指标可观测。

### 2.4 目录约定

默认仍沿用当前 `src/services/` 为主目录，只在必要时新增少量配套模块。若实施过程中平铺模块明显失控，再额外拆分子目录。

---

## 3. Batch 总览

| Batch | Tickets | 目标 | 并行建议 |
| --- | --- | --- | --- |
| Batch 0 | EIL-000 ~ EIL-004 | 冻结契约、评估集、基础设施和 repository 边界 | 以串行为主 |
| Batch 1 | EIL-101 ~ EIL-104 | 跑通文章标准化与入库主路径 | `EIL-102` / `EIL-103` 可局部并行 |
| Batch 2 | EIL-105、EIL-201 ~ EIL-204 | 跑通 dedup、事件构建、状态机和查询 | `EIL-203` / `EIL-204` 可在事件主链稳定后并行 |
| Batch 3 | EIL-301 ~ EIL-303、EIL-601 | 建立排序、证据压缩和指标观测 | `EIL-302` / `EIL-601` 可并行 |
| Batch 4 | EIL-401 ~ EIL-404 | 建立 event brief、theme brief 和 context builder | `EIL-402` / `EIL-404` 可在 `EIL-401` 后局部并行 |
| Batch 5 | EIL-501 ~ EIL-504 | 完成报告栈重写并接入主引擎 | `EIL-503` 可在 orchestrator 稳定后并行 |
| Batch 6 | EIL-602 ~ EIL-604 | 完成评估闭环、反馈闭环和旧模块删除 | `EIL-602` / `EIL-603` 可并行，`EIL-604` 最后做 |

---

## 4. Batch 0 - Foundation

### [x] EIL-000: 评估样本与基准契约冻结

- 主要模块: `tests/fixtures/`、`tests/evaluation/`、`docs/`
- 主要工作:
  1. 固化 duplicate pair、same-event pair、top-N relevance 三类样本。
  2. 定义统一评估输入输出格式，避免后续模块各自造数据契约。
  3. 为后续回归评估准备可重复执行的 fixture 装载方式。
- 依赖: 无
- 产出物:
  1. 评估样本目录结构。
  2. 样本说明文档。
  3. 基础加载器或 fixture helper。
- 验收标准:
  1. 样本可被测试直接加载。
  2. 后续 dedup / event / ranking ticket 可以复用同一套样本。

### [x] EIL-001: 运行时配置与目标架构开机骨架

- 主要模块: `src/config/settings.py`、`src/main.py`、`src/engine.py`
- 主要工作:
  1. 引入新架构所需配置项，包括 PostgreSQL、Qdrant、Redis、embedding、reranker、report profile。
  2. 设计新的 app bootstrap 顺序，避免继续把 `db_service.py` 当成系统初始化中心。
  3. 明确新旧引擎入口边界，给后续 event-centric engine 留位置。
- 依赖: EIL-000
- 产出物:
  1. 新配置字段清单。
  2. 运行时初始化骨架。
  3. 基础启动测试。
- 验收标准:
  1. 新配置缺失时能明确报错。
  2. 应用能完成最小启动并初始化依赖容器。

### [x] EIL-002: PostgreSQL / Qdrant / Redis 基础接入层

- 主要模块: `src/services/postgres_store.py`、`src/services/vector_store.py`、`src/services/cache_service.py`
- 主要工作:
  1. 建立事务存储、向量索引、缓存/任务中转的基础客户端封装。
  2. 统一连接生命周期、超时、重试与健康检查。
  3. 为后续 repository 与 dedup / event builder 提供稳定接口。
- 依赖: EIL-001
- 产出物:
  1. 三类基础接入模块。
  2. 健康检查函数。
  3. 本地开发配置示例。
- 验收标准:
  1. 应用启动时能完成依赖健康检查。
  2. 测试环境可替换为本地或内存化 stub。

### [x] EIL-003: 新 schema 初始化与核心表创建

- 主要模块: `src/services/schema_bootstrap.py`
- 主要工作:
  1. 建立 `articles`、`article_features`、`article_dedup_links`、`events`、`event_members`、`event_scores`、`event_state_transitions`、`event_briefs`、`theme_briefs`、`report_runs`、`report_event_links`、`evaluation_labels`。
  2. 明确索引、唯一键、时间字段和审计字段。
  3. 把 schema 初始化从旧 SQLite 表初始化逻辑中完全分离。
- 依赖: EIL-002
- 产出物:
  1. schema bootstrap 模块。
  2. 建表说明文档。
  3. 初始化测试。
- 验收标准:
  1. 新库可一键完成建表。
  2. 核心唯一性和外键关系满足设计预期。

### [x] EIL-004: Repository 边界与基础 CRUD

- 主要模块: `src/services/article_repository.py`、`src/services/event_repository.py`、`src/services/brief_repository.py`、`src/services/report_repository.py`
- 主要工作:
  1. 明确 article / event / brief / report 四类 repository 的职责边界。
  2. 提供最小可用 CRUD 和查询接口。
  3. 为后续服务层提供稳定的读写抽象，避免服务直接拼 SQL。
- 依赖: EIL-003
- 产出物:
  1. 四类 repository。
  2. 基础模型序列化/反序列化逻辑。
  3. repository 级单测。
- 验收标准:
  1. 上层服务无需直接依赖底层表结构。
  2. 核心插入、查询、更新路径均有测试覆盖。

---

## 5. Batch 1 - Article Ingestion

### [x] EIL-101: `ArticleRecord` 契约与标准化字段模型

- 主要模块: `src/services/article_models.py`
- 主要工作:
  1. 定义标准化文章对象及字段约束。
  2. 明确 `canonical_url`、`normalized_title`、`clean_content`、`language`、`quality_score` 等字段语义。
  3. 为 collector、normalizer、repository 建立统一输入输出模型。
- 依赖: EIL-004
- 产出物:
  1. 文章域模型。
  2. 示例数据与序列化测试。
- 验收标准:
  1. collector 与 article repository 能共享同一模型。
  2. 关键字段存在明确校验规则。

### [x] EIL-102: `article_normalizer` 实现

- 主要模块: `src/services/article_normalizer.py`
- 主要工作:
  1. 实现 URL canonicalization。
  2. 实现标题/正文清洗、时间标准化、语言识别。
  3. 生成 exact hash、simhash、基础 content fingerprint。
- 依赖: EIL-101
- 产出物:
  1. article normalizer 主模块。
  2. 中英文标准化测试样本。
- 验收标准:
  1. 相同 URL 变体会落到同一 canonical form。
  2. 脏文本、空正文、异常时间格式均可稳定处理。

### [x] EIL-103: 文章特征提取流程

- 主要模块: `src/services/article_feature_extractor.py`
- 主要工作:
  1. 为标准化文章生成 embedding、entities、keywords、quality score。
  2. 将特征写入 `article_features`。
  3. 与向量存储建立写入同步逻辑。
- 依赖: EIL-101、EIL-002、EIL-004
- 产出物:
  1. 特征提取服务。
  2. `article_features` 写入逻辑。
  3. 向量写入测试。
- 验收标准:
  1. 新文章入库后可查询到完整特征。
  2. 特征提取失败不会破坏文章主记录写入。

### [x] EIL-104: `collector -> normalizer -> repository` 主路径重接

- 主要模块: `src/services/collector.py`、`src/engine.py`
- 主要工作:
  1. 将 collector 输出从“原始新闻 dict”切换为标准化文章对象。
  2. 在采集阶段接入 normalizer、feature extractor 和 article repository。
  3. 让入库入口不再围绕旧 `db_service.save_news()` 组织。
- 依赖: EIL-102、EIL-103
- 产出物:
  1. 新的文章入库主路径。
  2. 采集到入库的集成测试。
- 验收标准:
  1. 抓取结果能稳定落到 `articles` 与 `article_features`。
  2. 入库主路径不再依赖旧 `raw_news` 表结构。
- 当前实现说明:
  1. `src/services/collector.py` 已优先执行标准化文章入库与 feature extraction，仅将旧 `raw_news` 写入保留为兼容 mirror，不再作为新主路径的组织中心。
  2. `tests/test_collector.py` 已覆盖 article-first 持久化顺序、feature extraction failure 不阻断 article 写入，以及 legacy mirror failure 不阻断采集成功。

### [x] EIL-105: `semantic_deduper` 与关系写入

- 主要模块: `src/services/semantic_deduper.py`
- 主要工作:
  1. 建立 ingestion gate 的 cheap dedup。
  2. 基于向量近邻、时间窗、实体重叠实现 semantic dedup 候选判定。
  3. 将 exact / near / semantic 关系写入 `article_dedup_links`。
- 依赖: EIL-103、EIL-104
- 产出物:
  1. dedup 服务。
  2. dedup reason / confidence 日志。
  3. dedup 评估测试。
- 验收标准:
  1. duplicate pair 标注集上的识别率达到目标区间。
  2. 语义关系可查询、可回放。
- 当前实现说明:
  1. `src/services/semantic_deduper.py` 已提供 cheap dedup（exact + near）与 semantic dedup 两段式流程；near 阶段会跳过已由 exact 阶段命中的候选，避免重复写入 relation。
  2. `src/services/collector.py` 已按 article-first 顺序接入：`create_article -> link_cheap_duplicates -> extract_and_persist -> link_semantic_duplicates -> legacy mirror`；feature/dedup 异常均为 best-effort，不阻断采集成功。
  3. `src/services/vector_store.py` 已提供 `query_similar_points()` 并兼容 `query_points`/`search`/`search_points` 客户端路径，semantic dedup 可直接复用。
  4. `src/services/article_repository.py` 的 `create_dedup_link()` 使用 `ON CONFLICT (left_article_id, right_article_id, relation_type) DO UPDATE`，保证 exact/near/semantic link 幂等更新。
- 验证记录:
  1. `.venv/bin/pytest tests/test_semantic_deduper.py tests/test_event_intelligence_stores.py tests/test_collector.py tests/test_engine.py` 通过（22 passed）。
  2. `.venv/bin/pytest tests/test_article_feature_extractor.py tests/test_event_intelligence_repositories.py` 通过（12 passed）。

---

## 6. Batch 2 - Event Layer

### [x] EIL-201: `event_builder` 候选检索与事件新建

- 主要模块: `src/services/event_builder.py`
- 主要工作:
  1. 为新文章检索时间窗内相似事件候选。
  2. 实现“加入已有事件”与“创建新事件”的基本分流。
  3. 将事件主记录和成员映射写入 `events` / `event_members`。
- 依赖: EIL-105、EIL-004
- 产出物:
  1. event builder 主流程。
  2. 文章到事件映射测试。
- 验收标准:
  1. 新文章能够稳定落入某个 `event_id`。
  2. 事件对象具备时间边界和代表标题。
- 当前实现说明:
  1. `src/services/event_builder.py` 已新增 `EventBuilder.assign_article_to_event()` 主流程：按时间窗调用 `EventRepository.list_recent_events()` 检索候选，基于标题相似度在“加入已有事件 / 创建新事件”间分流。
  2. 新事件路径会写入 `events` 与 `event_members`：`create_event()` 落 `canonical_title`、`started_at`、`latest_article_at`、计数字段；首篇成员按 `primary` 写入。
  3. 已有事件路径会写入 `event_members` 并更新 `events` 时间边界与计数：维护 `started_at` 最小值、`latest_article_at` 最大值、`article_count` 与 `source_count`。
  4. `tests/test_event_builder.py` 已覆盖两条主分流：无匹配候选时新建事件、有匹配候选时加入既有事件并断言时间边界/代表标题/计数字段。
- 验证记录:
  1. `uv run pytest tests/test_event_builder.py tests/test_semantic_deduper.py tests/test_event_intelligence_repositories.py` 通过（15 passed）。

### [x] EIL-202: 事件合并判定与状态机迁移

- 主要模块: `src/services/event_builder.py`、`src/services/event_state_machine.py`
- 主要工作:
  1. 实现 embedding、实体、区域、时间、冲突规则的多信号合并判定。
  2. 定义 `new / active / updated / escalating / stabilizing / resolved / dormant` 的状态迁移规则。
  3. 将迁移记录写入 `event_state_transitions`。
- 依赖: EIL-201
- 产出物:
  1. 状态机模块。
  2. 状态迁移测试。
  3. 误合并/漏合并回放样例。
- 验收标准:
  1. same-event pair 标注集上合并结果达到目标区间。
  2. 每次状态变化均有可审计记录。
- 当前实现说明:
  1. `src/services/event_state_machine.py` 已新增确定性状态机：覆盖 `new / active / updated / escalating / stabilizing / resolved / dormant` 迁移判断，并暴露独立的 dormancy 评估入口。
  2. `src/services/event_builder.py` 已从单一标题相似度升级为多信号合并判定：综合标题、embedding 近邻、实体重叠、区域重叠、时间邻近度和动作冲突规则来决定“并入既有事件 / 新建事件”。
  3. 事件创建路径会写入 `event_state_transitions` 的初始 `new` 迁移；既有事件在 `active / updated / escalating / stabilizing / resolved` 之间发生变化时，也会记录带 merge signal 摘要的审计日志。
  4. `src/engine.py` 已在 runtime wiring 中为 `EventBuilder` 注入 vector store，确保 ingestion 主路径能直接复用 article embedding 做事件合并判定。
- 验证记录:
  1. `.venv/bin/pytest tests/test_event_state_machine.py tests/test_event_builder.py tests/test_engine.py` 通过（18 passed）。
  2. `.venv/bin/pytest tests/test_collector.py tests/test_semantic_deduper.py tests/test_event_intelligence_repositories.py` 通过（20 passed）。

### [x] EIL-203: `event_enrichment` 结构化标签聚合

- 主要模块: `src/services/event_enrichment.py`
- 主要工作:
  1. 聚合 regions、entities、assets、market channels。
  2. 区分 supporting sources 与 contradicting sources。
  3. 让事件对象具备可排序、可摘要的结构化附加信息。
- 依赖: EIL-201、EIL-202
- 产出物:
  1. event enrichment 服务。
  2. enrichment 查询接口。
- 验收标准:
  1. 高价值事件具备稳定的结构化标签。
  2. 冲突叙事可以被显式保留。
- 当前实现说明:
  1. `src/services/event_enrichment.py` 已新增 `EventEnrichmentService`，可从 `event_members + articles + article_features + event_state_transitions` 聚合 `regions / entities / assets / market_channels / event_type / supporting_sources / contradicting_sources / last_transition`。
  2. enrichment 结果会写回 `events.primary_region`、`events.event_type` 和 `events.metadata.enrichment`，并提供 `enrich_event()` / `get_event_enrichment()` 两个入口供后续 `EIL-204` 直接复用。
  3. `src/services/collector.py` 已在 `event_builder` 之后追加 event enrichment，`src/engine.py` 已把 `EventEnrichmentService` 接到 runtime wiring，保证 ingestion 主链路能持续刷新事件增强信息。
- 验证记录:
  1. `.venv/bin/pytest tests/test_event_enrichment.py tests/test_collector.py tests/test_engine.py` 通过（17 passed）。
  2. `.venv/bin/pytest tests/test_event_builder.py tests/test_event_state_machine.py tests/test_semantic_deduper.py tests/test_event_intelligence_repositories.py` 通过（24 passed）。

### [x] EIL-204: 事件检索、回放与调试接口

- 主要模块: `src/services/event_query_service.py`
- 主要工作:
  1. 提供按 `event_id`、时间窗、状态、主题的查询接口。
  2. 提供事件成员、状态迁移、证据关系的回放视图。
  3. 为后续评估、人工 review 和调试提供统一入口。
- 依赖: EIL-202、EIL-203
- 产出物:
  1. 事件查询服务。
  2. 调试用序列化输出。
- 验收标准:
  1. 任一事件都可回放其成员与状态变化。
  2. 评估和摘要模块无需直接拼底层多表查询。
- 当前实现说明:
  1. `src/services/event_query_service.py` 已新增 `EventQueryService`，提供 `list_events()`、`get_event_timeline()`、`get_event_debug_view()` 三个入口，统一封装事件列表查询、时间线回放和调试视图。
  2. `list_events()` 已支持按 `event_id`、时间窗、状态过滤，并使用 `event_type` 与 `metadata.enrichment.market_channels` 的近似匹配实现轻量主题过滤。
  3. `get_event_timeline()` 会统一返回 `event / members / transitions / enrichment / scores`；`get_event_debug_view()` 会进一步聚合成员文章、去重关系和规则化 debug notes，便于排查误合并、单源事件和去重命中情况。
  4. `src/services/event_repository.py` 已补齐 `list_event_scores()`，使查询服务无需直接拼接 `event_scores` 的底层 SQL。
- 验证记录:
  1. `.venv/bin/pytest tests/test_event_query_service.py tests/test_event_intelligence_repositories.py` 通过（13 passed）。
  2. `.venv/bin/pytest tests/test_event_builder.py tests/test_event_state_machine.py tests/test_event_enrichment.py tests/test_collector.py tests/test_engine.py tests/test_semantic_deduper.py` 通过（31 passed）。

---

## 7. Batch 3 - Ranking, Evidence, Metrics

### [x] EIL-301: `event_ranker` 核心打分引擎

- 主要模块: `src/services/event_ranker.py`
- 主要工作:
  1. 实现 `threat_score`、`market_impact_score`、`novelty_score`、`corroboration_score`、`source_quality_score`、`velocity_score`、`uncertainty_score`。
  2. 将多维分数写入 `event_scores`。
  3. 提供总分计算和排序接口。
- 依赖: EIL-203
- 产出物:
  1. event ranker。
  2. 事件排序测试。
- 验收标准:
  1. 事件可按多维分数稳定排序。
  2. 高频但低价值事件不再轻易冲到前列。
- 当前实现说明:
  1. `src/services/event_ranker.py` 已新增 `EventRanker`，提供 `score_event()`、`score_events()`、`rank_events()` 三个入口，直接复用 `event_query_service.get_event_timeline()` 做规则版事件打分。
  2. 当前实现已覆盖 `threat_score / market_impact_score / novelty_score / corroboration_score / source_quality_score / velocity_score / uncertainty_score` 七个维度，并用内置 `macro_daily` 权重合成 `total_score`。
  3. 评分结果会通过 `EventRepository.upsert_event_score()` 持久化到 `event_scores`，同时在 `payload` 中保存权重与解释信息，供后续 `EIL-302` 扩展 profile 和 explainability。
  4. `rank_events()` 已支持按状态、时间窗、主题过滤事件并返回按总分排序的结果，作为后续 `EIL-303` / `EIL-401` 的输入基础。
- 验证记录:
  1. `.venv/bin/pytest tests/test_event_ranker.py tests/test_event_intelligence_repositories.py` 通过（13 passed）。
  2. `.venv/bin/pytest tests/test_event_builder.py tests/test_event_state_machine.py tests/test_event_enrichment.py tests/test_event_query_service.py tests/test_collector.py tests/test_engine.py tests/test_semantic_deduper.py` 通过（34 passed）。

### [x] EIL-302: 评分 profile 与解释日志

- 主要模块: `src/services/scoring_profiles.py`
- 主要工作:
  1. 定义宏观日报、风险日报、策略晨报等不同 weighting profile。
  2. 输出每个事件分数的解释结构，便于人工校验。
  3. 为未来调参保留 profile 切换能力。
- 依赖: EIL-301
- 产出物:
  1. scoring profile 配置。
  2. explainability 输出结构。
- 验收标准:
  1. 不同 profile 作用于同一事件集时排序可复现。
  2. 每个高分事件都能解释其高分来源。
- 当前实现说明:
  1. `src/services/scoring_profiles.py` 已定义 `ScoringProfile` 和 `get_scoring_profile()`，内置 `macro_daily`、`risk_daily`、`strategy_am` 三套权重、标签和说明文本。
  2. `src/services/event_ranker.py` 已改为在公开入口处解析 profile，并将 `event_scores.payload.explanation` 收敛为 `profile / dimension_scores / weighted_contributions / top_drivers / risk_flags / event_facts` 的稳定结构。
  3. `rank_events()` 现在会在同一 profile 下按 `total_score` 和 `event_id` 稳定排序，避免相同事件集重复排序时出现不确定结果。
  4. 未知 profile 会在评分入口直接抛出明确的 `ValueError`，避免静默回退到默认权重。
- 验证记录:
  1. `.venv/bin/pytest tests/test_event_ranker.py` 通过（5 passed）。
  2. `.venv/bin/pytest tests/test_event_builder.py tests/test_event_state_machine.py tests/test_event_enrichment.py tests/test_event_query_service.py tests/test_collector.py tests/test_engine.py tests/test_semantic_deduper.py` 通过。

### [x] EIL-303: `evidence_selector` 证据压缩

- 主要模块: `src/services/evidence_selector.py`
- 主要工作:
  1. 为每个高价值事件选出少量代表证据文章或证据句。
  2. 优先多样性、高 Tier、独立信源和数字/政策信息。
  3. 对冲突叙事保留正反证据。
- 依赖: EIL-203、EIL-301
- 产出物:
  1. evidence selector。
  2. evidence package 数据结构。
- 验收标准:
  1. 每个入选事件都有紧凑证据包。
  2. 重复同义证据数量显著下降。
- 当前实现说明:
  1. `src/services/evidence_selector.py` 已新增 `EvidenceSelector`，提供 `select_event_evidence()` 和 `select_ranked_event_evidence()` 两个 service 入口，分别用于单事件和批量已排序事件的证据压缩。
  2. 当前实现先采用文章级 evidence package，不做句级摘录；输出结构固定为 `event_id / profile / event_score / supporting_evidence / contradicting_evidence / coverage_notes / selection_metadata`。
  3. 证据选择规则会综合 `event_query_service` 时间线、`event_ranker` 总分、文章 Tier / source type、primary 角色、数字/政策信号、已覆盖 source 和关键词/实体覆盖，优先保留独立高质量证据并压低重复来源。
  4. 当事件存在 `contradicting_sources` 或 transition 中显式 conflict article 时，selector 会为 `contradicting_evidence` 保留至少一个证据位，避免后续摘要链路只看单边叙事。
- 验证记录:
  1. `.venv/bin/pytest tests/test_evidence_selector.py` 通过（3 passed）。
  2. `.venv/bin/pytest tests/test_evidence_selector.py tests/test_event_ranker.py tests/test_event_query_service.py` 通过（11 passed）。
  3. `.venv/bin/pytest tests/test_event_enrichment.py` 通过（3 passed）。

### [x] EIL-601: 运行指标与结构化日志

- 主要模块: `src/services/metrics.py`、`src/engine.py`
- 主要工作:
  1. 落地原始文章数、dedup 命中数、文章到事件压缩比、单源事件比例、事件卡进入报告比例、预算截断率等指标。
  2. 为 ranking、brief、report 各阶段输出结构化日志。
  3. 让 ticket 验收不再依赖手工肉眼抽查。
- 依赖: EIL-104、EIL-201、EIL-301
- 产出物:
  1. 指标汇总模块。
  2. 关键阶段日志埋点。
- 验收标准:
  1. 每次运行都能输出核心质量计数。
  2. 指标字段与设计文档保持一致。
- 当前实现说明:
  1. `src/services/metrics.py` 已新增 `safe_ratio()`、阶段指标 builder 和 `log_stage_metrics()`，统一输出 `pipeline_metrics` 结构化日志事件。
  2. `src/services/collector.py` 现已返回扩展 ingestion metrics，包括 `articles_seen / articles_inserted / duplicate_refreshes / cheap_dedup_links / semantic_dedup_links / events_created / events_updated / events_touched / article_to_event_compression_ratio`，同时保留 `new_items / errors / skipped` 兼容字段。
  3. `src/services/event_ranker.py` 与 `src/services/evidence_selector.py` 已分别接入 `ranking`、`evidence` 阶段指标输出，并保留最近一次 `last_ranking_metrics` / `last_evidence_metrics` 快照，便于测试和后续调试。
  4. `src/services/ai_service.py` 已保存最近一次 report guard/budget metrics；`src/engine.py` 已在 `collect_data()` 和 `generate_and_send_report()` 输出 `ingestion`、`report` 阶段结构化日志，而不新增数据库持久化或额外 sidecar 计算。
- 验证记录:
  1. `.venv/bin/pytest tests/test_metrics.py tests/test_collector.py tests/test_event_ranker.py tests/test_evidence_selector.py tests/test_engine.py tests/test_ai_service.py` 通过（35 passed）。
  2. `.venv/bin/pytest tests/test_event_builder.py tests/test_event_state_machine.py tests/test_event_enrichment.py tests/test_event_query_service.py tests/test_event_intelligence_repositories.py tests/test_semantic_deduper.py` 通过（30 passed）。

---

## 8. Batch 4 - Briefs and Context

### [x] EIL-401: `event_summarizer` 生成 `event_brief`

- 主要模块: `src/services/event_summarizer.py`
- 主要工作:
  1. 为高价值事件生成结构化 `event_brief`。
  2. 固化 `canonicalTitle`、`stateChange`、`coreFacts`、`whyItMatters`、`marketChannels`、`regions`、`assets`、`confidence`、`novelty`、`corroboration`、`evidenceRefs`、`contradictions` 等字段。
  3. 将摘要结果写入 `event_briefs`。
- 依赖: EIL-303
- 产出物:
  1. event summarizer。
  2. brief schema 测试。
- 验收标准:
  1. 每个高价值事件可生成格式稳定的事件卡。
  2. 事件卡能独立支撑后续 AI 输入。
- 当前实现说明:
  1. `src/services/event_summarizer.py` 已新增 `EventSummarizer`，提供 `summarize_event()` 与 `summarize_ranked_events()` 两个 service 入口，分别用于单事件和批量 ranked 事件卡生成。
  2. 当前实现采用规则/模板版 `event_brief`，不接入 LLM；生成字段固定为 `eventId / canonicalTitle / stateChange / coreFacts / whyItMatters / marketChannels / regions / assets / confidence / novelty / corroboration / evidenceRefs / contradictions`，并补充 `profile / eventType / status / totalScore / lastTransition / generatedAt` 供后续层复用。
  3. 事件卡会复用 `event_query_service` 时间线、`evidence_selector` 证据包和 `event_ranker` 的 explainability 输出，将 supporting / contradicting evidence 压成摘要友好的 `coreFacts`、`whyItMatters` 和 `contradictions`。
  4. 生成结果通过 `BriefRepository.upsert_event_brief()` 持久化到 `event_briefs`，并输出 `brief` 阶段结构化日志，保存最近一次 `last_brief_metrics` 供测试和调试使用。
- 验证记录:
  1. `.venv/bin/pytest tests/test_event_summarizer.py` 通过（3 passed）。
  2. `.venv/bin/pytest tests/test_event_summarizer.py tests/test_evidence_selector.py tests/test_event_ranker.py tests/test_event_query_service.py tests/test_event_intelligence_repositories.py` 通过（24 passed）。

### [x] EIL-402: `theme_summarizer` 生成 `theme_brief`

- 主要模块: `src/services/theme_summarizer.py`
- 主要工作:
  1. 按主题、区域、资产通道聚合事件卡。
  2. 形成第二层输入压缩，避免 AI 再次阅读大量 event briefs。
  3. 将结果写入 `theme_briefs`。
- 依赖: EIL-401
- 产出物:
  1. theme summarizer。
  2. 主题聚合测试。
- 验收标准:
  1. 主题卡能代表多个相关事件的共同脉络。
  2. 主题覆盖不依赖文章级拼接。
- 当前实现说明:
  1. `src/services/theme_summarizer.py` 已新增 `ThemeSummarizer`，提供 `summarize_theme()` 与 `summarize_ranked_themes()` 两个 service 入口，统一消费 ranked `event_brief` 而不是文章集合。
  2. 当前实现采用固定 taxonomy：`geopolitics / central_banks / macro_data / energy / cyber / commodities / rates_fx`，并对高频主区域额外生成 `region:<name>` 补充桶，避免把 `EIL-403` 的自由主题或预算逻辑提前做进来。
  3. `theme_brief` 会聚合 `summary / coreThreads / whyItMatters / eventRefs / topEvents / stateMix / regions / marketChannels / assets / themeScore` 等稳定字段，并通过 `BriefRepository.upsert_theme_brief()` 持久化到 `theme_briefs`。
  4. 服务会输出 `theme_brief` 阶段结构化日志，保存最近一次 `last_theme_metrics`，用于验证主题覆盖、区域桶比例和多事件聚合比率。
- 验证记录:
  1. `.venv/bin/pytest tests/test_theme_summarizer.py` 通过（3 passed）。
  2. `.venv/bin/pytest tests/test_event_summarizer.py tests/test_event_intelligence_repositories.py` 通过（13 passed）。

### [x] EIL-403: `report_context_builder` 上下文构建器

- 主要模块: `src/services/report_context_builder.py`
- 主要工作:
  1. 在 token 预算内组合 top event briefs、theme briefs 与 market context。
  2. 实现多样性配额，避免单一地区或单一主题霸占上下文。
  3. 固化截断顺序与优先级策略。
- 依赖: EIL-401、EIL-402、EIL-404、EIL-601
- 产出物:
  1. context builder。
  2. 上下文预算测试。
- 验收标准:
  1. 新上下文不再直接消费文章列表。
  2. token 使用量相对现状明显下降。
- 当前实现说明:
  1. `src/services/report_context_builder.py` 已新增 `ReportContextBuilder`，提供 `build_context()`、`build_prompt_sections()` 和 `build_context_from_services()` 三个入口，统一消费 `event_brief`、`theme_brief` 和外部注入的 `market_context`。
  2. 当前实现采用最小规则版预算逻辑：先为 market context 预留固定份额，再以事件优先、主题补充的顺序选入上下文；在超预算时先舍弃低价值主题卡，再把事件卡从完整模式降为轻量模式，最后才删除事件卡。
  3. builder 会对同一主主题和同一区域施加事件位上限，避免单一冲突或单一区域霸占上下文；同时保留 `context_package`、`prompt_sections`、`budget_summary`、`coverage_summary` 和 `truncation_summary` 供后续 `EIL-404/501` 直接复用。
  4. 服务会输出 `context` 阶段结构化日志，保存最近一次 `last_context_metrics`，用于验证预算利用率、压缩比例和 hard-cap 命中情况。
- 验证记录:
  1. `.venv/bin/pytest tests/test_report_context_builder.py` 通过（4 passed）。
  2. `.venv/bin/pytest tests/test_report_context_builder.py tests/test_event_summarizer.py tests/test_theme_summarizer.py tests/test_event_intelligence_repositories.py` 通过（20 passed）。

### [x] EIL-404: 市场上下文适配与预算配额策略

- 主要模块: `src/utils/market_data.py`、`src/services/context_quota_policy.py`
- 主要工作:
  1. 定义 market context 输入结构，明确价格快照、波动、跨资产联动字段。
  2. 设计 event / theme / market 三类输入的预算占比。
  3. 让 context builder 具备稳定的预算裁剪规则。
- 依赖: EIL-401、EIL-601
- 产出物:
  1. 市场上下文契约。
  2. quota policy 模块。
- 验收标准:
  1. 市场数据注入方式稳定且可测试。
  2. 不同报告 profile 可切换不同配额策略。
- 当前实现说明:
  1. `src/services/context_quota_policy.py` 已新增 `ContextQuotaPolicy` 与 `get_context_quota_policy()`，将 `macro_daily / risk_daily / strategy_am` 三套 event/theme/market 预算占比、事件位上限和 region theme 上限收敛为独立 policy。
  2. `src/utils/market_data.py` 已扩展 `build_market_context_snapshot()` 与 `render_market_context_snapshot()`，把价格快照标准化为 `as_of / prices / winners / losers / cross_asset_signals / summary` 的稳定结构，同时保留原有 `get_market_price()` / `search_market_symbol()` 抓数能力不变。
  3. `src/services/report_context_builder.py` 已改为按 profile 读取 quota policy，`budget_summary` 中会暴露 `policy_name` 与 `quota` 明细；同时 builder 支持直接消费结构化 market snapshot，并用 `max_region_themes` 与 `prefer_taxonomy_themes` 稳定约束主题卡选择顺序。
  4. 现有 builder 仍兼容自由文本 `market_context` 输入，因此这一步没有强制改 `AIService.build_market_price_context()` 的返回签名。
- 验证记录:
  1. `.venv/bin/pytest tests/test_context_quota_policy.py tests/test_market_data_context.py tests/test_report_context_builder.py` 通过（10 passed）。
  2. `.venv/bin/pytest tests/test_ai_service.py tests/test_scorer.py tests/test_theme_summarizer.py tests/test_event_summarizer.py tests/test_report_context_builder.py` 通过（21 passed）。

---

## 9. Batch 5 - Report Stack

### [x] EIL-501: 多智能体输入/输出契约与 Prompt v2

- 主要模块: `src/services/prompts.py`、`src/services/report_models.py`
- 主要工作:
  1. 重写 Macro Analyst、Sentiment Analyst、Market Strategist 的输入模板。
  2. 让三类 agent 只消费事件卡、主题卡和市场上下文。
  3. 固化结构化输出 schema，减少后续 orchestrator 清洗成本。
- 依赖: EIL-403、EIL-404
- 产出物:
  1. Prompt v2。
  2. report model schema。
- 验收标准:
  1. 三类 agent 输入不再依赖原始新闻列表。
  2. 输出格式稳定可被 orchestrator 消费。
- 当前实现说明:
  1. `src/services/report_models.py` 已新增并承接 `DailyReport`、`GlobalEvent`、`InvestmentTrend`、`IntelligenceItem`、`IntelSource`、`AgentInsights`，同时补充 `MacroAnalystOutput` 与 `SentimentAnalystOutput` 两个 v2 agent 输出模型。
  2. `src/services/prompts.py` 已新增 `MACRO_ANALYST_PROMPT_V2`、`SENTIMENT_ANALYST_PROMPT_V2`、`MARKET_STRATEGIST_PROMPT_V2`，明确要求模型只消费 `event briefs / theme briefs / market context`，并新增 `build_macro_analyst_input()`、`build_sentiment_analyst_input()`、`build_market_strategist_input()` 三个输入拼装 helper。
  3. `src/services/ai_service.py` 已改为从 `report_models.py` 导入报告模型，但继续在模块顶层暴露这些符号，因此现有 `from src.services.ai_service import DailyReport` 等调用保持兼容。
  4. 本票只完成 Prompt v2 与 schema 契约，不切换 `generate_daily_report()` 主流程；真正把 event-centric context 接进报告生成链路，留到 `EIL-502`。
- 验证记录:
  1. `.venv/bin/pytest tests/test_report_models.py tests/test_prompts.py tests/test_ai_service.py tests/test_notifier.py` 通过（14 passed）。
  2. `.venv/bin/pytest tests/test_report_models.py tests/test_prompts.py tests/test_ai_service.py tests/test_notifier.py tests/test_report_context_builder.py` 通过（19 passed）。

### [x] EIL-502: `ai_service` 拆分为 report orchestrator

- 主要模块: `src/services/ai_service.py`、`src/services/report_orchestrator.py`
- 主要工作:
  1. 把当前 `ai_service.py` 中的文章清洗、上下文拼接、agent 调用、结果整合职责拆开。
  2. 保留与 LLM provider 的必要适配层，但让 orchestrator 只处理 report flow。
  3. 将 event-centric context 接入新的 orchestrator 主路径。
- 依赖: EIL-501
- 产出物:
  1. report orchestrator。
  2. `ai_service.py` 精简方案。
  3. 报告生成集成测试。
- 验收标准:
  1. 报告生成主路径可独立于旧 `build_news_context()` 运行。
  2. `ai_service.py` 不再承担文章级上下文清洗职责。
- 当前实现说明:
  1. 已新增 `src/services/report_orchestrator.py`，提供 `ReportOrchestrator.generate_event_centric_report()`，直接消费 `report_context_builder` 产出的 `context_package`，并以 Prompt v2 驱动 `MacroAnalyst -> SentimentAnalyst -> MarketStrategist` 的 event-centric 报告生成主路径。
  2. orchestrator 复用 `AIService` 的 provider 适配和底层 utility，包括 shared context window 计算、输入预算估算、市场价格上下文获取、agent 调用、最终 JSON 解析与预测持久化；但把上下文拼装、agent 调度、strategist 输入 guard 和 report 指标回写从 `ai_service.py` 中剥离出来。
  3. strategist 输入现在只拼接 `event briefs / theme briefs / market context` 与两个 analyst 的 JSON 输出，不再读取原始文章列表；当未显式传入 briefs 时，orchestrator 会走 `report_context_builder.build_context_from_services()` 现算 event-centric context。
  4. 本票按兼容迁移方式落地，保留 `AIService.generate_daily_report()` 旧入口，尚未删除旧的文章级报告路径；真正重接 `engine / run_report / 调度入口` 留给 `EIL-504`。
- 验证记录:
  1. `.venv/bin/pytest tests/test_report_orchestrator.py` 通过（3 passed）。
  2. `.venv/bin/pytest tests/test_report_orchestrator.py tests/test_ai_service.py tests/test_report_context_builder.py tests/test_prompts.py tests/test_report_models.py` 通过（21 passed）。

### [x] EIL-503: `report_runs` 与事件追溯落库

- 主要模块: `src/services/report_repository.py`
- 主要工作:
  1. 在每次报告生成后写入 `report_runs`。
  2. 建立报告与事件的映射 `report_event_links`。
  3. 保存预算使用、top events、profile、摘要版本等元信息。
  4. 记录事件进入报告时的状态变化类型，支持 `new / updated / escalating / resolved` 的增量回放。
- 依赖: EIL-502
- 产出物:
  1. 报告落库逻辑。
  2. 报告追溯查询接口。
- 验收标准:
  1. 任一报告都能回溯到其事件输入集合。
  2. 报告元信息可用于后续评估和反馈。
  3. 报告可区分本次新增事件与延续事件更新。
- 当前实现说明:
  1. 已新增 `src/services/report_run_tracker.py`，提供 `record_completed_run()`、`get_report_trace()` 和 `get_latest_report_trace()`，把 event-centric `context_package + DailyReport + metrics` 写入 `report_runs` 与 `report_event_links`，并返回可直接消费的追溯视图。
  2. 在不改 schema 的前提下，`report_runs.metadata` 已固定写入 `report_summary / context / budget / source_versions / coverage / report_metrics` 等结构化信息；`report_event_links.rationale` 则使用稳定 JSON 字符串承载 `state_change / render_mode / why_it_matters / brief refs / evidence refs / contradiction_count` 等事件入选理由。
  3. `src/services/report_repository.py` 已补充 `list_report_runs()`，支持按 `profile / status / limit` 过滤最近报告；同 `report_date + profile` 已存在时，tracker 会走 update + replace links，兼容当前唯一约束，不额外修改表结构。
  4. `src/services/report_orchestrator.py` 已支持可选注入 `report_run_tracker`，并在成功生成报告后自动保存 `last_report_trace`；同时 `src/services/report_context_builder.py` 补充了 `input_summary` 与 brief 标识透传，保证 report trace 能回放到具体 event brief / theme brief 版本。
- 验证记录:
  1. `.venv/bin/pytest tests/test_report_run_tracker.py tests/test_report_orchestrator.py tests/test_event_intelligence_repositories.py` 通过（17 passed）。
  2. `.venv/bin/pytest tests/test_report_run_tracker.py tests/test_report_orchestrator.py tests/test_report_context_builder.py tests/test_ai_service.py tests/test_prompts.py tests/test_report_models.py` 通过（25 passed）。

### [ ] EIL-504: `engine` / `run_report` / 调度入口重接

- 主要模块: `src/engine.py`、`src/run_report.py`、`src/main.py`
- 主要工作:
  1. 让主引擎按 `article -> event -> brief -> report` 顺序运行。
  2. 更新 CLI 入口与定时任务入口。
  3. 保证手动跑全流程与定时跑全流程使用同一条新链路。
  4. 让日报默认围绕自上次报告后发生状态变化的事件运行，而不是再次扫描“未报告文章”。
- 依赖: EIL-502、EIL-503
- 产出物:
  1. 新主引擎入口。
  2. 手动运行与定时调度测试。
- 验收标准:
  1. 新链路可端到端生成结构化日报。
  2. CLI 与调度入口不再调用旧文章级报告路径。
  3. 无增量变化的长期事件不会在日报中被重复展开。

---

## 10. Batch 6 - Evaluation, Feedback, Cleanup

### [ ] EIL-602: 回归评估套件

- 主要模块: `tests/evaluation/`、`src/services/evaluation_runner.py`
- 主要工作:
  1. 将 duplicate、same-event、top-N relevance、final report review 四类评估收敛为统一 runner。
  2. 输出固定格式的评估结果，供每次大改后复算。
  3. 将成功标准映射为可执行断言或至少可比较报表。
- 依赖: EIL-000、EIL-204、EIL-301、EIL-503
- 产出物:
  1. evaluation runner。
  2. 评估结果样例。
- 验收标准:
  1. 可以一键复算核心质量指标。
  2. 评估输出足以判断是否达到 `5:1` 压缩比、`80%+` Top30 精度等目标。
  3. 评估结果可同时复算 token 消耗、重复事件泄漏率和关键事件遗漏率。

### [ ] EIL-603: 人工反馈与标注闭环

- 主要模块: `src/services/feedback_service.py`
- 主要工作:
  1. 设计 `evaluation_labels` 的写入路径。
  2. 支持记录误合并、漏报、证据不足、摘要失真等人工反馈。
  3. 让反馈能够反向驱动 ranking、brief 与 merge 规则调优。
- 依赖: EIL-503
- 产出物:
  1. feedback service。
  2. 人工标注数据结构。
- 验收标准:
  1. 人工 review 结果可结构化入库。
  2. 反馈字段能够映射到后续调优动作。

### [ ] EIL-604: 旧模块删除与最终清理

- 主要模块: `src/services/db_service.py`、`src/services/clustering.py`、`src/services/classifier.py`、`src/services/ai_service.py`
- 主要工作:
  1. 删除或降级不再服务于新主链路的旧实现。
  2. 清理对 `raw_news`、旧文章级上下文构建、标题级聚类主路径的直接依赖。
  3. 更新 README 和运维文档，使其反映新系统运行方式。
- 依赖: EIL-504、EIL-602
- 产出物:
  1. 删除清单。
  2. 文档更新。
  3. 最终回归验证记录。
- 验收标准:
  1. 旧文章级主链路已不再是正式实现的一部分。
  2. 项目文档与运行入口全部指向新架构。

---

## 11. 第一轮推荐执行序列

如需立刻启动实施，建议按以下顺序落第一轮 backlog:

1. `EIL-000` -> `EIL-004`，先把评估与地基打平。
2. `EIL-101` -> `EIL-105`，先把文章入口改成标准化对象。
3. `EIL-201` -> `EIL-204`，先让事件对象稳定出现。
4. `EIL-301` -> `EIL-303` + `EIL-601`，先让事件能被正确排序与观察。
5. `EIL-401` -> `EIL-404`，先让 AI 改读事件卡。
6. `EIL-501` -> `EIL-504`，再接管报告生成主路径。
7. `EIL-602` -> `EIL-604`，最后做评估闭环和旧模块退场。

---

## 12. 不应提前做的事

以下工作不应在核心 backlog 之前启动:

1. 先重写 prompt、但仍让模型读文章列表。
2. 先追求复杂知识图谱或跨主题自治 agent。
3. 先做大规模 UI / dashboard，而核心事件链路尚未稳定。
4. 先做历史数据搬运，而新 schema 与主链路尚未闭环。

---

## 13. 结论

这份 backlog 的目标不是把设计文档再说一遍，而是把它压缩成可以真正开工的 ticket 序列。

执行时应始终抓住一个原则:

先把 DeepCurrents 变成“会构建、排序、压缩事件”的系统，再让 AI 去解释这些事件。
