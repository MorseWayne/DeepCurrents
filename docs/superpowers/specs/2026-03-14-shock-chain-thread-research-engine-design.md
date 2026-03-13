# Shock-Chain-Thread 研究引擎设计

**日期**: 2026-03-14
**状态**: Draft
**目标**: 在现有 event-centric 架构上新增面向宏观投资研究的 `Shock -> Chain -> Thread` 研究层，把系统重心从“事件摘要”推进到“传导链驱动的主线发现与持续跟踪”。

## 背景

`DeepCurrents` 当前已经完成 `article-first ingestion -> dedup -> event building -> ranking -> event-centric report orchestration` 主链路，能够稳定输出事件中心型宏观日报。

但对目标中的宏观投资研究场景，当前系统仍存在一个结构性缺口：

- 能抓到单条重要事件，但不能稳定抬出跨天持续的宏观主线
- 能描述事件内容，但不能把“起点冲击 -> 传导节点 -> 资产含义”结构化表达出来
- 排序更接近“事件显著性”，还没有明确转向“未来 1-4 周大类资产定价冲击”
- 研报虽然越来越完整，但底层研究对象仍然以 `event` 为中心，缺少能持续追踪的研究层

本次设计不是继续堆 prompt，也不是单纯扩写研报段落，而是在现有 event-centric 架构上新增一层更贴近 buy-side 研究流程的研究语义层。

## 目标

面向 `1-4 周` 决策节奏的宏观投资者，构建一个“传导链驱动的信号发现引擎”，使系统优先完成三件事：

- 更早识别对 `美股 / 美元 / 美债 / 黄金 / 原油` 有实质冲击潜力的起点事件
- 将起点事件组织为可更新的轻量传导链，而不是停留在事件摘要
- 把跨天重复出现的相关冲击和证据汇总成可持续追踪的研究主线

## 非目标

- 不重做 `article`、`event`、`evidence` 这些已落地的事实层对象
- 不在本轮引入重型知识图谱或全市场因果网络
- 不新增平台化 UI 或独立前端工作台
- 不把系统目标扩展到日内交易或 1-3 个月资产配置
- 不要求完全自动得出“正确交易结论”；本轮重点是把研究主线抬出来

## 第一用户与研究边界

本设计围绕以下边界展开：

- 第一用户：宏观投资者
- 主时域：`1-4 周`
- 首要判据：`对大类资产定价冲击强度`
- 优先资产：`美股 / 美元 / 美债 / 黄金 / 原油`
- 当前最大短板：系统看不出持续主线
- 下一阶段首要突破口：`传导链的起点识别`

因此，新研究层的判断标准不是“这条新闻热不热”，而是“它是否足以成为未来数周资产重定价的起点”。

## 备选方案

### 1. 继续强化事件排序和 prompt 表达

只在 `event_ranker` 和 `report_orchestrator` 上加更多规则和提示词，让现有事件层输出更像研究报告。

优点：

- 改动面最小
- 不需要新增中间对象

缺点：

- 无法解决“跨天主线承载对象缺失”的根因
- 输出仍然会过度依赖单次生成质量
- 很难区分“今天的大事”和“值得持续研究的主线”

### 2. 新增 Shock -> Chain -> Thread 研究层（采用）

在现有 `event` 事实层之上，新增三个研究对象：

- `Shock Candidate`
- `Transmission Chain`
- `Chain Thread`

优点：

- 直接对应“起点识别 -> 传导解释 -> 持续跟踪”三段能力
- 不推翻现有 event-centric 架构
- 更适合作为后续研报深度和质量评估的基础层

缺点：

- 需要联动新增评分、状态迁移和跨日归并逻辑
- 对可观测性和离线评估要求更高

### 3. 围绕资产先建驱动器

先按 `美股 / 美元 / 美债 / 黄金 / 原油` 建五个资产研究器，再反推出值得关注的事件。

优点：

- 更接近直接投资决策
- 输出会天然以资产为中心

缺点：

- 容易过早锁死资产视角
- 对新主题、新 regime 的起点发现能力不足
- 不能直接解决“主线归并”问题

## 采用方案

### 一、核心对象模型

#### 1. `Shock Candidate`

定义：从现有 `event` 中筛出的“可能触发未来 1-4 周大类资产重定价”的起点事件。

它不是普通事件标签，而是研究层入口对象。建议最少包含以下字段：

- `source_event_id`
- `shock_type`
- `shock_score`
- `impact_assets`
- `impact_horizon`
- `consensus_surprise`
- `cross_asset_relevance`
- `persistence_potential`
- `confidence`
- `why_now`
- `transmission_seed`
- `decay_risk`

#### 2. `Transmission Chain`

定义：对高分 `Shock Candidate` 生成的一条轻量结构化传导假设。

它不是全局知识图谱，而是一条可增量修正的研究链，建议包含：

- `origin_shock`
- `transmission_nodes`
- `affected_assets`
- `directional_impacts`
- `watchpoints`
- `scenario_notes`
- `confidence`
- `status`

推荐统一成五段结构：

1. `Origin Shock`
2. `Transmission Nodes`
3. `Asset Impact Hypothesis`
4. `Watchpoints`
5. `Chain Confidence + Status`

#### 3. `Chain Thread`

定义：跨天跟踪同一条宏观主线的容器，用来聚合相关 shock 和 transmission updates。

建议字段：

- `thread_title`
- `core_hypothesis`
- `current_status`
- `priority_score`
- `days_active`
- `supporting_shocks`
- `latest_updates`
- `affected_assets`
- `key_watchpoints`
- `what_changed_today`
- `regime_tags`

`Chain Thread` 是本设计中最关键的对象，因为它解决的是“研究主线承载层缺失”的问题。

### 二、评分框架

#### 1. `Shock Score`

目标：判断一个 `event` 是否值得升级为研究主线候选。

建议由以下六个维度组成：

1. `asset_impact_strength`
2. `surprise_to_consensus`
3. `cross_asset_breadth`
4. `persistence_potential`
5. `credibility_and_evidence_density`
6. `regime_relevance`

权重上必须明确偏向前两项，尤其是 `asset_impact_strength`。这一步的目标不是选“新闻大”，而是选“定价大”。

#### 2. `Thread Priority Score`

目标：判断哪条主线值得被持续追踪并进入报告主骨架。

建议维度：

- `recent_reinforcement`
- `new_confirming_evidence`
- `market_sensitivity_now`
- `linkage_clarity`
- `cross_asset_importance`
- `remaining_uncertainty`
- `already_priced_risk`

这项分数要让系统偏向“正在持续塑造定价的主线”，而不是只偏爱新近 headline。

### 三、评分实现原则

不建议把 `Shock Score` 做成单一 LLM 直觉分。更稳的组合方式是：

`feature extraction -> structured judgment -> weighted score`

其中：

- 规则/统计层负责提取基础特征，如 source tier、跨源验证数、涉及资产数、时间窗口信息
- LLM 负责输出结构化判断，如 `why_now`、`consensus_surprise`、`transmission_seed`
- 程序化组合层负责生成最终分数并保留各维度拆解结果

这样能确保每次误判都可回放、可解释、可调权重。

### 四、模块演进路径

不建议新建平行主链路。推荐在现有架构中插入研究层：

`event building -> event ranking -> shock candidate detection -> transmission chain generation -> thread tracking -> report context`

具体模块建议如下：

- 复用现有 `event_builder`、`event_enrichment`、`event_repository`
- 新增 `src/services/shock_candidate_detector.py`
- 新增 `src/services/transmission_chain_builder.py`
- 新增 `src/services/chain_thread_tracker.py`
- 新增 `src/services/thread_query_service.py`
- 改造 `src/services/report_context_builder.py` 使其优先消费 `thread`

#### `shock_candidate_detector`

职责：

- 读取已排序事件和证据
- 判断是否入选 `Shock Candidate`
- 计算 `Shock Score`
- 生成最初的 `why_now` 和 `transmission_seed`

#### `transmission_chain_builder`

职责：

- 仅对高分 shock 运行
- 生成轻量结构化传导链
- 补充中间节点、资产影响和关键观察点

#### `chain_thread_tracker`

职责：

- 将新 shock 与历史 chain 做跨日匹配
- 决定 `new_thread`、`reinforce_existing_thread`、`contested`、`reversing`
- 更新 thread 状态、优先级和“今日变化”

#### `thread_query_service`

职责：

- 给研报层和评估层提供“当前最值得跟踪的主线”
- 按资产、主题、状态和时间窗查询 threads

### 五、Thread 生命周期

建议 thread 只保留少量清晰状态：

- `forming`
- `reinforcing`
- `contested`
- `fading`
- `reversing`
- `closed`

状态设计目标是让系统能表达“主线如何变化”，而不是每天重写一份新的解释。

### 六、归并逻辑

新的 shock 进入研究层后，先判断它是否属于既有 thread。判断依据建议至少覆盖：

- 冲击源是否同类
- 关键传导节点是否高度重合
- 核心受影响资产是否一致
- 时间窗口是否连续
- 当前市场 regime 是否相近

只有在无法归入现有 thread 时，才创建 `new_thread`。否则应视为对既有主线的强化、争议或反转更新。

### 七、对报告层的影响

研报主骨架应从“Top Events”转向“Top Threads”，建议组织为：

1. `Top Macro Threads`
2. 每条 thread 的 `what_changed_today`
3. `Asset Impact Hypothesis`
4. `Key Watchpoints`
5. 其次再列 supporting events

这意味着事件开始服务主线，而不是主线被事件清单淹没。

### 八、错误处理与回退

- `Shock Candidate` 结构化判断失败时，应保留 event 层可用性，不得阻断主链路
- `Transmission Chain` 生成失败时，报告层可以回退到“高分 shock + why_now + watchpoints”的简化结构
- `Chain Thread` 匹配失败时，允许短期内创建孤立 thread，但必须记录原因
- 任何研究层失败都不应导致现有 event-centric 报告完全不可用

## 可观测性

建议新增以下指标或运行摘要：

- 进入 shock 评估的事件数量
- 最终成为 shock candidate 的事件数量和占比
- 各 shock score 维度分布
- 每日新建 thread 数、强化 thread 数、关闭 thread 数
- 报告引用的 top threads 与 supporting events 关系
- 研究层输出来自模型原生判断还是回退逻辑

这些指标的目标不是看“模型调没调通”，而是观察研究层是否真的在抬主线，而不是继续生产碎片摘要。

## 测试计划

- 为 `shock_candidate_detector` 增加基于 fixture 的打分测试
- 增加“新闻热但定价弱”和“新闻不热但定价强”的对照用例
- 为 `transmission_chain_builder` 增加结构完整性和字段归一化测试
- 为 `chain_thread_tracker` 增加跨天归并、强化、争议、反转状态迁移测试
- 为 `report_context_builder` 增加 thread-first 输出测试
- 增加一组离线评估，检查 top threads 是否比 top events 更贴近人工定义的研究主线

## 成功标准

- 系统能稳定从事件层中抬出少量高价值 `Shock Candidate`
- 研报开始以 `thread` 而不是单日事件列表组织主骨架
- 同一条宏观主线能跨天维持、更新和降权，而不是每天重新生成相似结论
- 对 `美股 / 美元 / 美债 / 黄金 / 原油` 的研究输出更聚焦未来 `1-4 周` 定价冲击
- 当系统误判时，可以清楚回放是起点识别错误、传导链错误，还是 thread 归并错误

## 分阶段落地建议

### 阶段一：Shock 层

先做 `shock_candidate_detector` 与 `Shock Score`，把“什么事件值得进入研究主线”定义清楚。

### 阶段二：Chain 层

对高分 shock 生成轻量 `Transmission Chain`，让系统开始输出结构化传导假设。

### 阶段三：Thread 层

完成跨天主线追踪和状态迁移，让报告主骨架从 `events` 迁移到 `threads`。

### 阶段四：质量闭环

把 `Shock / Chain / Thread` 的误判回放、评估标签和反馈回灌到排序与权重调优中。

## 备注

- 本文档记录了本轮 brainstorming 收束后的设计结果
- 当前会话中没有可用的 `spec-document-reviewer` 子代理，因此未执行技能要求中的自动 review loop；本轮采用人工自审作为替代
- 当前会话中也没有可用的 `writing-plans` 技能入口，因此本轮只停在 spec 阶段
