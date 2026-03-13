# Event Intelligence Feedback Loop Design

- 日期: 2026-03-13
- 状态: 已批准进入实施
- 适用范围: `src/services/feedback_service.py`、`evaluation_labels`
- 关联 backlog: `docs/EVENT_INTELLIGENCE_LAYER_IMPLEMENTATION_BACKLOG.md` 中 `EIL-603`
- 关联设计: `docs/superpowers/specs/2026-03-13-event-intelligence-layer-design.md`

## 0. 背景

截至 `EIL-503` 与 `EIL-504`，系统已经具备:

1. `report_runs`
2. `report_event_links`
3. `ReportRunTracker.get_report_trace()`

因此每一份报告都已经可以回放到:

1. 报告级 metadata
2. 入选事件列表
3. `state_change`
4. `brief_id / brief_version`
5. `evidence_refs`

与此同时，schema 中已经存在通用表 `evaluation_labels`，但尚无写入路径与查询封装。

`EIL-603` 的目标不是建立完整标注平台，而是把人工 review 结果结构化入库，并稳定映射到后续调优动作。

## 1. 目标

本票目标:

1. 新增 `src/services/feedback_service.py`
2. 为 `evaluation_labels` 建立稳定写入和查询入口
3. 支持 report-centric feedback first 的人工 review 记录
4. 将反馈映射为结构化调优建议，而不是直接自动修改系统行为

本票非目标:

1. 不改 `evaluation_labels` 表结构
2. 不做 UI 或 dashboard
3. 不做自动 rank weight 更新
4. 不在本票接入 `EvaluationRunner`

## 2. 方案选择

第一版采用 `report_run_id` 作为主锚点的 report-centric 反馈模型。

不采用完全泛化多主体模型的原因:

1. 当前最稳定、最可回放的业务主体是 `report_run`
2. `report_run_tracker` 已经提供事件级 trace，可直接复用
3. 若一开始就把 article/event/report 三层写入路径同时做完，会明显扩大本票范围

因此第一版的主 `subject_id` 固定为 `report_run_id`，同时在 `label_value` 中保留 `event_id / brief_id / article_id` 等次级锚点。

## 3. 数据模型

### 3.1 表结构复用

沿用现有 `evaluation_labels`:

1. `label_id`
2. `label_type`
3. `subject_id`
4. `label_value`
5. `source`
6. `notes`

### 3.2 `label_type`

第一版仅支持两类:

1. `report_review`
2. `report_event_review`

### 3.3 `label_value`

第一版建议固定结构:

1. `issue_type`
   - `false_merge`
   - `missed_event`
   - `weak_evidence`
   - `summary_distortion`
   - `ranking_error`
2. `decision`
   - `confirmed`
   - `rejected`
   - `needs_followup`
3. `target`
   - `report_run_id`
   - 可选 `event_id`
   - 可选 `brief_id`
   - 可选 `article_id`
4. `context`
   - 可选 `state_change`
   - 可选 `why_it_matters`
   - 可选 `evidence_refs`
   - 可选 `expected_action`
   - 可选 `out_of_trace_target`
5. `reviewer`
   - `reviewer_id`
   - 可选 `reviewer_role`

## 4. Service 接口

新增 `FeedbackService`，第一版提供以下能力:

1. `record_report_review(...)`
2. `record_report_event_review(...)`
3. `list_feedback(...)`
4. `summarize_feedback_actions(...)`

### 4.1 `record_report_review`

职责:

1. 写入 `label_type=report_review`
2. `subject_id` 固定为 `report_run_id`
3. 用于记录整份报告的整体问题，例如摘要失真、整体遗漏、整体噪音

### 4.2 `record_report_event_review`

职责:

1. 写入 `label_type=report_event_review`
2. `subject_id` 固定为 `report_run_id`
3. 在 `label_value.target` 中补充 `event_id / brief_id / article_id`
4. 用于记录事件级问题，例如误合并、证据不足、排序错误、漏报事件

### 4.3 `list_feedback`

支持按以下条件过滤:

1. `subject_id`
2. `label_type`
3. `issue_type`
4. `source`
5. `limit`

第一版返回统一的标准化 label 列表，不做复杂分页。

### 4.4 `summarize_feedback_actions`

职责:

1. 读取符合过滤条件的 feedback labels
2. 按 `issue_type` 聚合
3. 输出结构化调优建议，而不是直接执行闭环动作

输出建议结构至少包含:

1. `issue_type`
2. `feedback_count`
3. `affected_report_runs`
4. `affected_event_ids`
5. `recommended_actions`

## 5. Trace 对接

`FeedbackService` 可选依赖 `ReportRunTracker`。

写入 `report_event_review` 时:

1. 若给定 `report_run_id + event_id`
2. service 会尝试读取 `get_report_trace(report_run_id)`
3. 若该事件在 trace 中:
   - 自动补充可用的 `brief_id / state_change / evidence_refs`
4. 若该事件不在 trace 中:
   - 仍允许写入
   - 但在 `label_value.context.out_of_trace_target` 中标记为 `true`

这样可以同时支持:

1. 已入选事件的负反馈
2. 应当入选但未入选的漏报反馈

## 6. 调优建议映射

第一版不自动修改任何模型或规则，只输出结构化建议。

映射规则:

1. `false_merge`
   - 建议检查 merge signals、entity overlap、region overlap、冲突规则
2. `missed_event`
   - 建议检查 rank threshold、增量窗口、theme quota、Top-K 选择
3. `weak_evidence`
   - 建议检查 evidence selector 的 source diversity、tier weighting、contradiction retention
4. `summary_distortion`
   - 建议检查 brief schema、prompt v2、context truncation
5. `ranking_error`
   - 建议检查 scoring profile 权重以及 novelty/corroboration/source quality 维度

## 7. 测试设计

新增:

1. `tests/test_feedback_service.py`

至少覆盖:

1. `record_report_review()` 正常写入结构化 label
2. `record_report_event_review()` 能写入 `report_run_id/event_id/brief_id/evidence_refs`
3. `list_feedback()` 可按 `subject_id / label_type / issue_type` 过滤
4. `summarize_feedback_actions()` 能稳定聚合 issue type 与建议动作
5. trace 外的 `event_id` 不报错，但会标出 `out_of_trace_target`

## 8. 成功标准映射

本设计对应 `EIL-603` 的验收映射如下:

1. 人工 review 结果可结构化入库
   - 由 `record_report_review()` / `record_report_event_review()` 完成
2. 反馈字段能够映射到后续调优动作
   - 由 `summarize_feedback_actions()` 完成

## 9. 实施边界

本票完成后，系统状态将变为:

1. 任何一次 report run 都可以被结构化 review
2. feedback 能稳定落到 `evaluation_labels`
3. feedback 能汇总为后续调优建议

但仍不包含:

1. UI 标注界面
2. 自动调参
3. 自动将 feedback 回灌到 `EvaluationRunner`
