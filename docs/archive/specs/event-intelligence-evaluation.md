# Event Intelligence Evaluation Runner Design

- 日期: 2026-03-13
- 状态: 已归档（历史设计稿）
- 适用范围: `src/services/evaluation_runner.py`、`tests/evaluation/`、`tests/fixtures/event_intelligence/`
- 关联 backlog: `docs/archive/event-intelligence-backlog.md` 中 `EIL-602`
- 关联设计: `docs/archive/specs/event-intelligence-layer.md`

## 0. 背景

截至当前版本，仓库中已经冻结了三类 Event Intelligence 评估 fixtures:

1. `duplicate_pairs.json`
2. `same_event_pairs.json`
3. `top_event_relevance.json`

并通过 `tests/evaluation/fixture_loader.py` 提供了稳定加载入口。

但系统仍缺少一个统一 runner 来回答以下问题:

1. 每次大改后如何一键复算核心质量指标。
2. 如何用统一结构输出 duplicate leakage、same-event 命中率、Top-K relevance 等结果。
3. 当 `final report editorial review` 尚未建好标注集时，如何保留接口但不阻塞自动回归。

## 1. 目标

`EIL-602` 的第一版目标是建立统一评估 runner，而不是接入完整生产 runtime。

本票目标:

1. 在 `src/services/evaluation_runner.py` 提供统一入口，收敛 duplicate、same-event、top-N relevance 和 final report review 四类 suite。
2. 第一版完整实现前三类自动评估。
3. 为 `final_report_review` 保留稳定接口和结果占位，状态明确为 `not_configured`。
4. 输出固定格式的结构化结果，支持后续比较和人工查看。

本票非目标:

1. 不要求启动数据库、Qdrant、Redis 或完整 engine。
2. 不把 runner 直接耦合到真实 `SemanticDeduper`、`EventBuilder` 或 `EventRanker` runtime。
3. 不在本票定义新的人工 review 标注集。
4. 不在本票实现反馈闭环或 evaluation labels 落库。

## 2. 方案选择

本票采用“可注入依赖的离线 runner”方案。

不采用其它方案的原因:

1. 若把评估逻辑完全散在 `pytest` 中，将缺少统一结果 schema，不利于后续比较报表和固定基线。
2. 若直接接入真实 runtime，将把 `EIL-602` 变成脆弱的集成测试工程，范围明显超过当前票。

因此 runner 只负责 orchestration，具体判定逻辑通过默认 evaluator 或可注入 resolver/provider 完成。

## 3. Runner 边界

### 3.1 统一入口

`EvaluationRunner` 提供至少两个入口:

1. `run_all()`
2. 按 suite 单独执行的方法或等价私有流程

Runner 只依赖:

1. fixtures loader
2. 可注入的 duplicate resolver
3. 可注入的 same-event resolver
4. 可注入的 ranked event provider

### 3.2 评估 suite

第一版 runner 固定包含四个 suite:

1. `duplicate_pairs`
2. `same_event_pairs`
3. `top_event_relevance`
4. `final_report_review`

其中前三个真正执行，第四个仅返回标准化占位结果。

## 4. Evaluator 职责

### 4.1 `duplicate_pairs`

输入:

1. `duplicate_pairs.json`

依赖:

1. `duplicate_relation_resolver(left, right) -> bool`

第一版默认实现:

1. 规范化 `canonical_url` 后相同则判定为 duplicate。
2. 若 URL 不足，则按标题标准化相等或高度相似做保底判定。

输出:

1. pair 级 pass/fail
2. suite 级通过率
3. duplicate leakage 指标

### 4.2 `same_event_pairs`

输入:

1. `same_event_pairs.json`

依赖:

1. `same_event_resolver(left, right) -> bool`

第一版默认实现:

1. 时间窗接近
2. 标题 token overlap 足够高
3. 关键事件词、区域词、央行/航运等主题词有明显重叠

输出:

1. pair 级 pass/fail
2. suite 级命中率
3. same-event miss 指标

### 4.3 `top_event_relevance`

输入:

1. `top_event_relevance.json`

依赖:

1. `ranked_event_provider(query_payload) -> list[event_like]`

第一版默认实现:

1. 若未注入 provider，则直接消费 fixture 中的 `candidates`
2. 默认按 `expected_rank` 升序作为稳定基线

输出:

1. Top-K precision
2. 平均 rank 偏移
3. 关键相关事件遗漏率

### 4.4 `final_report_review`

第一版不做真实评估器。

输出固定为:

1. `suite = final_report_review`
2. `status = not_configured`
3. `samples_total = 0`
4. `samples_passed = 0`
5. `samples_failed = 0`
6. `metrics = {}`
7. `failures = []`

该 suite 不参与整体验收失败判定，但必须出现在统一结果中。

## 5. 统一结果 Schema

### 5.1 Suite 级结果

每个 suite 输出统一结构:

1. `suite`
2. `status`
3. `samples_total`
4. `samples_passed`
5. `samples_failed`
6. `metrics`
7. `failures`

`status` 第一版取值:

1. `passed`
2. `failed`
3. `not_configured`

### 5.2 Runner 总结果

`run_all()` 输出统一结构:

1. `generated_at`
2. `profile`
3. `suites`
4. `summary`

`summary` 第一版至少聚合:

1. `suite_count`
2. `passed_suite_count`
3. `failed_suite_count`
4. `not_configured_suite_count`
5. `article_to_event_compression_ratio`
6. `duplicate_leakage_rate`
7. `critical_miss_rate`
8. `top_k_precision`

其中:

1. `duplicate_leakage_rate` 来自 duplicate suite
2. `critical_miss_rate` 优先来自 top relevance suite
3. `top_k_precision` 来自 top relevance suite
4. `article_to_event_compression_ratio` 第一版通过 fixture 规模与相关事件数的近似值产出，作为可比较指标，而非生产真实运行值

## 6. 测试设计

新增:

1. `tests/test_evaluation_runner.py`

至少覆盖:

1. `run_all()` 能同时产出四个 suite 的统一结果
2. 三个自动 suite 在默认 evaluator 下能稳定运行
3. `final_report_review` 在无 fixture 时输出 `not_configured`
4. 注入自定义 resolver/provider 时，runner 采用注入逻辑
5. summary 中的聚合指标可复现

## 7. 与后续票的关系

本票完成后:

1. 仓库将具备稳定的一键离线回归骨架
2. 但 `final_report_review` 仍是占位结果

后续票继续承担:

1. `EIL-603`：补齐人工 review / feedback schema，并把其结果真正接入 `final_report_review`
2. 可能的后续增强：把真实 `SemanticDeduper`、`EventBuilder`、`EventRanker` 适配为 runner 的 provider，而不改动 runner 总体结构

## 8. 成功标准映射

本设计对应 `EIL-602` 的验收映射如下:

1. 可以一键复算核心质量指标
   - 由 `EvaluationRunner.run_all()` 完成
2. 输出足以判断 `5:1` 压缩比、Top-K 精度与 miss/leakage 趋势
   - 由统一 summary 和 suite metrics 提供
3. 评估输出可同时复算 token/覆盖相关代理指标
   - 第一版先提供稳定结构和近似代理指标，后续可在不破坏 schema 的前提下扩充真实运行数据
