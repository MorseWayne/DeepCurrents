# Event Intelligence Layer 架构设计

- 日期: 2026-03-13
- 状态: 已批准进入规划与实施
- 适用范围: `src/` Python 主链路
- 关联文档: `docs/EVENT_INTELLIGENCE_LAYER_ROADMAP.md`、`docs/EVENT_INTELLIGENCE_LAYER_IMPLEMENTATION_BACKLOG.md`

## 0. 设计前提

本设计采用破坏性重构前提，不考虑以下事项:

1. 不沿用现有 `raw_news` / `predictions` 的存储结构。
2. 不为旧链路保留并行发布或保底切换设计。
3. 不搬运历史数据，旧数据视为可丢弃或仅用于离线参考。
4. 不为了旧模块边界而约束新架构。

目标是直接把 DeepCurrents 重构为事件中心系统，而不是在旧链路上做增量修补。

## 1. 背景

DeepCurrents 当前主链路是:

`collector -> raw_news -> classify/clustering -> ai_service -> notifier/scorer`

该链路适合处理中等规模、明显重复的新闻流，但在面对数千条新闻时存在结构性上限:

1. 处理单位仍是文章，而不是事件。
2. 候选选择发生在事件归并之前，导致上下文预算被文章级重复消耗。
3. 重要性排序主要依赖源级别、时间和规则 threat，无法稳定衡量市场价值和信息增量。
4. 去重与聚类主要基于标题相似度，难以处理跨语言、多来源、不同措辞的同一事件。
5. 多智能体阶段承担了过多原始信息压缩工作，导致 token 成本高、覆盖率不稳定、输出质量波动。

本设计的目标不是继续优化文章级截断，而是为 DeepCurrents 建立一个独立的 Event Intelligence Layer，使系统先形成高质量事件对象，再让 AI 做宏观解释与策略综合。

## 2. 当前链路问题归纳

### 2.1 处理单位错位

当前报告阶段从 `src/services/db_service.py` 的 `get_unreported_news()` 拉取原始新闻，再在 `src/engine.py` 中做 threat 分类与聚类，最后由 `src/services/ai_service.py` 直接拼接文章级上下文。

这会导致:

1. 同一事件的多篇文章仍可能共同进入 prompt。
2. 重要事件与高频事件无法有效区分。
3. 文章数量越大，越依赖硬截断而不是高质量压缩。

### 2.2 排序偏差

`raw_news` 的 report 候选选择先于运行时 threat 分类，导致系统在进入 AI 之前并未真正完成重要性判断。

### 2.3 聚类语义能力不足

当前 `src/services/clustering.py` 使用标题 token Jaccard + union-find，优点是便宜、可解释，但不足以承担大规模事件归并主职责。

### 2.4 LLM 负担过重

当前 prompt 同时承担:

1. 去重
2. 合并
3. 压缩
4. 宏观解释
5. 策略输出

这些工作应当拆层处理，否则随着文章规模上升，模型将越来越像一个昂贵且不稳定的清洗器。

## 3. 目标与非目标

### 3.1 目标

1. 将主处理单位从文章切换为事件。
2. 在进入大模型前完成双层去重、事件归并、事件评分、证据选择与事件摘要。
3. 让最终日报基于事件变化而不是文章变化生成。
4. 建立多维事件评分体系，显式区分 threat、market impact、novelty 和 corroboration。
5. 提供可回放、可追溯、可评估的数据层，为后续研究、回测和质量优化服务。

### 3.2 非目标

1. 本阶段不重写采集器网络栈。
2. 本阶段不将系统改造成通用知识图谱平台。
3. 本阶段不追求端到端完全自动学习排序，初期仍允许规则与模型混合。
4. 本阶段不为旧 schema、旧数据和旧服务接口额外妥协。

## 4. 核心设计原则

### 4.1 Event First

日报、主题分析、策略推理都围绕事件对象，而不是文章列表展开。

### 4.2 Incremental by Default

系统优先识别事件的新增、升级、反转和失效，而不是每天重新处理一批未报告文章。

### 4.3 Evidence Traceability

每一条重要结论都必须能追溯到事件卡和底层证据文章。

### 4.4 Hybrid Intelligence

规则方法负责稳定、可解释、低成本的第一层判断；语义方法负责跨措辞、跨来源、跨语言归并；LLM 只负责高价值摘要与解释。

### 4.5 Measurable Quality

所有关键步骤必须可观测、可评估、可回归测试，避免只看主观感受。

## 5. 目标架构概览

```text
RSS / RSSHub / Other feeds
  -> Collector
  -> Article Normalizer
  -> Dedup Pipeline
  -> Event Builder
  -> Event Enrichment
  -> Event Ranker
  -> Evidence Selector
  -> Event Brief Generator
  -> Theme Brief Generator
  -> Report Context Builder
  -> Multi-Agent Report Orchestrator
  -> Notifier / Prediction Persistence / Evaluation
```

其中新增的 Event Intelligence Layer 为:

```text
Article Normalizer
  -> Dedup Pipeline
  -> Event Builder
  -> Event Enrichment
  -> Event Ranker
  -> Evidence Selector
  -> Event Brief Generator
  -> Theme Brief Generator
  -> Report Context Builder
```

## 6. 逻辑分层设计

### 6.1 Layer 0: 采集层

职责:

1. 保留 `src/services/collector.py` 的抓取、熔断、并发控制与正文增强能力。
2. 将采集结果转交给文章标准化层，而不是直接当作分析输入。

约束:

1. 采集层不负责事件级判断。
2. 采集层不负责最终报告排序。

### 6.2 Layer 1: 文章标准化层

新增模块建议:

- `src/services/article_normalizer.py`

职责:

1. 规范 URL、标题、正文、发布时间、来源名称和来源元数据。
2. 做语言识别、正文质量评分、文本清洗、归一化分段。
3. 生成 exact hash、simhash、content fingerprint 等特征。
4. 生成初始实体和关键词特征，供后续语义归并使用。

输出对象 `ArticleRecord` 建议字段:

1. `article_id`
2. `source_id`
3. `canonical_url`
4. `title`
5. `normalized_title`
6. `content`
7. `clean_content`
8. `language`
9. `published_at`
10. `ingested_at`
11. `tier`
12. `source_type`
13. `exact_hash`
14. `simhash`
15. `content_length`
16. `quality_score`

### 6.3 Layer 2: 双层去重层

新增模块建议:

- `src/services/semantic_deduper.py`

#### 第一层: Ingestion Gate

沿用当前便宜且可解释的规则:

1. URL 唯一性
2. 标题标准化后近重复
3. 短时间窗口标题缓存

目标:

1. 降低明显重复转载写入成本
2. 保护下游语义层吞吐

#### 第二层: Semantic Dedup

新增语义去重逻辑，处理以下情况:

1. 不同标题的同一事件报道
2. 不同语言的同一事件报道
3. 转载改写和二次包装文章

判定特征建议组合:

1. 向量相似度
2. 时间窗接近度
3. 实体重叠度
4. 地域重叠度
5. 规则冲突检查

语义去重输出不是直接删除文章，而是为事件归并提供候选关系。

### 6.4 Layer 3: 事件构建层

新增模块建议:

- `src/services/event_builder.py`

职责:

1. 将文章映射到已有事件或创建新事件。
2. 在线维护事件的生命周期和成员集合。
3. 为每个事件维护代表标题、时间边界、状态与证据列表。

核心规则:

1. 新文章进入后先检索相似事件候选。
2. 在时间窗内对候选事件做相似度判定。
3. 若满足合并条件则加入事件，否则新建事件。
4. 若文章为事件带来实质新增信息，则推动事件状态转移。

事件状态建议:

1. `new`
2. `active`
3. `updated`
4. `escalating`
5. `stabilizing`
6. `resolved`
7. `dormant`

### 6.5 Layer 4: 事件增强层

新增模块建议:

- `src/services/event_enrichment.py`

职责:

1. 从事件成员文章中提取稳定实体、区域、主题、资产与市场传导通道。
2. 为事件打上结构化标签，而不是只给文章打标签。
3. 聚合 conflicting evidence 和 corroborating evidence。

建议输出字段:

1. `regions`
2. `entities`
3. `assets`
4. `market_channels`
5. `event_type`
6. `supporting_sources`
7. `contradicting_sources`

### 6.6 Layer 5: 事件评分层

新增模块建议:

- `src/services/event_ranker.py`

设计目标:

当前 `threatLevel` 只能表示风险等级，不能覆盖报告所需的全部价值维度。新的排序必须围绕事件评分工作。

建议拆分评分维度:

1. `threat_score`: 冲突、灾害、攻击、政治升级等风险强度。
2. `market_impact_score`: 对利率、汇率、商品、股指、航运、信用利差等定价的潜在影响。
3. `novelty_score`: 相对于最近报告周期的增量信息量。
4. `corroboration_score`: 独立信源交叉确认强度。
5. `source_quality_score`: Tier 和 source type 的综合质量。
6. `velocity_score`: 事件传播速度、成员增长速度。
7. `uncertainty_score`: 单源、冲突叙事、细节不一致带来的不确定性。

不同报告类型使用不同加权模板:

1. 宏观日报: `market_impact + novelty + corroboration` 为主。
2. 风险日报: `threat + corroboration + velocity` 为主。
3. 策略晨报: `market_impact + cross_asset_relevance + novelty` 为主。

### 6.7 Layer 6: 证据选择层

新增模块建议:

- `src/services/evidence_selector.py`

职责:

1. 每个事件只选择有限数量的代表证据文章或证据句。
2. 优先覆盖不同来源和不同角度，而不是重复同义内容。
3. 为摘要和最终报告提供紧凑、高密度、可追溯的 evidence package。

选择规则建议:

1. 高 Tier 优先。
2. 独立信源优先。
3. 含数字、政策、市场反应的证据优先。
4. 对相同信息做惩罚，提升多样性。
5. 若存在冲突叙事，必须保留正反两类证据。

### 6.8 Layer 7: 事件摘要层

新增模块建议:

- `src/services/event_summarizer.py`

职责:

1. 为每个事件生成结构化 `event_brief`。
2. 让后续 AI 读取事件卡，而不是读取整批文章。

建议的 `event_brief` 结构:

```json
{
  "eventId": "evt_xxx",
  "canonicalTitle": "事件标题",
  "stateChange": "new|updated|escalated|resolved",
  "coreFacts": ["事实 1", "事实 2"],
  "whyItMatters": "为什么重要",
  "marketChannels": ["oil", "rates"],
  "regions": ["Middle East"],
  "assets": ["Brent"],
  "confidence": 0.86,
  "novelty": "high",
  "corroboration": "strong",
  "evidenceRefs": ["article_id_1", "article_id_2"],
  "contradictions": []
}
```

### 6.9 Layer 8: 主题摘要层

新增模块建议:

- `src/services/theme_summarizer.py`

职责:

1. 将高价值事件卡按主题、区域和资产通道聚合成主题摘要。
2. 形成第二层输入压缩，供最终多智能体推理使用。

主题维度建议:

1. geopolitics
2. central banks
3. macro data
4. energy
5. cyber
6. commodities
7. rates/fx
8. region buckets

### 6.10 Layer 9: 报告上下文构建层

新增模块建议:

- `src/services/report_context_builder.py`

职责:

1. 按事件而不是文章构建 AI 输入。
2. 在预算内保留最有价值的 event briefs 和 theme briefs。
3. 保证主题、区域、资产通道的多样性覆盖。

核心原则:

1. 优先保留 `new`、`escalated`、`updated` 事件。
2. 对长期持续但无增量的事件降权。
3. 先截断低价值事件，再截断主题补充，最后才动顶层关键信息。

### 6.11 Layer 10: 多智能体报告层

保留多智能体角色，但改变输入职责:

1. `MacroAnalyst` 读取事件卡和主题卡，做宏观逻辑、政策传导、尾部风险分析。
2. `SentimentAnalyst` 读取事件卡、价格快照与不确定性，做 risk-on/risk-off 与分歧分析。
3. `MarketStrategist` 读取前两者输出、关键事件卡、市场数据，做最终结构化报告。

大模型不再负责海量原始新闻整理，只负责解释、权衡和结论输出。

## 7. 数据模型设计

### 7.1 核心表建议

1. `articles`
2. `article_features`
3. `article_dedup_links`
4. `events`
5. `event_members`
6. `event_scores`
7. `event_state_transitions`
8. `event_briefs`
9. `theme_briefs`
10. `report_runs`
11. `report_event_links`
12. `evaluation_labels`

### 7.2 表职责说明

#### `articles`

存标准化后的文章主体，不承担事件聚合职责。

#### `article_features`

存 embedding、language、simhash、entities、keywords、quality score 等派生特征。

#### `article_dedup_links`

存 exact/near/semantic 关系，支持去重调试与回放。

#### `events`

存事件主记录、时间边界、状态、代表标题和高层标签。

#### `event_members`

存文章与事件的映射关系，以及该文章在事件中的角色，例如 `primary`, `supporting`, `conflicting`。

#### `event_scores`

存多维分数和最终总分，支持不同模板下的重算。

#### `event_state_transitions`

存事件状态机演进，用于增量报告和审计。

#### `event_briefs`

存事件级摘要卡，作为 AI 主输入对象。

#### `theme_briefs`

存主题级摘要卡，作为次级压缩对象。

#### `report_runs`

存每次日报生成元信息、预算使用、主要统计和版本号。

#### `report_event_links`

建立报告和事件之间的追溯关系。

#### `evaluation_labels`

存人工标注、质量反馈和基准评估数据。

## 8. 存储与基础设施设计

### 8.1 目标部署形态

本方案默认以新的目标架构直接替换现有运行形态，推荐基础设施为:

1. 元数据与事务数据: PostgreSQL
2. 向量索引: Qdrant
3. 缓存/任务中转: Redis

原因:

1. 事件层存在多表关系、状态机和高频更新，SQLite 不再是目标架构选项。
2. 语义检索与在线事件归并天然需要独立向量索引服务。
3. 事件摘要、主题摘要和评估任务需要稳定的异步任务与缓存层。

### 8.2 非目标部署形态

1. 不以 SQLite 为长期目标形态。
2. 不以“先适配旧数据库，再慢慢替换”为实施方式。
3. 不以现有 `db_service.py` 的结构约束最终设计。

## 9. 推荐技术栈

### 9.1 强烈建议采用

1. 多语言 embedding: `bge-m3` 或 `multilingual-e5-large`
2. 向量数据库: `Qdrant`
3. 近重复检测: `datasketch` 或 SimHash 实现
4. reranker: `bge-reranker-v2-m3` 或 `jina-reranker`
5. 抽取式压缩: `PyTextRank` 或 `LexRank`

### 9.2 可选增强

1. `BERTopic` 用于离线主题趋势发现，不作为在线主链路。
2. `LLMLingua` 仅用于进一步压缩事件卡或主题卡，不替代事件层设计。
3. 多语言 NER 可接入可替换模型，但应通过统一抽象封装。

## 10. 增量报告设计

新的报告单元不是“未报告文章”，而是“自上次报告后有状态变化的事件”。

建议规则:

1. `new`: 首次进入候选集，默认参与报告。
2. `updated`: 有实质新增事实，但结论方向不变。
3. `escalated`: 风险等级、市场通道或影响范围显著上升。
4. `resolved`: 事件被澄清、结束或证伪，可在报告中降权或收尾。
5. `dormant`: 长期无新增信息，不重复展开。

这将显著降低日报中同一事件反复出现但没有新增价值的问题。

## 11. 可观测性与评估设计

### 11.1 必备观测指标

1. 原始文章数
2. exact dedup 丢弃数
3. near dedup 丢弃数
4. semantic merge 命中数
5. 文章到事件压缩比
6. 事件平均独立信源数
7. 单源事件比例
8. 事件卡进入报告比例
9. 预算截断率
10. 重复事件泄漏率
11. 关键事件遗漏率

### 11.2 必备评估集

1. duplicate pair 标注集
2. same-event pair 标注集
3. top-N relevance 标注集
4. final report editorial review 标注集

### 11.3 回归验证目标

1. 每次改动都能在固定标注集上复算 Top30 事件精度。
2. 每次改动都能复算 token 消耗和事件覆盖率。
3. 每次改动都能复算重复率和遗漏率。

## 12. 替换策略

### 12.1 总体策略

采用 clean-slate replacement，而不是渐进式演进。

1. 直接建立新的事件中心数据模型和服务边界。
2. 新的 `engine/report stack` 直接消费事件层，不再读取旧的文章级报告输入。
3. 历史数据不搬运；新系统从新 schema 和新存储开始积累。
4. 旧模块只作为短期参考实现，验证完成后直接删除。

### 12.2 替换顺序

1. 先定义新 schema、新 repository 和事件服务边界。
2. 再完成 article normalizer、semantic deduper、event builder。
3. 再完成 event ranker、evidence selector、event brief/theme brief。
4. 再重写新的 report orchestrator 与 prompts。
5. 最后删除旧的文章级报告构建和标题级聚类主路径。

## 13. 风险与缓解

### 风险 1: 新架构过重，迭代周期过长

缓解:

1. 先冻结目标边界，只做事件中心主链路，不引入额外平台化诉求。
2. 以“先打通端到端主路径，再补增强模块”为顺序推进。

### 风险 2: 语义归并错误导致误合并

缓解:

1. 合并条件采用多特征而不是单一 embedding 相似度。
2. 引入置信度和审核日志。
3. 建立冲突事件回放工具。

### 风险 3: 多语言支持不稳定

缓解:

1. 优先使用多语言 embedding 做归并。
2. 不把翻译作为主前提。
3. 对非中英文语言先通过观测确认覆盖情况。

### 风险 4: 成本上升

缓解:

1. 让 LLM 只读取事件卡，减少下游 token 消耗。
2. 事件摘要可采用分级模型策略，小模型优先，大模型用于最终综合。

## 14. 成功标准

1. 文章到事件压缩比达到至少 `5:1`，目标 `10:1+`。
2. Top30 事件人工评审精度达到 `80%+`。
3. 重复事件泄漏率控制在 `5%` 以下。
4. 关键事件遗漏率控制在 `10%` 以下。
5. 最终报告 token 消耗较现状下降约 `70%`。
6. 报告中每条关键结论都可追溯到事件卡和底层证据。

## 15. 结论

本设计的核心不是“让模型读更多”，而是“让系统先形成高质量事件对象，再让模型解释这些事件”。

DeepCurrents 从新闻聚合器升级为事件智能引擎后，收益将体现在四个方面:

1. 更稳定地提取关键事件。
2. 更有效地去除重复和噪声。
3. 更清晰地追踪事件状态变化。
4. 为研究、回测、趋势分析和未来平台化演进提供长期可复用的数据底座。
