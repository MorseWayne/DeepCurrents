# 宏观传导链研报扩展设计

## 背景

当前事件驱动型研报虽然结构完整，但结论层明显过浅。

已观察到的典型问题：

- `executiveSummary`、`economicAnalysis` 和 `investmentTrends` 经常重复同一层意思，信息增量很低
- 报告能够描述事件，但不能清晰解释从事件冲击到宏观变量、再到资产定价和配置含义的完整传导链
- 当 `MarketStrategist` 输出稀疏时，fallback 会退化成泛化总结语，分析深度明显丢失
- 当前 schema 中没有专门承载“总主线宏观传导链”或“关键资产传导拆解”的结构化字段

本次要解决的不是“把文字写长”，而是把研报结论升级为更高维度、更稳定的结构化输出。

## 目标

扩展日报输出格式，使其稳定呈现：

- 一条偏宏观视角的“总主线传导链”
- 两到四个从该主线拆解出的“关键资产传导分析”

该设计必须与当前管线兼容，并在模型输出不完整时安全退化。

## 非目标

- 不重做事件排序、聚类或证据筛选逻辑
- 不要求最终研报阶段重新读取原始文章全文
- 不替换现有 `investmentTrends`；它仍然作为精简版配置结论保留
- 不做超出新增段落渲染之外的大规模 UI 或通知系统重构

## 备选方案

### 1. 只改 Prompt 扩写文本

仅通过 prompt 要求模型把 `economicAnalysis` 和 `investmentTrends` 写得更像“传导链”。

优点：

- 改动面最小
- 不需要调整下游模型结构

缺点：

- 对稀疏输出没有约束力，稳定性差
- 难以校验，也难以做确定性的 fallback
- 宏观解释和资产结论仍然混在自由文本里

### 2. 扩展结构化输出并配套确定性 fallback（采用）

新增“宏观传导链”和“关键资产拆解”字段，并在模型遗漏或写得过空时做结构化补全。

优点：

- 直接解决研报维度不足的问题
- 宏观逻辑和资产结论边界清晰
- 可以对 sparse output 做确定性兜底
- 给 notifier 和后续展示层稳定的数据结构

缺点：

- 需要联动修改模型、prompt、解析、fallback 和渲染逻辑

### 3. 仅做后处理拼装

保持现有 schema 不变，在 report 生成后程序化追加一段“传导链”分析。

优点：

- 对 LLM 格式服从依赖更低
- 可以作为较窄的补丁上线

缺点：

- 分析质量上限受现有简短字段限制
- 会形成两套并行的报告表达方式
- 不能从根本上升级 JSON 合约

## 采用方案

### 报告结构扩展

在 `DailyReport` 中新增两个可选字段：

- `macroTransmissionChain`
- `assetTransmissionBreakdowns`

`macroTransmissionChain` 表示当天唯一的一条宏观总主线，用来回答：

- 当前最核心的冲击源是什么
- 哪些宏观变量最先被重定价
- 这些变量如何传导到市场定价
- 这对当前配置姿态意味着什么

建议字段结构：

- `headline`：一句话宏观主线
- `shockSource`：主冲击源或主事件主题
- `macroVariables`：两到四个关键宏观变量
- `marketPricing`：跨资产定价影响概述
- `allocationImplication`：配置含义总结
- `steps`：三到五步的链路节点，每个节点包含 `stage` 和 `driver`
- `timeframe`
- `confidence`

`assetTransmissionBreakdowns` 用于承载两到四个关键资产或资产簇的拆解。每条拆解要回答：

- 当前方向判断是什么
- 这个资产主要表达的是哪一段宏观传导
- 为什么价格推动仍可能延续，或者为什么已经接近尾声
- 接下来哪些信号会验证或证伪该判断

建议单条结构：

- `assetClass`
- `trend`
- `coreView`
- `transmissionPath`
- `keyDrivers`
- `watchSignals`
- `timeframe`
- `confidence`

### 各段落职责划分

扩展后各段落分工如下：

- `executiveSummary`：简要总括
- `macroTransmissionChain`：主宏观传导逻辑
- `globalEvents`：最重要的底层事件
- `economicAnalysis`：对总主线的补充性展开
- `assetTransmissionBreakdowns`：关键资产的详细拆解
- `investmentTrends`：简明配置结论

这样可以避免当前 `economicAnalysis` 和 `investmentTrends` 同时承担全部分析负荷，导致重复表述、但没有结构增量的问题。

### Prompt 调整

`MarketStrategist` 必须被明确要求输出：

- 严格一条 `macroTransmissionChain`
- 两到四条 `assetTransmissionBreakdowns`
- 宏观传导逻辑与资产配置/交易含义分开表达

Prompt 中需要直接约束模型使用如下思路组织内容：

`冲击源 -> 宏观变量 -> 市场定价 -> 配置含义`

同时显式禁止模型把“复述事件”当作“传导链分析”。

`MacroAnalyst` 与 `SentimentAnalyst` 的输出结构可以保持不变。它们继续为 strategist 提供输入，但最终日报中的新增结构由 `MarketStrategist` 负责产出。

### 归一化处理

`AIService.normalize_daily_report_payload()` 需要对新增字段做防御性归一化：

- 缺失字段不能导致解析失败，应回退为空结构或空列表
- 标量、错误类型或畸形列表需要尽量整理为稳定容器
- `trend`、`timeframe`、`confidence` 延用当前投资趋势字段的归一化规则

归一化必须保持向后兼容，确保历史报告或旧 fixture 在不包含新字段时仍然可以正常解析。

### Sparse Fallback

本设计要求“确定性 fallback”，不能只依赖 prompt 提示。

如果 `macroTransmissionChain` 缺失或内容过空：

- 从最高优先级事件和最强主题中推导
- 优先使用 `stateChange`、`whyItMatters`、`marketChannels`、`regions`、主题 summary 等字段
- 即使表达较保守，也必须输出一条完整的四段式传导链

如果 `assetTransmissionBreakdowns` 缺失或内容过空：

- 基于 `investmentTrends`、已选主题和已选事件推导两到四条资产拆解
- 当主题明显指向能源或风险偏好时，保证至少有一条对应的资产视角
- 在可用的前提下为每条资产补上可跟踪的验证信号

Sparse 判定不能只检查字段是否存在，还要把“地缘政治影响市场”这类空泛表述视为无效分析。

### 渲染与展示

通知渲染层新增两个明确段落：

- `总主线传导链 | Macro Transmission`
- `关键资产拆解 | Asset Breakdown`

推荐展示顺序：

1. 核心主线摘要
2. 总主线传导链
3. 重大事件
4. 关键资产拆解
5. 精简投资结论
6. 风险评估

对于不含新字段的旧报告，渲染层仍需保持兼容，不得报错或出现空标题。

## 错误处理

- 新字段缺失不能导致日报解析失败
- 新字段格式错误应退化为空结构或归一化结构，而不是抛异常
- `MarketStrategist` 输出稀疏时，除了现有 summary/economic/trend fallback 外，还要对新增字段做定向补全
- 日志中应记录新增字段到底来自模型原始输出还是 fallback 补齐

## 可观测性

在 report stage 增加以下诊断指标：

- `macroTransmissionChain` 是否存在
- `assetTransmissionBreakdowns` 实际产出了多少条
- 哪些字段触发了 fallback

原因很明确：当前核心问题不是模型调用失败，而是“调用成功但信息密度不够”。

## 测试计划

- 为新增字段的缺失、畸形格式、错误类型增加 normalization 测试
- 为 orchestrator 增加宏观传导链与资产拆解的 fallback 测试
- 为 notifier/render 增加新旧报告兼容渲染测试
- 更新一个手工 fixture，用于展示新增段落的典型输出

## 成功标准

- 只要存在可报告事件上下文，最终日报都应包含一条宏观导向的总主线传导链
- 正常的 `macro_daily` 运行应至少产出两条关键资产拆解
- `economicAnalysis` 不再独自承担全部传导链表达职责
- `MarketStrategist` 输出稀疏时，报告不再退化回低维度的泛化总结

## 备注

- 这份 spec 记录了本轮 brainstorming 确认后的设计结果
- 当前会话中没有可用的 spec-review subagent 和 `writing-plans` skill，因此无法完整执行技能要求的自动 review 流程
