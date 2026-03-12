# Implementation Plan: AI Hedge Fund Features Implementation

## Phase 1: 基础设施与数据集成 (Infrastructure & Data SDK) [checkpoint: 7994575]
- [x] Task: 集成 `yfinance` 获取金融行情数据
    - [x] 创建辅助脚本获取指定资产的价格走势
    - [x] 通过 TypeScript 实现对该脚本的调用逻辑
    - [x] 编写测试用例验证数据获取的准确性
- [x] Task: 数据库 Schema 更新：新增 `predictions` 与 `scores` 表
    - [x] 更新 SQLite 数据库，记录 AI 研判及预测时的基准价格
    - [x] 实现数据持久化逻辑
- [x] Task: Conductor - User Manual Verification 'Phase 1: Infrastructure' (Protocol in workflow.md)


## Phase 2: 多智能体推理引擎开发 (Multi-Agent Engine) [checkpoint: a426671]
- [x] Task: 定义多智能体 Prompt 模板与角色分配
    - [x] 编写 `Macro Analyst`, `Sentiment`, `Market Strategist` 的系统提示词
    - [x] 更新 `ai.service.ts` 支持多角色并发推理
- [x] Task: 实现 Market Strategist 的交叉验证逻辑
    - [x] 将获取的价格走势注入到 `Market Strategist` 的 Prompt 中
    - [x] 验证推理逻辑中的权重平衡
- [x] Task: 编写多智能体协作的集成测试
    - [x] 模拟输入聚类事件，验证三个 Agent 的输出逻辑
- [x] Task: Conductor - User Manual Verification 'Phase 2: Agent Engine' (Protocol in workflow.md)

## Phase 3: 准确性评分与研报增强 (Accuracy Scoring & Report Enhancing) [checkpoint: 8d9b657]
- [x] Task: 实现自动评分 Cron 任务
    - [x] 定期查询过期预测并对比最新价格计算评分
    - [x] 更新 `db.service.ts` 中的评分持久化逻辑
- [x] Task: 优化研报合成模板，展示 Agent 推理链
    - [x] 在报告中加入“智能体研判详情”板块
    - [x] 展示置信度评分和历史准确率参考
- [x] Task: 最终全流程回归测试与文档更新
    - [x] 验证从采集到生成报告、再到事后评分的完整闭环
- [x] Task: Conductor - User Manual Verification 'Phase 3: Scoring & Enhancement' (Protocol in workflow.md)
