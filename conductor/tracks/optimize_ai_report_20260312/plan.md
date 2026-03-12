# Implementation Plan: 优化 AI 提示词与上下文注入

## Phase 1: Research & Baseline
- [ ] Task: 分析现有的 Prompt 模板和上下文注入逻辑
- [ ] Task: 建立基准测试用例，记录当前生成效果
- [ ] Task: Conductor - User Manual Verification 'Research & Baseline' (Protocol in workflow.md)

## Phase 2: Prompt Optimization
- [ ] Task: 设计并实现新的 Prompt 模板注入逻辑（包含角色设定、任务指令、格式规范）
- [ ] Task: 编写测试用例验证新 Prompt 的输出格式与逻辑注入
- [ ] Task: Conductor - User Manual Verification 'Prompt Optimization' (Protocol in workflow.md)

## Phase 3: Context Enhancement
- [ ] Task: 优化聚类事件的摘要提取逻辑，减少冗余并改进注入权重
- [ ] Task: 验证增强后的上下文生成逻辑，确保符合 Token 预算管理
- [ ] Task: Conductor - User Manual Verification 'Context Enhancement' (Protocol in workflow.md)

## Phase 4: Finalization
- [ ] Task: 运行全量回归测试，确保新逻辑不影响其他功能
- [ ] Task: 对比优化前后的研报质量，验证改进效果
- [ ] Task: Conductor - User Manual Verification 'Finalization' (Protocol in workflow.md)
