# Event Intelligence Legacy Retirement Design

- 日期: 2026-03-13
- 状态: 已批准进入实施
- 适用范围: `src/services/collector.py`、`src/engine.py`、`src/services/ai_service.py`、`src/services/notifier.py`、`README*`
- 关联 backlog: `docs/EVENT_INTELLIGENCE_LAYER_IMPLEMENTATION_BACKLOG.md` 中 `EIL-604`
- 关联设计:
  - `docs/superpowers/specs/2026-03-13-event-intelligence-layer-design.md`
  - `docs/superpowers/specs/2026-03-13-event-intelligence-report-entry-rewire-design.md`

## 0. 背景

截至 `EIL-504`，正式报告入口已经切换到 event-centric 链路：

1. `engine.generate_and_send_report()`
2. `ReportOrchestrator.generate_event_centric_report()`
3. `report_runs / report_event_links`

但仓库中仍残留多处旧文章级实现与文档描述：

1. `collector` 在 event-intelligence 成功后仍会 mirror 到 `raw_news`
2. `collector` 在 runtime wiring 缺失时仍可回退到旧 SQLite 新闻保存路径
3. `db_service.py` 仍同时承担 `raw_news`、预测存储和文本相似度工具
4. `ai_service.py` 仍保留旧文章级 `generate_daily_report()` 与 news/cluster context 组装
5. `classifier.py` / `clustering.py` 仍被生产代码或测试直接引用
6. README / README.en / 技术文档仍把旧链路描述为正式架构

`EIL-604` 的目标不是一次性抹平所有历史代码，而是让旧文章级主链路彻底退出“正式实现”，并让项目文档与运行入口只指向新架构。

## 1. 目标

本票目标：

1. 删除旧文章级正式主链路
2. 清理对 `raw_news`、旧文章级上下文构建和标题级 clustering 的直接依赖
3. 将仍然需要的能力迁移到更窄的边界
4. 更新 README 和相关运维文档，使其反映 event-intelligence 系统

本票非目标：

1. 不重做 event-intelligence runtime 本身
2. 不重构 `ReportOrchestrator`
3. 不重做评分逻辑
4. 不逐段重写所有历史分析文档

## 2. 方案选择

本票采用“兼容壳退场”方案，而不是一次性硬删除所有旧文件。

### 2.1 不采用“硬删除全部旧模块”

原因：

1. `db_service.py` 目前仍承载预测存储
2. `event_builder.py` / `semantic_deduper.py` 仍复用其中的文本相似度工具
3. `notifier.py` 仍引用 `THREAT_LABELS`

如果本票直接硬删所有 legacy 文件，会连带引入：

1. 预测存储重建
2. 文本相似度工具迁移
3. 通知展示常量迁移

因此更稳妥的做法是：

1. 正式主链路立即退场
2. 将仍有价值的能力迁到新边界
3. 迁移完成后再删除已无调用的 legacy 文件

## 3. 主链路退场边界

### 3.1 `collector`

`RSSCollector` 改为只服务 event-intelligence ingestion：

1. 删除 `raw_news` fallback 保存
2. 删除 event-intelligence 成功后的 legacy mirror
3. 当 ingestion wiring 不可用时，返回结构化 `skip/fail-closed` 指标，而不是回退旧 SQLite

这意味着正式采集入口将只认：

1. `article_normalizer`
2. `article_repository`
3. `article_feature_extractor`
4. 可选 `semantic_deduper`
5. 可选 `event_candidate_extractor`
6. 可选 `event_enrichment`

### 3.2 `engine`

`DeepCurrentsEngine` 不再把旧 SQLite 新闻库当成系统主依赖：

1. 采集阶段只认 event-intelligence runtime
2. 报告阶段继续保持当前 `fail-closed`
3. 不再通过任何分支回退到 `raw_news -> clustering -> AIService.generate_daily_report()`

## 4. `db_service` 拆分策略

### 4.1 `raw_news` 相关能力退出正式路径

以下能力不再保留在正式运行路径中：

1. `has_news`
2. `has_similar_title`
3. `save_news`
4. `get_unreported_news`
5. `mark_as_reported`
6. `cleanup` 中针对 `raw_news` 的清理逻辑

### 4.2 预测存储独立成新边界

新增窄边界 repository，例如 `prediction_repository.py`，承接：

1. `save_prediction`
2. `get_pending_predictions`
3. `update_prediction_score`
4. 可选 `cleanup`（若仍保留定时清理任务）

`AIService._persist_predictions()` 与 `PredictionScorer` 改依赖该 repository，而不是 `DBService`。

### 4.3 文本相似度工具迁移

以下通用工具迁出 `db_service.py`，放入独立 util：

1. `generate_trigrams`
2. `jaccard_similarity`
3. `dice_coefficient`

`event_builder.py` 与 `semantic_deduper.py` 改从新 util 引用，不再依赖 `db_service.py`。

### 4.4 `DBService` 的最终状态

若以上能力都已迁出且无生产调用，则直接删除 `db_service.py`。

若仍残留极少兼容调用，则将其降级为仅用于过渡的 compatibility shell，不再出现在 README、项目结构或正式运行说明中。

## 5. `ai_service / classifier / clustering` 退场

### 5.1 `ai_service.py`

保留 event-centric 报告仍在复用的通用能力：

1. provider window / budget 计算
2. `build_market_price_context()`
3. `call_agent()`
4. `parse_daily_report_json()`
5. `_persist_predictions()`

删除或显式降级旧文章级能力：

1. `generate_daily_report()`
2. `build_news_context()`
3. news/cluster raw context 组装相关私有方法

### 5.2 `classifier.py` / `clustering.py`

两者不再作为生产链路模块保留。

`THREAT_LABELS` 迁到更中性的展示常量模块，例如：

1. `threat_labels.py`
2. `report_constants.py`

`notifier.py` 改从新模块取 threat label 映射，避免继续依赖 legacy classifier。

## 6. 文档清理

### 6.1 README / README.en

更新以下内容：

1. 顶部系统描述改为 event-centric 架构
2. 架构图改成：
   - `collector -> article repository/features/dedup -> event builder/ranker -> report orchestrator -> notifier/scorer`
3. 删除对 `Classifier / Clustering / raw_news / SQLite cleanup` 作为正式主链路的描述
4. 项目结构改为 event-intelligence 相关模块
5. 调度表只保留仍然正式存在的任务

### 6.2 技术文档

至少同步：

1. `docs/TECHNICAL_DESIGN.md`

对于 `TECH_OPTIMIZATION_*` 等历史分析文档，不逐段重写，只在必要处补充“基于旧链路，已过时”的说明即可。

## 7. 错误处理

1. `collector` 在 ingestion wiring 缺失时，不回退旧 SQLite，而是返回结构化 skip/fail-closed 指标
2. `generate_and_send_report()` 保持当前 fail-closed，不生成旧文章级报告
3. `scorer` 不改变现有评分语义，只替换底层 repository 边界

## 8. 测试设计

### 8.1 删除或收缩旧测试

删除：

1. `tests/test_pipeline.py`
2. `tests/test_db_service.py`
3. `tests/test_ai_service.py` 中围绕 `generate_daily_report()` 和 article-list context 的旧用例

### 8.2 新增或改造测试

新增：

1. `tests/test_prediction_repository.py`
2. `tests/test_text_similarity.py`

改造：

1. `tests/test_collector.py`
   - 验证无 legacy mirror
   - 验证无 `raw_news` fallback
2. `tests/test_engine.py`
   - 验证 runtime 不可用时不会回退旧采集/报告链路
3. `tests/test_notifier.py`
   - 验证 threat label 常量迁移后展示行为不变
4. `tests/test_scorer.py`
   - 改用新 `PredictionRepository`

## 9. 回归验证

至少执行：

1. `tests/test_collector.py`
2. `tests/test_engine.py`
3. `tests/test_report_orchestrator.py`
4. `tests/test_scorer.py`
5. `tests/test_notifier.py`
6. 新增的 repository / util 测试

同时补一轮 event-intelligence 关键测试，确认 `EIL-602` / `EIL-603` 未受影响。

## 10. 成功标准映射

本设计对应 `EIL-604` 的验收映射如下：

1. 旧文章级主链路已不再是正式实现的一部分
   - 通过删除 `collector` fallback/mirror、删除 `AIService.generate_daily_report()` 正式路径、移除生产代码对 `classifier/clustering` 的依赖完成
2. 项目文档与运行入口全部指向新架构
   - 通过 README / README.en / 技术文档清理完成

## 11. 实施边界

本票完成后，系统状态应变为：

1. 正式采集链路只认 article-first / event-intelligence ingestion
2. 正式报告链路只认 event-centric report orchestrator
3. 预测存储与文本相似度能力拥有更窄边界
4. README 与运维文档不再宣传旧文章级实现

但本票仍不包含：

1. event runtime 新能力扩展
2. 评分算法重写
3. 全量历史文档重构
