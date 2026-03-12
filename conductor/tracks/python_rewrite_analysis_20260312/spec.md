# Track Specification: Python Rewrite Feasibility Analysis

## Overview
调研并深度分析将 DeepCurrents 引擎从现有的 `TypeScript/Node.js + Python 脚本` 混合架构，全面重写为 `100% Python` 架构的可行性。目标是消除跨语言通信的维护成本，并在 Python 生态中更好地原生集成数据科学与 AI 库（如 yfinance, pandas）。因为项目尚未正式部署且处于早期阶段，无需考虑历史数据库迁移的包袱。

## Functional Requirements
- **架构映射与选型**: 确定等价于 Node.js 组件的 Python 库组合（如：`aiohttp` 替代 `axios`/`rss-parser`，`Pydantic` 替代 `Zod`，`APScheduler` 替代 `node-cron`）。
- **并发与性能验证 (PoC)**: 编写微型原型，证明 Python 的异步 I/O (asyncio) 能够在 RSS 并发抓取上达到与 Node.js 相当的性能和容错性。
- **生态对齐**: 分析项目特有的逻辑（如基于 `Intl.Segmenter` 的多语言分词、模糊去重的算法实现）在 Python 中的原生替代品。
- **迁移规划**: 制定一份细致的代码重写实施计划，包括模块拆分、测试迁移和最终替换步骤。

## Acceptance Criteria
- 产出包含具体性能对比或验证结论的 **架构选型报告**（更新入 `tech-stack.md` 的备用方案或形成独立报告）。
- 提供可运行的 **Python 基础骨架代码 (PoC)**，涵盖异步抓取和 Pydantic 验证。
- 产出明确的 **完整重写计划 (`migration-plan.md`)**。

## Out of Scope
- 本阶段不执行全量生产代码的 100% 重写。
- 历史 SQLite 数据库的 Schema 迁移工具开发。
