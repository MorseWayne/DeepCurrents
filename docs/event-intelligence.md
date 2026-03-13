# Event Intelligence 当前状态

**日期**: 2026-03-13
**状态**: Event-centric 主链路已落地，当前进入下一轮优化
**配套文档**: [technical-design.md](./technical-design.md) | [iteration-plan.md](./iteration-plan.md) | [archive/event-intelligence-roadmap.md](./archive/event-intelligence-roadmap.md) | [archive/event-intelligence-backlog.md](./archive/event-intelligence-backlog.md)

## 当前事实

- Event Intelligence 已经是唯一正式的采集与研报主链路。
- `src/main.py` 和 `src/run_report.py` 统一通过 `DeepCurrentsEngine` 进入 event-centric runtime。
- 运行时依赖 PostgreSQL、Qdrant、Redis；预测评分仍使用 SQLite `predictions`。
- runtime 未启用或启动失败时，采集和研报入口都保持 fail-closed，不再回退旧文章级链路。

## 首轮已完成范围

- runtime bootstrap、schema bootstrap、repository 边界已经落地。
- article-first ingestion、特征抽取、cheap/semantic dedup、事件构建、状态机和事件增强已经落地。
- 排序、证据选择、event brief、theme brief、report context builder 已经接入正式主链路。
- report orchestrator、report run tracker、evaluation runner、feedback 写入与查询能力已经落地。
- 旧 `raw_news -> classifier -> clustering -> generate_daily_report()` 主链路已经退役。

## 明确未完成或仍在迭代的部分

- `EVENT_INTELLIGENCE_RERANKER_MODEL` 目前只是配置位，reranker 还没有接入生产链路。
- `final_report_review` 仍是 `evaluation_runner` 中的 placeholder suite，不是可用的人审闭环。
- feedback 已可写入、查询和聚合建议，但还没有自动回灌到 evaluation 或调优流程。
- provider 兼容性仍需继续加固，尤其是 embedding model 可用性检查、preflight 校验和错误暴露。
- 生产化、调优和观测增强仍属于持续迭代，不应再用首轮 backlog 完成状态代替当前系统状态。

## 当前运行注意事项

- 宿主机手动运行时，必须在 `.env` 中显式配置 `EVENT_INTELLIGENCE_*`；`docker-compose.yml` 内的容器环境变量不会自动影响宿主机进程。
- embedding model 必须是当前 provider 真正支持的模型名，否则会在特征抽取阶段失败。
- PostgreSQL `JSON/JSONB` 编解码已在 `src/services/postgres_store.py` 统一处理，repository 层不需要再手工 `json.dumps()`。

## 历史文档入口

- 路线图: [archive/event-intelligence-roadmap.md](./archive/event-intelligence-roadmap.md)
- 首轮 backlog: [archive/event-intelligence-backlog.md](./archive/event-intelligence-backlog.md)
- 设计稿: [archive/specs/event-intelligence-layer.md](./archive/specs/event-intelligence-layer.md)
- 评估设计: [archive/specs/event-intelligence-evaluation.md](./archive/specs/event-intelligence-evaluation.md)
- feedback 设计: [archive/specs/event-intelligence-feedback.md](./archive/specs/event-intelligence-feedback.md)
