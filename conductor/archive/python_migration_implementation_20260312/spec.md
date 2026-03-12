# Track Specification: Full Python Migration Implementation

## Overview
将 DeepCurrents 项目从 TypeScript/Node.js 完全迁移至 Python 3.10+。此任务不仅是代码的简单翻译，而是利用 Python 异步生态（aiohttp, asyncio）和 AI 生态（Pydantic, OpenAI Python SDK）重建整个情报管线。

## Functional Requirements
- **全面替换**: 将所有 TS 逻辑（数据采集、威胁分类、聚类、多智能体推理、评分系统、调度）重写为 Python。
- **架构一致性**: 保持原有的多层架构（Collector -> DB -> Analysis -> Intelligence -> Notifier）。
- **测试驱动 (TDD)**: 每一个 Python 模块必须编写对应的单元测试，确保其输入输出逻辑与原 TS 版本完全一致。
- **目录重组**: 
    - 将现有 TS 代码移动至 `src_ts/`。
    - 在 `src/` 目录下建立标准的 Python 包结构。
    - 引入 `pyproject.toml` 或 `requirements.txt` 管理依赖。

## Acceptance Criteria
- Python 版本在执行 `main.py` 时，能成功采集 RSS、识别威胁、生成多智能体研报并完成推送。
- 单元测试覆盖率达到 80% 以上，且核心算法（模糊去重、聚类）通过一致性校验。
- `README.md` 与 `tech-stack.md` 已根据 Python 架构完成更新。

## Out of Scope
- 增加新的业务功能逻辑。
- 维护双语言并行运行。
