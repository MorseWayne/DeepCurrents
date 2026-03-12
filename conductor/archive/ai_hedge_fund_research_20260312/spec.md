# Track Specification: Research ai-hedge-fund Integration

## Overview
调研 `ai-hedge-fund` 的技术栈，分析其多智能体架构和金融分析工具，并制定将相关特性整合进 DeepCurrents 的实施计划。

## Functional Requirements
- **多智能体角色调研**: 分析 `ai-hedge-fund` 的不同 Agent 角色（如：Fundamentals, Sentiment, Risk）及其协作逻辑。
- **金融数据与工具分析**: 识别其使用的数据源（如 Alpha Vantage）及技术工具（如分析库），评估其在 DeepCurrents 采集流程中的复用性。
- **回测与评估机制调研**: 学习其如何验证投资决策，探讨如何在 DeepCurrents 的研报生成中引入类似的回测/评分系统。
- **整合映射**: 明确 `ai-hedge-fund` 的哪些具体组件可用于优化 DeepCurrents 的 LLM 推理引擎。

## Acceptance Criteria
- 提供一份包含具体步骤的实施计划。
- 明确多智能体角色如何与 DeepCurrents 的“深流”管线（Fuzzy Dedup -> LLM Reasoning -> Report）相结合。
- 提供选定功能的潜在技术选型（如：新增哪些数据源 SDK）。

## Out of Scope
- 在此 Track 中直接实现全自动交易逻辑。
- 复用与宏观策略无关的基础设施。
