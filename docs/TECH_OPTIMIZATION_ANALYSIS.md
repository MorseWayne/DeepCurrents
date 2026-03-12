# DeepCurrents (深流) 技术优化分析与演进建议

**版本**: v1.0  
**状态**: 分析文档 / 待实施  
**范围**: Python 主链路 `src/`  
**基线日期**: 2026-03-12

---

## 1. 文档目的

本文档用于固化当前 DeepCurrents 项目的核心技术分析结论，并结合成熟开源项目与常见算法方案，给出后续技术优化方向、优先级与落地顺序。

本文聚焦三类问题：

1. 当前系统的核心技术与能力边界是什么。
2. 当前实现的主要瓶颈在哪里。
3. 哪些开源技术和算法最值得引入，投入产出比最高。

---

## 2. 当前项目的核心技术栈

### 2.1 业务主链路

当前项目已经形成完整闭环：

`多源 RSS/RSSHub 采集 -> 标题级去重 -> 规则分类 -> 事件聚类 -> 多 Agent LLM 生成研报 -> 预测落库 -> 简单评分`

主编排位于 `src/engine.py`，主要流程为：

1. 拉取未报告新闻
2. 执行 threat classification
3. 执行事件聚类
4. 调用多 Agent 生成结构化日报
5. 推送到通知通道
6. 标记新闻为已报告

对应实现见：

- `src/engine.py`
- `src/services/collector.py`
- `src/services/db_service.py`
- `src/services/classifier.py`
- `src/services/clustering.py`
- `src/services/ai_service.py`
- `src/services/scorer.py`

### 2.2 采集层

采集层主要技术：

- `aiohttp`
- `feedparser`
- `asyncio.Semaphore`
- `RSSCircuitBreaker`

当前特征：

- 支持 70+ 信息源并发抓取
- 按 `tier` 优先级排序抓取
- 支持 RSSHub URL 重写
- 对高优先级源尝试正文提取
- 有源级熔断和冷却机制

优点：

- I/O 设计正确，适合高并发 RSS 拉取
- 采集链路足够轻，维护成本低
- 具备生产化基础能力

### 2.3 存储与去重层

存储层主要技术：

- `SQLite`
- `aiosqlite`
- URL 唯一约束
- 标题归一化
- `Jaccard`
- `trigram Dice`
- 倒排词索引

当前去重属于“规则模糊去重”，特点是：

- 成本低
- 可解释
- 对近似重复标题有效
- 对跨语言表达、改写标题、语义同事件能力有限

### 2.4 分类与聚类层

分类层：

- 基于关键词规则
- 支持 `critical/high/medium/low/info`
- 带简单地缘升级规则

聚类层：

- 先分词
- 再做标题 token 的 Jaccard 相似度
- 使用并查集合并 cluster

这一套逻辑的优点是简单、稳定、易调试；缺点是仍然停留在“词面相似”层面。

### 2.5 AI 生成层

AI 生成层主要技术：

- OpenAI 兼容接口
- `Pydantic` 输出结构定义
- 多 Agent 并行调用
- 主备模型回退
- JSON 修复重试

当前 Agent 结构：

- `MacroAnalyst`
- `SentimentAnalyst`
- `MarketStrategist`

这是一个合理的 v1 多 Agent 结构，已经比单次大 prompt 汇总更清晰。

### 2.6 预测与评分层

预测层当前做的事：

- 从日报中的 `investmentTrends` 自动抽取预测
- 自动解析 symbol
- 落库到 `predictions`

评分层当前做的事：

- 拉当前价格
- 与基准价比较
- 根据方向给启发式评分

这说明项目已经具备“研究闭环”的雏形，但目前评分维度还比较浅。

---

## 3. 当前架构的优势判断

从工程角度看，本项目目前最强的地方不是“算法先进性”，而是“闭环完整性”：

1. 采集、分析、生成、分发、回测已经串起来了。
2. 异步 I/O、熔断、主备回退这类工程要素已经具备。
3. 使用 Python 重构后，技术路线明显比保留的 `src_ts/` 更适合后续数据与 AI 扩展。
4. 代码分层比较清晰，后续替换模块成本可控。

简单说，当前项目是一个很好的“可持续演进底座”。

---

## 4. 当前最主要的技术短板

### 4.1 threat 分类没有前移到入库阶段

目前 threat classification 发生在生成报告之前，而不是采集入库时。

这导致两个问题：

1. 数据库里已有 `threat_level` 字段，但大多数记录在入库时并未真正写入有效 threat 信息。
2. 后续按 threat 排序、筛选、统计的价值没有充分发挥。

影响：

- 报告上下文排序精度下降
- 历史统计价值变弱
- 无法稳定做基于 threat 的回溯分析

### 4.2 去重与聚类仍是标题词面级方案

当前方案对这些情况效果有限：

- 同一事件的不同媒体改写
- 中英双语互译标题
- 标题极短但正文高度相似
- 同一事件的后续进展与首发报道关联

这会造成：

- 重复新闻仍混入上下文
- cluster 粒度不稳定
- LLM 在聚合同一事件时浪费 token

### 4.3 聚类复杂度偏高

当前聚类对 `n` 条新闻做两两比较，复杂度接近 `O(n^2)`。

在当前默认规模下问题不大，但如果未来扩到：

- 更多信源
- 更长保留窗口
- 更高频采集

则成本会快速上升。

### 4.4 正文抽取器偏简陋

当前正文抽取逻辑主要是：

- 拉 HTML
- `BeautifulSoup` 清理标签
- 抽取 `<p>` 文本
- 不足时回退到整个 body 文本

这套逻辑能跑，但会出现：

- 正文噪声大
- 导航栏、版权说明混入
- 某些动态网页提取失败
- 中英文媒体兼容性不稳定

### 4.5 Agent 编排仍偏“手工 prompt orchestration”

当前多 Agent 管理方式主要是：

- 手工拼 prompt
- 手工串接 JSON
- 手工做解析和修复

短期可用，但随着 Agent 增加，会带来：

- 调试成本升高
- 错误边界不清晰
- provider 差异兼容成本升高
- 难做细粒度 tracing

### 4.6 预测数据结构过薄

当前 `predictions` 主要只保留：

- symbol
- direction
- reasoning
- base_price
- timestamp

缺失关键研究字段：

- horizon
- target
- stop / invalidation 条件
- confidence
- linked event / linked report

因此评分只能做简单方向判断，无法形成真正可比较的研究评估体系。

### 4.7 信源元数据尚未进入主排序逻辑

当前 `sources.py` 中已经有很有价值的字段：

- `tier`
- `type`
- `propaganda_risk`
- `state_affiliated`

但现阶段主要真正参与主流程的是 `tier`，其他字段尚未系统进入：

- 可信度估计
- 事件证据加权
- 报告 source analysis
- 风险标签

这意味着项目已经有“信源画像”的基础，但没有完全变成算法能力。

---

## 5. 开源项目与算法参考

下面列的是最值得参考的一批项目，不是为了整套照搬，而是为了提取适合 DeepCurrents 的能力模块。

### 5.1 RSS 与抓取侧

#### RSSHub

用途：

- 统一抓取 Telegram、中文站点、X/Twitter 等非标准 RSS 来源

价值：

- 当前项目已经深度依赖 RSSHub，是采集层的重要外部基础设施

参考：

- https://docs.rsshub.app/

#### trafilatura

用途：

- 高质量正文抽取

适合本项目的原因：

- 比当前 `BeautifulSoup + p` 的方案更稳
- 接入成本低
- 适合作为高优先级媒体正文增强的默认方案

参考：

- https://trafilatura.readthedocs.io/

#### news-please

用途：

- 新闻抓取、正文、发布时间、作者等元数据提取

适合场景：

- 如果后续需要更强的新闻文章结构化抽取，可作为增强方案

参考：

- https://github.com/fhamborg/news-please

### 5.2 去重、相似度与聚类

#### Sentence Transformers

用途：

- 句向量
- paraphrase mining
- 语义相似度
- 轻量聚类

适合本项目的原因：

- 非常适合“标题/摘要语义去重”
- 可以作为当前规则去重的第二层
- 接入门槛低于自己训练模型

参考：

- https://www.sbert.net/examples/applications/paraphrase-mining/README.html
- https://www.sbert.net/examples/applications/clustering/README.html

#### BERTopic

用途：

- embedding + 聚类 + topic representation

适合本项目的原因：

- 更适合做“日报主题发现”“中期趋势漂移”“每周主题归纳”
- 不一定适合直接替换在线事件聚类，但适合作为离线分析模块

参考：

- https://github.com/MaartenGr/BERTopic

### 5.3 向量检索与历史事件召回

#### Qdrant

用途：

- 向量存储
- 相似事件召回
- 历史案例检索

适合本项目的原因：

- 后续可以从“只分析当天新闻”升级到“引入历史类比事件”
- 对日报质量提升非常明显

参考：

- https://qdrant.tech/documentation/

### 5.4 Agent 编排与结构化输出

#### PydanticAI

用途：

- 类型化 agent 输出
- 更稳定的结构化结果约束

适合本项目的原因：

- 当前项目已经使用 `Pydantic`
- 比继续手工维护 JSON 修复链更适合长期演进

参考：

- https://ai.pydantic.dev/

#### LiteLLM

用途：

- 多模型 provider 统一封装
- 路由、回退、兼容层

适合本项目的原因：

- 当前项目已有主备 provider 回退需求
- 接入 LiteLLM 后可减少 provider 兼容代码

参考：

- https://docs.litellm.ai/

#### LangGraph

用途：

- 复杂多 Agent 状态图编排

适合场景：

- 只有当 Agent 数量和流程复杂度明显上升时才值得引入
- 当前阶段不建议立即全量迁移

参考：

- https://github.com/langchain-ai/langgraph

### 5.5 金融研究与评估参考

#### ai-hedge-fund

用途：

- 多角色金融 Agent 协作
- 研究任务拆分

适合本项目的原因：

- 可借鉴 agent role design
- 可借鉴研究评估闭环

不建议整套照搬的原因：

- 该项目不是为“多源情报聚合”设计的
- DeepCurrents 的核心优势仍在采集和事件抽取

参考：

- https://github.com/virattt/ai-hedge-fund

#### FinGPT

用途：

- 金融领域任务模板
- 金融情绪分析与 benchmark

适合本项目的原因：

- 可增强市场解释、资产趋势判断、金融任务评估

参考：

- https://github.com/AI4Finance-Foundation/FinGPT

#### backtesting.py

用途：

- 轻量回测框架

适合本项目的原因：

- 未来如果将 `investmentTrends` 逐步结构化为可执行观点，可用于更正式的回测

参考：

- https://github.com/kernc/backtesting.py

### 5.6 事件与全球新闻外部基线

#### GDELT

用途：

- 全球事件数据
- 地理、情绪、关注度等结构化信号

适合本项目的原因：

- 可作为外部覆盖率校准
- 可作为事件重要度与地理影响因子的补充

参考：

- https://blog.gdeltproject.org/doc-geo-2-0-api-updates-full-year-searching-and-more/

---

## 6. 技术优化方向

以下建议按“性价比”和“演进顺序”组织。

### 6.1 P0: 低风险高收益优化

这些项应优先做，原因是改动小、收益直接、不会破坏现有闭环。

#### 方向 A: threat classification 前移

建议：

- 在采集入库时直接完成初始 threat classification
- 将结果写入 `raw_news`
- 报告阶段只做补充修正，不再从零计算

收益：

- 数据层可按 threat 稳定排序
- 历史查询、统计、回溯能力增强
- 为后续事件打分和 source credibility 建模打基础

#### 方向 B: 替换正文抽取器

建议：

- 高优源默认使用 `trafilatura`
- 失败后回退到当前 `BeautifulSoup` 逻辑

收益：

- 提升正文质量
- 降低噪声
- 改善后续分类、聚类、LLM 理解效果

#### 方向 C: source credibility 评分进入主流程

建议：

- 基于 `tier + propaganda_risk + state_affiliated + source_count`
 计算一个统一 `evidence_score`
- 用于 cluster 排序、日报上下文排序、最终 sourceAnalysis

收益：

- 信源模型从“配置元信息”变成“可计算特征”
- 更适合做机构化情报报告

#### 方向 D: prediction schema 扩展

建议新增字段：

- `time_horizon`
- `confidence`
- `target_price` 或 `target_condition`
- `linked_report_date`
- `linked_cluster_id`

收益：

- 后续评分模型不再局限于方向涨跌

### 6.2 P1: 语义层升级

这些项是中期最值得投入的方向。

#### 方向 E: 二级语义去重

建议架构：

1. URL 去重
2. 标题规则去重
3. embedding 语义近邻去重

建议技术：

- `sentence-transformers`
- 本地 embedding 缓存

收益：

- 大幅减少同事件重复报道进入上下文
- 提高 token 利用效率

#### 方向 F: 事件聚类升级为语义图聚类

建议架构：

1. 计算标题或标题+摘要 embedding
2. 构建近邻图
3. 按相似边合并 cluster

可选策略：

- KNN graph + union-find
- community clustering
- 小规模 DBSCAN / HDBSCAN

收益：

- 更稳地合并跨语言和改写标题
- 减少当前 `O(n^2)` 直接两两比较的成本

#### 方向 G: 历史事件相似召回

建议：

- 对历史 cluster 建 embedding
- 报告生成前召回相似历史事件
- 将“过去类似事件 + 后续市场表现”作为 strategist 输入

建议技术：

- 小规模先本地缓存
- 中规模以后上 `Qdrant`

收益：

- 报告质量从“当天汇总”升级到“带历史类比的研究结论”

### 6.3 P2: 研究与平台层升级

这些项适合在 P0/P1 完成后推进。

#### 方向 H: 引入结构化事件抽取层

建议：

- 在聚类后增加 `event normalization`
- 输出统一事件对象，例如：
  - `who`
  - `action`
  - `target`
  - `where`
  - `when`
  - `confidence`
  - `sources`

收益：

- LLM 输入从“新闻堆”变成“事件对象列表”
- 输出更稳
- 更容易做回测和知识库建设

#### 方向 I: Agent 编排类型化

建议：

- 若保持轻量，优先引入 `PydanticAI`
- 若 provider 兼容诉求很强，可引入 `LiteLLM`
- 仅在 Agent 数量大幅增加后再考虑 `LangGraph`

收益：

- 降低手工 JSON 修复成本
- 提高多 provider 兼容性
- 更易测试和监控

#### 方向 J: 评分模型升级为研究评估体系

建议从以下维度评分：

- directional accuracy
- excess return
- horizon hit rate
- calibration
- conviction-weighted score

收益：

- 真正形成“研究质量评分”
- 可以比较 agent、prompt、source mix 的长期表现

#### 方向 K: 接入外部事件基线

建议：

- 接入 GDELT 作为覆盖校验与辅助特征来源

收益：

- 提升全球事件覆盖稳定性
- 可降低 RSS 偶发缺失带来的盲区

---

## 7. 推荐实施顺序

### Phase 1: 立即可做

建议 1-2 周内完成：

1. threat classification 前移入库
2. `trafilatura` 替换正文抽取
3. source credibility 评分进入主排序逻辑
4. 扩展 `predictions` 表结构

目标：

- 提升数据质量
- 提升报告输入质量
- 为下一阶段语义能力打基础

### Phase 2: 语义增强

建议 2-4 周内完成：

1. 引入 `sentence-transformers`
2. 做二级语义去重
3. 做语义聚类
4. 为历史事件建立 embedding 缓存

目标：

- 提升事件聚合精度
- 提升 token 使用效率
- 降低重复上下文噪声

### Phase 3: 平台化与研究化

建议后续逐步推进：

1. 结构化事件对象层
2. Agent 类型化编排
3. 历史相似事件召回
4. 研究评估与回测升级

目标：

- 从“日报引擎”演进到“宏观情报研究平台”

---

## 8. 如果只优先做三件事

如果资源有限，建议只优先做以下三项：

1. `trafilatura` 替换正文抽取
2. `sentence-transformers` 做二级语义去重
3. 重构 `predictions + scorer`，建立更真实的评估闭环

理由：

- 这三项对最终报告质量和研究价值提升最直接
- 不需要大规模推翻现有架构
- 改造成本与收益比最高

---

## 9. 当前代码证据点

以下文件体现了本文结论的主要依据：

- `src/services/collector.py`
  - 采集、并发、熔断、正文增强
- `src/services/db_service.py`
  - SQLite 模型、标题缓存、模糊去重
- `src/services/classifier.py`
  - 基于关键词的 threat classification
- `src/services/clustering.py`
  - 基于 token Jaccard 的并查集聚类
- `src/services/ai_service.py`
  - 多 Agent、结构化 JSON、模型回退
- `src/services/scorer.py`
  - 当前启发式预测评分
- `src/config/sources.py`
  - 信源画像和可扩展元信息

---

## 10. 总结

DeepCurrents 当前最重要的事实不是“算法还不够先进”，而是：

- 架构闭环已经成立
- 工程基础已经可用
- 具备继续向更强语义层和研究层演进的良好底座

因此，最合理的路线不是推倒重来，而是按以下路径逐步增强：

1. 先补数据质量与结构化能力
2. 再补语义去重、语义聚类与历史召回
3. 最后升级 Agent 编排和研究评估体系

按照这个顺序推进，项目会比较自然地从“自动宏观日报生成器”演进为“AI 驱动的宏观情报研究平台”。

---

*Last aligned with codebase on 2026-03-12. Tests observed locally on 2026-03-12: `uv run pytest -q` -> `28 passed`.*
