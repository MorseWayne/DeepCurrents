# Track Specification: AI Hedge Fund Features Implementation

## Overview
基于对 `ai-hedge-fund` 的调研，在 DeepCurrents 中实现多智能体（Multi-Agent）协作架构。引入 `Macro Analyst`, `Sentiment` 和 `Market Strategist` 三个角色，通过 `yfinance` 注入真实行情数据，并建立 AI 预测准确性的事后验证评分系统。

## Functional Requirements
- **多智能体推理逻辑**:
    - **Macro Analyst Agent**: 专注于全球地缘政治和宏观经济政策对市场的影响分析。
    - **Sentiment Agent**: 从新闻和 RSS 摘要中分析市场看涨/看跌情绪。
    - **Market Strategist Agent**: 负责根据 `yfinance` 提供的真实行情数据，对前两个智能体的分析进行交叉验证，并形成最终结论。
- **yfinance 集成**: 引入相关的获取脚本，获取核心资产（黄金、原油、标普 500 等）的价格走势。
- **准确性评分系统**:
    - 在数据库中新增 `predictions` 表，记录 AI 对某一资产在特定时间点的研判。
    - 定期触发评分任务，对比真实价格走势，为该预测评分。
- **研报优化**: 在合成研报时，展示各智能体的独立意见及其推理逻辑。

## Acceptance Criteria
- 推理流程成功调用三个不同的角色 Prompt。
- 研报中能正确注入 `yfinance` 的价格快照数据。
- 数据库能正确记录 AI 预测并计算出准确率评分。
- 所有新功能需通过单元测试。

## Out of Scope
- 全自动投资组合回测。
- 接入除 `yfinance` 以外的其他付费金融 API。
