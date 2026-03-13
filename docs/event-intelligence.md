# Event Intelligence 当前状态

**日期**: 2026-03-13
**状态**: Event-centric 主链路已落地，当前进入下一轮优化
**配套文档**: [technical-design.md](./technical-design.md) | [iteration-plan.md](./iteration-plan.md) | [archive/event-intelligence-roadmap.md](./archive/event-intelligence-roadmap.md) | [archive/event-intelligence-backlog.md](./archive/event-intelligence-backlog.md)

## 当前事实

- Event Intelligence 已经是唯一正式的采集与研报主链路。
- `src/main.py` 和 `src/run_report.py` 统一通过 `DeepCurrentsEngine` 进入 event-centric runtime。
- 运行时依赖 PostgreSQL、Qdrant、Redis；预测评分仍使用 SQLite `predictions`。
- runtime 未启用或启动失败时，采集和研报入口都保持 fail-closed，不再回退旧文章级链路。

## 关键核心演进 (2026-03-14)

- **深度事件摘要 (`llm_v1`)**: 事件总结器不再依赖硬编码模板，支持基于 LLM 的跨文章逻辑整合，能够识别因果传导路径与资产定价影响。
- **增强型金融富化**: 事件富化服务接入 AI 语义识别，支持自动映射具体资产标的 (Tickers)、提取受影响的金融频道 (Market Channels) 并识别地缘/宏观因子。
- **动态配额与上下文预算**: 重构了 `ContextQuotaPolicy`，放宽了 `macro_daily` 等策略的事件容量上限，并允许按主题重要性动态分配 Token 预算。
- **宏观决策因子化**: 将 VIX、10Y-2Y 息差等行情指标作为一级决策因子注入 Agent 系统，提升了在无新闻时期的策略深度。

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
