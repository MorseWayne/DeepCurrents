# Event Intelligence Layer 研发路线图

**版本**: v2.0  
**状态**: 待实施  
**依据文档**: `docs/superpowers/specs/2026-03-13-event-intelligence-layer-design.md`  
**实施 Backlog**: `docs/EVENT_INTELLIGENCE_LAYER_IMPLEMENTATION_BACKLOG.md`  
**代码基线**: `src/` Python 主链路  
**基线日期**: 2026-03-13

---

## 0. 前提

本文档采用 clean-slate replacement 前提，直接服务于一次重构到位的事件中心架构，不以沿用现有链路为目标。

明确约束:

1. 不为旧 `raw_news` / 旧报告路径设计过渡层。
2. 不做并行发布、保底切换或备用运行方案。
3. 历史数据直接丢弃，旧数据仅可作为离线分析参考。
4. 不要求新架构复用现有 `db_service.py`、`clustering.py`、`ai_service.py` 的边界。

目标不是“平滑演进”，而是把 DeepCurrents 直接替换为事件中心系统。

---

## 1. 文档目的

本文档把 Event Intelligence Layer 架构设计落成一个可执行的研发顺序，回答四个问题:

1. 应该先搭什么，后搭什么。
2. 每个阶段要交付什么能力。
3. 每个阶段的验收门槛是什么。
4. 何时可以删除旧模块并进入下一阶段。

---

## 2. 总体原则

### 2.1 先换处理单位，再换报告表现

先把“文章处理系统”重构成“事件处理系统”，再重写 prompt 和报告编排。

### 2.2 先打通主链路，再补增强模块

必须优先形成 `article -> event -> brief -> report` 端到端闭环。高级特性不能阻塞主路径落地。

### 2.3 先定最终边界，再做实现拆解

数据库、服务边界、事件状态机、brief 结构必须先以目标形态定义清楚，避免边做边迁就旧实现。

### 2.4 质量验证依赖目标指标，不依赖旧链路共存

验证依据是标注集、人工评审和目标指标，而不是新旧系统并行对比。

---

## 3. 项目分期概览

| Phase   | 目标 | 建议周期 | 风险级别 | 阶段出口 |
| ------- | ---- | -------- | -------- | -------- |
| Phase 0 | 目标边界与评估基线冻结 | 2-4 天 | 低 | 架构、指标、标注集冻结 |
| Phase 1 | 新数据层与基础设施落地 | 1 周 | 中 | 新 schema 与 repository 可用 |
| Phase 2 | 文章标准化与双层去重 | 1-2 周 | 中 | 文章对象与 dedup pipeline 跑通 |
| Phase 3 | 事件构建与事件状态机 | 2 周 | 中高 | 稳定产出事件与状态变化 |
| Phase 4 | 事件增强、评分与证据选择 | 1-2 周 | 中高 | 形成可排序的高价值事件集 |
| Phase 5 | Event Brief / Theme Brief / Context Builder | 2 周 | 中高 | AI 输入彻底切为事件卡 |
| Phase 6 | 多智能体报告 v2 | 1-2 周 | 中高 | 新报告链路端到端可生成日报 |
| Phase 7 | 生产化、调优与旧模块删除 | 持续迭代 | 中 | 新架构成为唯一正式实现 |

如果资源有限，最小完整范围至少应完成到 Phase 6；否则仍未完成从文章系统到事件系统的真正替换。

---

## 4. Phase 0: 目标边界与评估基线冻结

### 4.1 目标

冻结目标架构、关键对象、验收指标和评估样本，避免后续实现阶段反复改边界。

### 4.2 交付物

1. 冻结版架构设计文档。
2. 统一术语表与事件对象定义。
3. 评估指标定义表。
4. 小规模人工标注集。

### 4.3 关键任务

#### P0-1: 冻结对象模型

明确以下对象的字段和职责:

1. `ArticleRecord`
2. `Event`
3. `EventScore`
4. `EventBrief`
5. `ThemeBrief`
6. `ReportRun`

#### P0-2: 冻结评估集

构建 3 份小型标注数据:

1. duplicate pair 样本
2. same-event pair 样本
3. top-N event relevance 样本

#### P0-3: 冻结目标指标

明确最终要优化的指标:

1. 文章到事件压缩比
2. 重复事件泄漏率
3. 关键事件遗漏率
4. Top30 事件精度
5. prompt token 成本

### 4.4 影响模块

1. `docs/superpowers/specs/2026-03-13-event-intelligence-layer-design.md`
2. `docs/EVENT_INTELLIGENCE_LAYER_ROADMAP.md`
3. `tests/fixtures/` 或等价评估样本目录

### 4.5 验收标准

1. 新架构边界不再反复变化。
2. 标注集和指标足以支撑后续每个阶段验收。

---

## 5. Phase 1: 新数据层与基础设施落地

### 5.1 目标

直接建立新事件中心系统所需的数据模型、repository 层和基础设施，不再围绕旧 SQLite 结构扩表。

### 5.2 交付物

1. 新 schema 第一版。
2. article / event / report repository。
3. PostgreSQL + Qdrant + Redis 的基础接入层。
4. 新系统初始化入口。

### 5.3 关键任务

#### P1-1: 建立新 schema

首批核心表:

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

#### P1-2: 拆出 repository 边界

明确并实现:

1. `article_repository`
2. `event_repository`
3. `brief_repository`
4. `report_repository`

#### P1-3: 建立新系统启动骨架

至少具备:

1. 数据库初始化
2. 向量索引初始化
3. 缓存/任务依赖初始化
4. 新引擎主入口骨架

### 5.4 影响模块

1. `src/services/` 下新的 repository 与 infra 模块
2. `src/engine.py` 或新的 orchestrator 入口
3. `tests/` 中数据层测试

### 5.5 验收标准

1. 新 schema 可独立初始化。
2. repository 层可完成核心增删查改。
3. 新系统不再依赖旧 `db_service.py` 的表结构。

---

## 6. Phase 2: 文章标准化与双层去重

### 6.1 目标

把抓取结果转为标准化文章对象，并建立可支撑事件归并的双层去重能力。

### 6.2 交付物

1. `article_normalizer`
2. `semantic_deduper`
3. 文章特征提取流程
4. dedup relation 存储

### 6.3 关键任务

#### P2-1: 文章标准化

实现:

1. URL canonicalization
2. 标题/正文清洗
3. 语言识别
4. 发布时间标准化
5. exact hash / simhash 生成

#### P2-2: 语义特征生成

为文章生成:

1. embedding
2. entities
3. keywords
4. quality score

#### P2-3: 双层去重

建立:

1. ingestion gate 的 cheap dedup
2. semantic dedup 的近邻检索
3. `article_dedup_links` 写入
4. dedup reason / confidence 日志

### 6.4 影响模块

1. `src/services/article_normalizer.py`
2. `src/services/semantic_deduper.py`
3. `src/services/collector.py`
4. repository 层

### 6.5 验收标准

1. exact / near / semantic 三类关系均可落库和查询。
2. 标注集上的 duplicate / same-event 命中率达到可接受区间。
3. 下游事件构建模块可直接消费标准化文章对象。

---

## 7. Phase 3: 事件构建与事件状态机

### 7.1 目标

建立稳定的事件对象，使系统主处理单位正式从文章切换为事件。

### 7.2 交付物

1. `event_builder`
2. 在线事件归并逻辑
3. 事件状态机
4. 事件检索与回放接口

### 7.3 关键任务

#### P3-1: 事件候选检索

新文章写入后:

1. 检索最近时间窗内相似事件
2. 拉取候选事件的代表 embedding 与结构化摘要

#### P3-2: 事件合并判定

采用多信号判定:

1. embedding 相似
2. 实体重叠
3. 区域重叠
4. 时间接近
5. 冲突规则检查

#### P3-3: 事件状态机

至少支持:

1. `new`
2. `active`
3. `updated`
4. `escalating`
5. `stabilizing`
6. `resolved`
7. `dormant`

### 7.4 影响模块

1. `src/services/event_builder.py`
2. `src/services/event_enrichment.py`
3. `src/services/event_repository.py`

### 7.5 验收标准

1. 同一事件跨周期能保持稳定 `event_id`。
2. 文章到事件压缩比达到目标区间。
3. 事件状态变化可回放、可追溯。

---

## 8. Phase 4: 事件增强、评分与证据选择

### 8.1 目标

让系统先完成事件级价值排序和证据压缩，再把结果交给摘要与报告层。

### 8.2 交付物

1. `event_enrichment`
2. `event_ranker`
3. `evidence_selector`
4. 多模板评分配置

### 8.3 关键任务

#### P4-1: 事件增强

从事件成员中提取并聚合:

1. regions
2. entities
3. assets
4. market channels
5. supporting / contradicting sources

#### P4-2: 多维评分模型

实现:

1. `threat_score`
2. `market_impact_score`
3. `novelty_score`
4. `corroboration_score`
5. `source_quality_score`
6. `velocity_score`
7. `uncertainty_score`

#### P4-3: 证据选择

确保每个高价值事件只保留少量高信息密度证据，并保留冲突叙事。

### 8.4 影响模块

1. `src/services/event_enrichment.py`
2. `src/services/event_ranker.py`
3. `src/services/evidence_selector.py`

### 8.5 验收标准

1. Top30 事件人工评审精度明显提升。
2. 高频低价值事件不再挤占前列。
3. 每个入选事件都能给出清晰证据包。

---

## 9. Phase 5: Event Brief / Theme Brief / Context Builder

### 9.1 目标

把数千篇文章压缩为少量高密度事件卡和主题卡，彻底替代文章级 prompt 组装。

### 9.2 交付物

1. `event_summarizer`
2. `theme_summarizer`
3. `report_context_builder`
4. token 预算与多样性配额逻辑

### 9.3 关键任务

#### P5-1: Event Brief 生成

为每个高价值事件生成结构化摘要卡。

#### P5-2: Theme Brief 生成

按主题、区域、资产通道聚合事件卡，形成二级压缩。

#### P5-3: 上下文构建器重写

新的上下文构建器只消费:

1. top event briefs
2. theme briefs
3. market context

不再直接消费文章列表。

### 9.4 影响模块

1. `src/services/event_summarizer.py`
2. `src/services/theme_summarizer.py`
3. `src/services/report_context_builder.py`
4. `src/services/ai_service.py` 或其替代模块

### 9.5 验收标准

1. prompt token 使用量显著下降。
2. 主题覆盖率达到目标要求。
3. 同一事件重复展开现象明显减少。

---

## 10. Phase 6: 多智能体报告 v2

### 10.1 目标

让 AI 从“整理新闻”转为“解释事件和主题”，完成日报链路的正式替换。

### 10.2 交付物

1. 新版 analyst prompts
2. 新版 strategist integration
3. 增量报告逻辑
4. 报告与事件追溯关系

### 10.3 关键任务

#### P6-1: Macro / Sentiment 输入重构

输入统一改为:

1. event briefs
2. theme briefs
3. market context

#### P6-2: Strategist 输入重构

Strategist 只整合分析输出、关键事件卡与市场数据，不再读取大批原始新闻。

#### P6-3: 增量报告机制

日报重点输出:

1. 新出现的事件
2. 已有事件的升级
3. 已有事件的反转或澄清

### 10.4 影响模块

1. `src/services/prompts.py`
2. `src/services/ai_service.py` 或新的 report orchestrator
3. `src/engine.py`

### 10.5 验收标准

1. 新链路可稳定生成结构化日报。
2. 报告事件密度明显提升。
3. 报告结论可回溯到事件与证据。

---

## 11. Phase 7: 生产化、调优与旧模块删除

### 11.1 目标

把事件层从“可运行”推到“可持续优化”，并删除不再服务于目标架构的旧实现。

### 11.2 交付物

1. 人工反馈闭环
2. 周期性评估任务
3. 阈值与模板调优机制
4. 运维监控面板
5. 旧模块删除清单与完成记录

### 11.3 关键任务

1. 建立人工 review 标注流程。
2. 将 report quality 纳入周期性评估。
3. 建立 duplicate leakage 和 miss rate 周报。
4. 尝试更强模型或 reranker，但不破坏事件层抽象。
5. 删除旧文章级报告构建与标题级聚类主路径。

### 11.4 验收标准

1. 连续多周质量稳定。
2. 更换模型或阈值不会导致架构层返工。
3. 旧链路模块已从正式实现中移除。

---

## 12. 模块实施顺序建议

按依赖关系，建议模块建设顺序如下:

1. repository / infra foundation
2. `article_normalizer`
3. `article_features` / embedding writer
4. `semantic_deduper`
5. `event_builder`
6. `event_enrichment`
7. `event_ranker`
8. `evidence_selector`
9. `event_summarizer`
10. `theme_summarizer`
11. `report_context_builder`
12. report orchestrator / `prompts` 重构

不建议先重写 prompts，因为那仍会在错误的数据单位上堆复杂度。

---

## 13. 阶段验收关口

每个阶段结束时，都要回答以下问题:

1. 本阶段是否让系统更接近事件中心主链路。
2. 本阶段产物是否已可被下一阶段直接消费。
3. 关键指标是否达到当前阶段门槛。
4. 是否引入了不必要的旧实现耦合。
5. 是否已经具备删除一批旧模块的条件。

任一阶段若无法回答这些问题，就不应继续推进下一阶段。

---

## 14. 风险管理

### 风险 1: 系统复杂度快速上升

应对:

1. 每个 Phase 只引入服务于主链路的必要模块。
2. 所有新模块都通过清晰接口暴露能力。

### 风险 2: 事件归并质量不足

应对:

1. 合并条件采用多特征而不是单一 embedding 相似度。
2. 建立评估集和误合并回放工具。
3. 优先把错误暴露在离线验收而不是报告阶段。

### 风险 3: 向量与 reranker 成本过高

应对:

1. embedding 与 ANN 检索优先用于候选缩小。
2. rerank 仅用于高价值候选，不全量使用。
3. 事件摘要采用分级模型策略。

### 风险 4: 范围膨胀导致主路径迟迟不闭环

应对:

1. 严格以 `article -> event -> brief -> report` 为主路径。
2. 主题发现、知识图谱、复杂自治 agent 等能力后置。
3. 每阶段只接受能直接提升主链路的新增需求。

---

## 15. 最终里程碑定义

### Milestone A: Event Foundation

完成 Phase 0-3。

成功标志:

1. 新系统已能稳定构建事件。
2. 同一事件具备稳定 ID 和状态演进。

### Milestone B: Event Prioritization

完成 Phase 4-5。

成功标志:

1. 事件能按价值排序。
2. AI 输入已从文章列表切换为事件卡和主题卡。

### Milestone C: Report V2 Replacement

完成 Phase 6-7。

成功标志:

1. 日报主要基于事件变化生成。
2. 报告可追溯、低重复、低 token、高覆盖。
3. 旧文章级主链路已被删除。

---

## 16. 结论

这条路线图的核心不是“优化现有聚类器”，而是把 DeepCurrents 直接替换为事件智能系统。

如果严格按本路线推进，系统的核心收益将按顺序体现为:

1. 从文章级噪声中脱身。
2. 建立可追溯、可排序、可增量更新的事件对象。
3. 用更少的 token 让模型看到更高价值的信息。
4. 为研究、回测和更高级策略引擎提供长期基础设施。
