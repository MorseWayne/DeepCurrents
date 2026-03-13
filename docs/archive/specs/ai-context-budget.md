# AI 上下文预算优化设计（仅 Python `src/`）

- 日期：2026-03-12
- 范围：仅 `src/`（Python 主链路）
- 状态：已批准进入实现

## 1. 背景

`src/services/ai_service.py` 当前的上下文预算方式是：基于 `AI_MAX_CONTEXT_TOKENS` 做固定比例切分，并使用粗粒度字符长度估算 token。该方式存在三个问题：

1. 与模型真实上下文窗口不对齐。
2. 未覆盖最终 Strategist 输入膨胀（raw context + 中间智能体输出 + 行情块 + 模板文本）。
3. 无法根据各分段实际使用量进行二次再分配。

## 2. 已确认决策

1. 运行时预算逻辑移除 `AI_MAX_CONTEXT_TOKENS` 依赖。
2. 模型窗口优先运行时从 provider 元数据获取；失败后回退本地模型窗口映射；仍失败则使用保守值 `16000`。
3. 输出预留采用比例制（8%）并附带内置最小/最大夹取。
4. 本次迭代不新增 `.env` 配置项。
5. 若窗口解析全失败，采用保守回退继续运行，不做硬失败。

## 3. 目标与非目标

### 目标

1. 每次请求的输入 prompt 保持在可用模型窗口内。
2. 提升 news/cluster/trending 分段的预算利用率。
3. 在 Strategist 调用前增加最终 guard，避免超窗失败。
4. 保持现有研报生成行为与回退鲁棒性。

### 非目标

1. 不引入跨语言链路改造。
2. 本阶段不新增外部配置面。
3. 不进行预算控制之外的提示词内容重构。

## 4. 方案架构

变更集中在 `src/services/ai_service.py`（若需要更清晰可拆到 `src/services/` 下辅助模块）。

### 4.1 上下文窗口解析器

新增运行时解析流程：

1. 调用 provider 元数据接口获取当前模型窗口。
2. 失败后使用内置 `MODEL_CONTEXT_WINDOW_FALLBACKS` 映射。
3. 映射缺失时使用 `16000`。
4. 对成功结果做短 TTL 缓存，降低元数据请求频率。

本阶段元数据读取约定：

1. 优先 OpenAI 兼容元数据端点（`GET /v1/models/{model}` 或 provider 等价端点）。
2. 若元数据未提供明确窗口字段，视为元数据未命中并回退映射。
3. 字段解析兼容常见别名（`context_window`、`max_context_tokens`、`input_tokens`）。

### 4.2 输入预算计算器

给定 `context_window`：

1. `output_reserve = clamp(context_window * 0.08, RESERVE_MIN, RESERVE_MAX)`
2. `usable_input = context_window - output_reserve - SAFETY_MARGIN - PROMPT_OVERHEAD`
3. 保证下界（不低于最小可工作输入）。

本次迭代采用代码内置常量。

实现初始常量：

1. `OUTPUT_RESERVE_RATIO = 0.08`
2. `OUTPUT_RESERVE_MIN = 2048`
3. `OUTPUT_RESERVE_MAX = 16384`
4. `SAFETY_MARGIN = 4000`
5. `PROMPT_OVERHEAD = 2000`
6. `MIN_WORKING_INPUT = 2000`
7. `WINDOW_CACHE_TTL_SEC = 900`

### 4.3 动态分段预算分配

raw context 采用动态分配：

1. 初始权重：`news=65%`、`cluster=20%`、`trending=15%`。
2. 某分段预算未用完时，剩余进入回流池。
3. 回流优先级：`news > cluster > trending`。
4. 最终组合上下文必须不超过 `usable_input`。

Python 当前链路可不存在 trending；该权重应自然回流。

### 4.4 Strategist 输入 Guard（二次约束）

在调用 MarketStrategist 前，先估算完整输入：

1. raw context
2. macro 输出
3. sentiment 输出
4. 行情数据块
5. 模板/系统开销

若超预算，按优先级裁剪：

1. 低优先级 raw context 条目
2. cluster context
3. 高优先级 news（最后手段）

发送请求前必须执行最终硬上限截断。

### 4.5 Provider 回退兼容

同一请求在回退时可能切到更小窗口模型。为避免回退后超窗：

1. 预先解析本次调用链路中所有可用 provider/model 的窗口。
2. 以其中最小窗口作为共享上下文构建基线。
3. 若部分 provider 窗口不可得，最小值计算中纳入保守回退值。
4. 记录各 provider 解析窗口及最终基线窗口。

## 5. 数据流变更

1. `generate_daily_report()` 先解析 primary/fallback 的有效窗口并确定安全基线窗口。
2. 基于该窗口计算 `usable_input` 并构建受控 `raw_context`。
3. 其余智能体调用流程保持不变。
4. Strategist 输入组装后经过 guard 压缩。
5. Strategist 调用在预算约束内执行。

## 6. 异常处理与可观测性

### 异常处理

1. 元数据接口错误：记录警告并降级到映射/保守回退。
2. 预算计算异常：降级到保守默认。
3. guard 无法充分压缩：执行最终硬截断后继续。

### 日志（避免内容泄露）

每次生成研报记录：

1. `model`、`resolved_window`、`output_reserve`、`safety_margin`、`usable_input`
2. 各分段分配与实际使用量
3. strategist guard 前后 token 估算及裁剪分段

仅记录长度/计数，不输出正文内容。

## 7. 测试计划

在 `tests/` 中新增或调整：

1. `test_ai_service`：元数据成功时使用运行时窗口。
2. `test_ai_service`：元数据失败 + 映射命中路径。
3. `test_ai_service`：元数据失败 + 映射缺失时使用 `16000`。
4. `test_ai_service`：紧预算下 `build_news_context` 退化为 `header-only`。
5. `test_ai_service`：Strategist 输入超限时触发 guard 并继续执行。
6. `test_config`：移除依赖 `AI_MAX_CONTEXT_TOKENS` 行为的断言。

## 8. 兼容与发布

1. 设置层临时容忍 `.env` 里的旧键，保证向后兼容。
2. 文档标注 `AI_MAX_CONTEXT_TOKENS` 已废弃，运行时逻辑不再依赖。
3. 发布建议同批包含代码、测试、README/文档更新。

## 9. 风险与缓解

1. provider 元数据异构。
   - 缓解：健壮字段解析 + 映射回退 + 安全默认值。
2. token 估算存在误差。
   - 缓解：安全余量 + 二次 guard + 最终硬截断。
3. 激进裁剪导致信息损失。
   - 缓解：基于优先级裁剪，高优先内容最后才裁。
