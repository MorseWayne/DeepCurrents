# Event Intelligence Report Entry Rewire Design

- 日期: 2026-03-13
- 状态: 已批准进入实施
- 适用范围: `src/engine.py`、`src/run_report.py`、`src/main.py`
- 关联 backlog: `docs/EVENT_INTELLIGENCE_LAYER_IMPLEMENTATION_BACKLOG.md` 中 `EIL-504`
- 关联设计: `docs/superpowers/specs/2026-03-13-event-intelligence-layer-design.md`

## 0. 背景

截至 `EIL-503`，DeepCurrents 已经具备完整的 event-centric report stack:

1. `EventRanker` 负责按 profile 对事件评分。
2. `EvidenceSelector` 负责为事件压缩 supporting / contradicting evidence。
3. `EventSummarizer` 和 `ThemeSummarizer` 负责产出结构化 brief。
4. `ReportContextBuilder` 负责在预算内组装 event/theme/market context。
5. `ReportOrchestrator` 负责调用多智能体并落库 `report_runs` / `report_event_links`。

但当前实际入口仍停留在旧文章级路径:

`raw_news -> clustering -> AIService.generate_daily_report()`

这导致三个问题:

1. CLI 与调度入口还没有切到新链路。
2. 日报仍围绕“未报告文章”而不是“事件增量变化”运行。
3. 即使 event intelligence runtime 已启动，报告阶段也会继续消费旧 `raw_news`。

## 1. 目标

`EIL-504` 只解决报告入口重接，不扩大到评估闭环或旧模块删除。

本票目标:

1. 让 `engine`、`run_report`、`main` 统一走 event-centric 报告主链路。
2. 让日报默认围绕自上次报告后发生增量变化的事件运行。
3. 保持现有 CLI 输出格式、推送逻辑和 `DailyReport` schema 不变。
4. 明确“首跑无历史报告”时的基线策略，避免调度首次上线直接空跑。

本票非目标:

1. 不删除 `AIService.generate_daily_report()`。
2. 不删除 `raw_news` 或旧 clustering 实现。
3. 不实现 `EIL-602` 评估 runner 或 `EIL-603` 人工反馈。

## 2. 方案选择

本次采用最小改动方案: 由 `DeepCurrentsEngine` 在 runtime 启动后本地组装 report stack，而不是扩展 bootstrap contract。

不选其它方案的原因:

1. 若把 report container 下沉到 `EventIntelligenceBootstrap`，需要同时扩大 runtime state contract 和相关测试面，不适合本票。
2. 若新建额外 `report_pipeline` 抽象，会引入新的 orchestration 边界，但当前已有 `ReportOrchestrator`，收益不大。

因此本票以 `engine.py` 作为 composition root，负责在已有 stores 基础上装配:

1. `ArticleRepository`
2. `EventRepository`
3. `EventEnrichmentService`
4. `EventQueryService`
5. `EventRanker`
6. `EvidenceSelector`
7. `EventSummarizer`
8. `ThemeSummarizer`
9. `ReportContextBuilder`
10. `ReportRepository`
11. `ReportRunTracker`
12. `ReportOrchestrator`

## 3. Runtime Wiring

### 3.1 Engine 新职责

`DeepCurrentsEngine.bootstrap_runtime()` 在完成 store bootstrap 后，新增 report stack wiring。

约束:

1. 只有 event intelligence runtime 成功启动且 `postgres.pool` 可用时才装配 report stack。
2. wiring 失败时不回退旧文章级报告路径，只记录错误并保持 report stack 为不可用。
3. 采集链路 wiring 与报告链路 wiring 分开处理，避免报告装配失败影响 ingestion。

### 3.2 运行时状态

`DeepCurrentsEngine` 新增一组私有字段保存 report stack 依赖，至少包括:

1. `report_repository`
2. `report_run_tracker`
3. `report_context_builder`
4. `report_orchestrator`
5. 当前 report profile

这些字段在 `engine.stop()` 时无需显式关闭，仍复用 bootstrap 中已管理的 store 生命周期。

## 4. 增量事件选择策略

### 4.1 默认过滤口径

报告入口不再查询 `DBService.get_unreported_news()`，改为直接调用 `ReportOrchestrator.generate_event_centric_report()`。

默认状态集合固定为:

1. `new`
2. `active`
3. `updated`
4. `escalating`
5. `stabilizing`
6. `resolved`

保留 `resolved` 的原因是日报仍需要覆盖“本次进入解决态”的事件，但长期无变化的已解决事件会被 `since` 窗口自然过滤掉。

### 4.2 上次报告时间窗口

每次生成日报前，入口先查询同 profile 最近一条 `completed report_run`。

若存在上一条 run:

1. `since` 优先取该 run 的 `updated_at`
2. 若缺失则取 `created_at`
3. 若仍缺失则回退为 `report_date` 的 `00:00 UTC`

然后把 `statuses + since + profile` 交给 `ReportOrchestrator`。

### 4.3 首跑基线策略

若指定 profile 不存在历史 `report_run`:

1. 进入首跑基线模式
2. 使用同一组状态过滤
3. `since=None`

该策略的目的不是“重扫所有历史文章”，而是为新入口生成第一份可追踪的基线日报，保证 CLI 和调度首次上线时有稳定输出。

### 4.4 无增量变化

如果 event/theme brief 选择结果为空，则本次视为“无增量变化”:

1. 不生成报告
2. 不推送通知
3. 返回 `None`
4. 输出结构化 report 指标，`reason=no_event_changes`

## 5. 入口行为

### 5.1 `DeepCurrentsEngine.generate_and_send_report()`

新主流程:

1. 解析当前 report profile 和最近一次 run 时间窗口
2. 调用 event-centric orchestrator 生成 `DailyReport`
3. 读取 orchestrator 暴露的 metrics / trace
4. 按现有逻辑执行 notifier 推送
5. 保留 `--no-push` 预览模式语义

删除的旧行为:

1. 不再读取 `raw_news`
2. 不再调用 `classify_threat`
3. 不再调用 `cluster_news`
4. 不再调用 `AIService.generate_daily_report()`
5. 不再调用 `mark_as_reported()` 标记文章

### 5.2 `run_report.py`

CLI 仍保留现有参数:

1. `--report-only`: 仅跳过采集，不改变报告生成链路
2. `--no-push`: 只预览，不推送
3. `--json` / `--output`: 输出行为不变

CLI 入口本身不感知旧/新报告链路，始终复用 `engine.generate_and_send_report()`。

### 5.3 `main.py`

调度入口继续绑定 `engine.generate_and_send_report`。

切换完成后，手动 CLI 和 cron 调度天然共享同一条 event-centric 报告路径，不再存在“手动和自动走不同实现”的分叉。

## 6. 错误处理与降级

### 6.1 runtime 不可用

如果 event intelligence runtime 未启动或 report stack 未成功装配:

1. 记录结构化 `report` 指标
2. 记录明确错误日志
3. 返回 `None`

本票明确不回退到旧文章级报告链路。这样可以避免“表面完成迁移、实际仍在偷偷跑旧实现”的假阳性。

### 6.2 orchestrator 失败

若 `ReportOrchestrator.generate_event_centric_report()` 抛错:

1. 记录失败指标与错误日志
2. 不推送通知
3. 返回 `None`

### 6.3 推送行为

报告生成成功后，通知仍使用现有 `Notifier.deliver_all()`。

为避免改动 notifier 契约，本票继续沿用:

1. `raw_count` 位置传 `0`
2. `cluster_count` 位置传选中的事件数或主题数

如果后续需要让通知正文更贴近 event-centric 统计，再在独立票中调整 notifier 输入契约。

## 7. 测试设计

### 7.1 `tests/test_engine.py`

至少覆盖:

1. runtime 启动后会装配 report stack
2. `generate_and_send_report()` 调用 orchestrator 而不是 `AIService.generate_daily_report()`
3. 首跑无历史 run 时，按首跑基线模式执行
4. 已有历史 run 时，会带 `since` 和 profile 走增量模式
5. 无增量事件时返回 `None`
6. 失败时写出 report 指标

### 7.2 `tests/test_run_report.py`

继续验证:

1. `bootstrap_runtime()` 仍在 CLI 报告链路前执行
2. CLI 仍统一调用 `engine.generate_and_send_report()`

### 7.3 调度入口

如有必要，在 `tests/test_engine.py` 或新增轻量测试中固定:

1. 调度仍绑定 `engine.generate_and_send_report`
2. 不需要任何旧文章级前置步骤即可生成 event-centric 报告

## 8. 验收标准映射

本设计对应 `EIL-504` 的验收映射如下:

1. 新链路可端到端生成结构化日报
   - 由 `engine -> report_orchestrator -> notifier` 完成
2. CLI 与调度入口不再调用旧文章级报告路径
   - 由 `tests/test_engine.py` 与 `tests/test_run_report.py` 固化
3. 无增量变化的长期事件不会在日报中被重复展开
   - 由 `latest report run + since window` 机制保证

## 9. 实施边界

本票完成后，系统会进入以下状态:

1. 采集主路径: `collector -> article -> event`
2. 报告主路径: `event -> brief -> report`
3. 旧 `AIService.generate_daily_report()` 仅作为兼容实现留存，不再由正式入口调用

后续票继续承担:

1. `EIL-602`: 用统一 runner 建立质量回归基线
2. `EIL-603`: 把人工反馈与报告 trace 连起来
3. `EIL-604`: 删除旧文章级正式主链路与相关文档
