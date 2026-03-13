# DeepCurrents 下一轮迭代计划

**日期**: 2026-03-13
**状态**: Planned
**基线**: 当前 event-centric 主链路已可运行，但 runtime hardening、质量闭环和观测仍需补齐

## 目标

本轮不再做第二次大重构，而是在现有 Event Intelligence 架构上完成四件事:

1. 降低手动跑批和日常调度的运行风险。
2. 提升检索、归并和排序质量。
3. 补齐 report quality 的评估闭环。
4. 收束文档和运维入口，减少状态判断成本。

## 规划原则

- 保持当前 event-centric 架构，不重启旧文章级链路。
- 先修 runtime 与 provider 兼容性，再做 reranker 和质量增强。
- 每项优化都必须带测试、日志和清晰的回退开关。
- 活跃文档只维护当前事实，历史推演统一放在 `docs/archive/`。

## 迭代一: Runtime Hardening

范围:

1. 启动前检查 embedding model、provider 可用性和关键依赖连通性。
2. 明确区分宿主机模式与 compose 模式的环境配置错误。
3. 提升 `run_report` 的失败原因输出，让“跳过”和“报错”可区分。
4. 为 fail-closed 入口补充更稳定的结构化日志和运行摘要。

完成标准:

- 常见配置错误能在启动前给出明确原因。
- 手动运行失败时，日志能直接指出是 runtime、provider 还是数据为空。

## 迭代二: Retrieval 与 Ranking 质量

范围:

1. 在召回后引入可开关的 reranker，而不是仅保留配置项。
2. 基于现有 evaluation fixtures 对比有无 reranker 的排序效果和延迟成本。
3. 继续优化 event ranking profile、evidence 选择和解释字段的稳定性。

完成标准:

- reranker 可配置启停，不影响默认主链路可用性。
- 评估结果能量化说明 reranker 是否值得开启。

## 迭代三: Evaluation 与 Feedback 闭环

范围:

1. 将 `final_report_review` 从 placeholder 变成真实的评估入口。
2. 把 feedback 聚合结果自动回灌到 evaluation summary 或调优建议。
3. 补一份按 `report_run` 聚合的质量摘要，便于定位劣化来源。

完成标准:

- 单次研报可以关联自动评估结果和人工 review 结果。
- 反馈不再只停留在存储层，而能进入调优流程。

## 迭代四: 运维与文档收尾

范围:

1. 固化 provider model 兼容矩阵和部署检查清单。
2. 为常用手动命令补简明运维说明和排障路径。
3. 持续把新增决策收束到 `docs/` 主文档，避免再次堆积同类设计稿。

完成标准:

- 新成员可以只读 `README.md` 和 `docs/` 主文档完成本地排障。
- 新迭代结束后不再新增平行 roadmap/backlog 文档。

## 非目标

- 不更换 PostgreSQL、Qdrant、Redis 作为当前运行时基础设施。
- 不在本轮引入新的 UI 或平台化前端。
- 不恢复旧文章级主链路作为兜底方案。
