# 研报质量差根因深度分析（当前代码校正版）

**分析日期**: 2026-03-14  
**触发场景**: `uv run -m src.run_report --report-only --force`  
**校正依据**:
- 当前代码实现：`src/services/*`
- 运行日志：`logs/deepcurrents.log` 中 2026-03-14 01:40 一次完整 report run
- 最终输出：`test.txt`

---

## 一、校正说明

这份文档用于替换旧版分析中已经过期的代码判断。当前代码下，以下 3 点需要明确纠正：

1. **`rank_events` 不再是“只取最近 100 条、按时间倒排”**
   - 当前 `EventRanker.rank_events()` 默认 `candidate_pool_size=500`
   - 当前 `EventRepository.list_recent_events()` 已按 `article_count DESC, source_count DESC, latest_article_at DESC` 排序

2. **`EventBuilder` 默认合并阈值不是旧版写的 `0.58 / 0.75`**
   - 当前代码默认值为 `merge_score_threshold=0.45`
   - 当前代码默认值为 `semantic_score_threshold=0.60`

3. **`MarketStrategist` 原始输出日志已经写进代码，但实际上没有打出来**
   - 代码里有 raw output log
   - 但项目使用 loguru，当前写法仍沿用 `%s` 占位符，日志文件里只会落字面量 `%s`
   - 结果是“看起来加了日志”，实际仍然看不到模型原始输出

---

## 二、当前代码下的真实问题链路

```text
[数据采集层]   collector 提供 RSS 摘要级正文
      ↓
[标准化层]     ArticleNormalizer 只清洗 content/summary/description/body，不抓全文
      ↓
[事件聚类层]   EventBuilder 默认阈值已下调，但短文本 + 异构标题仍导致大量单文章事件
      ↓
[候选池层]     当前代码已按 article_count/source_count 优先，不是旧版“最近100条”问题
               但 2026-03-14 01:40 运行中 ranking 只考虑到 12 个事件，且 single_source_event_ratio=1.0
      ↓
[摘要层]       EventSummarizer 仍是 rule_template_v1，brief 天花板很低
      ↓
[上下文组装]   ReportContextBuilder 同时受 brief 过短 + quota policy 限制，budget_utilization=19.5%
      ↓
[AI 生成层]    MarketStrategist(kimi-k2.5) 调用成功，但输出被判定为 sparse
      ↓
[观测层缺口]   raw output 日志占位符写法错误，当前无法直接看到模型真实输出
      ↓
[兜底层]       normalize 默认值 + sparse fallback 二次模板化
      ↓
[最终输出]     test.txt 主要是 brief/theme fallback 拼接，不是 AI 深度研判
```

---

## 三、逐层分析

### 3.1 数据采集与标准化层：正文短仍是首要根因

`ArticleNormalizer.normalize()` 当前只会从以下字段取正文并清洗：

```python
raw.get("content")
or raw.get("summary")
or raw.get("description")
or raw.get("body")
```

这意味着如果采集器只拿到 RSS 摘要，标准化层不会补抓原文全文，系统后续只能处理短文本。

**结论**：
- 旧版“正文严重缺失”这个方向仍然成立
- 但它的代码根因应表述为：**系统当前没有在标准化链路中补全文抓取能力**
- 所以这不是 normalizer 写坏了，而是 ingestion 输入本身就不足

**补充说明**：
- 旧版文档中的文章长度分布、中位数 93 字符等统计，可以继续作为“历史样本现象”参考
- 但这些数字本次没有重新复跑，属于数据侧证据，不是本次代码校正的直接产物

---

### 3.2 事件聚类层：问题依然存在，但“阈值过严”已不是当前代码事实

当前 `EventBuilder` 默认值：

```python
merge_score_threshold = 0.45
semantic_score_threshold = 0.60
```

也就是说，旧版文档里“阈值偏严：0.58 / 0.75”的表述已经过期。

**当前更准确的判断**：
- 阈值已经比旧版分析时更宽松
- 事件仍然碎片化，说明主要矛盾不只是阈值
- 更可能的主因是：
  - 文章正文太短，标题/语义相似度缺少信息
  - 不同 RSS 源对同一事件表述差异大
  - 单篇摘要文本不足以支撑稳定合并

所以这里的根因应从“阈值太严”修正为：**短文本输入导致聚类信号不足，阈值只是次要调节项**。

---

### 3.3 候选池与排序层：旧版“最近 100 条截断”结论已过期

当前代码路径是：

```text
EventRanker.rank_events(limit=12, candidate_pool_size=500)
  -> EventQueryService.list_events(limit=500)
  -> EventRepository.list_recent_events(
       ORDER BY article_count DESC, source_count DESC, latest_article_at DESC
     )
```

这和旧版文档里的：

```text
list_events(limit=100)
-> list_recent_events(ORDER BY latest_article_at DESC LIMIT 100)
```

已经不是同一套逻辑。

**当前运行事实**：
- 2026-03-14 01:40 的 ranking 日志显示：
  - `events_considered = 12`
  - `events_ranked = 12`
  - `single_source_event_ratio = 1.0`

**这说明什么**：
- 至少在这次真实 report run 中，问题不再能归因于“2088 条事件被时间截断到 100 条”
- 当前更真实的问题是：**进入 report 路径的候选事件集合本身质量就偏低，而且全是单信源事件**

**因此本层结论应改写为**：
- 当前代码已经部分修复了旧版候选池排序问题
- 但当前 run 仍然只有低质量、低佐证度事件进入 ranking
- 这更像是数据质量 / 聚类质量 / 过滤结果的问题，而不是排序 SQL 仍按时间硬截断

---

### 3.4 Enrichment 层：不是“完全为空”，而是“类型失真导致 regions/assets 常为空”

旧版文档把 enrichment 总结为“regions/entities/assets 全空”，这个说法对当前代码来说过于绝对。

当前代码里：
- `ArticleFeatureExtractor` 会抽取很多 `type="phrase"` 或 `type="ticker"` 的实体
- `EventEnrichmentService._extract_entities()` 会把这些实体保留下来
- 但 `EventEnrichmentService._extract_regions()` 和 `_extract_assets()` 只会接纳特定类型的实体

这会导致一个更常见的真实情况：

1. `entities` 可能并非完全空
2. 但很多实体只是泛化的 `phrase`
3. `regions` / `assets` 因为类型不匹配仍然经常为空

**因此当前更准确的表述**：
- enrichment 的核心问题不是“所有结构化字段都没有”
- 而是**实体类型质量太差，无法稳定沉淀成 region / asset 级别的高价值结构化信息**

这也解释了为什么 report 中经常看到：
- `regions=[]`
- `assets=[]`
- `market_channels` 偶尔还能命中，因为它主要靠关键词规则

---

### 3.5 评分层：同质化症状仍然存在

虽然旧版文档中逐维度常量值没有在本次校正中逐条复算，但当前日志仍然显示出明显的同质化症状：

- `single_source_event_ratio = 1.0`
- `avg_supporting_evidence_count = 1.0`
- `avg_evidence_ref_count = 1.0`
- `avg_confidence = 0.509`

这说明当前被选中的事件仍然以单文章、单信源为主，ranking 和 brief 层可区分的信息很少。

**当前层面的有效结论**：
- 评分退化问题仍然存在
- 但根因不应再表述为单一参数问题
- 更接近于：**候选事件本身缺少多信源、多文章、多视角证据，导致评分维度无法拉开**

---

### 3.6 Event Brief 层：模板化是当前代码的明确事实

这一层旧版结论完全成立，而且能直接从代码确认：

- `EventSummarizer` 默认 `model="rule_template_v1"`
- `whyItMatters` 是固定句式拼接

核心模板如下：

```python
return (
    f"This {event_type} matters for {channels_text} "
    f"because it is {state_change} and currently ranks on {driver_text}, "
    f"with confidence {confidence:.2f}{contradiction_text}."
)
```

因此：
- 只要上游 enrichment 稀薄、evidence 只有 1 条
- brief 基本一定会高度同质化

`test.txt` 当前输出也印证了这一点，核心摘要几乎就是 brief 模板和 theme fallback 的再包装。

---

### 3.7 上下文组装层：低预算利用率是“短内容 + quota policy”共同结果

2026-03-14 01:40 日志显示：

| 指标 | 值 |
|------|----|
| token_budget | 7,952 |
| budget_utilization | 19.5% |
| events_selected | 8 |
| themes_selected | 3 |

旧版文档只强调“brief 太短，所以浪费预算”，这个方向没错，但还少了一半原因。

当前 `macro_daily` 的 quota policy 还包括：
- `max_events_per_theme = 2`
- `max_events_per_region = 2`

因此 12 条 brief 最后只选 8 条，不只是因为 token 不够，而是**主题/区域覆盖约束主动丢掉了一部分事件**。

**当前更准确的结论**：
- 预算利用率低，的确说明输入太短
- 但 `12 -> 8` 这个结果同时是 quota policy 的设计结果，不是单纯的 token 浪费

---

### 3.8 AI 生成层：当前主问题是“输出稀疏 + 无法观测原始输出”

当前 2026-03-14 01:40 的真实日志序列是：

1. `MarketStrategist 调用成功 (Model: kimi-k2.5)`
2. 紧接着触发 `MarketStrategist output sparse`

这说明当前 run 的主症状是：
- **调用成功**
- **但结果被判定为稀疏**

需要注意的是，旧版文档中“JSON 解析失败、自动修复”属于历史现象，当前这次 run 的主问题并不是 parse failure，而是 sparse fallback。

更关键的是，raw output 虽然在代码里尝试记录：

```python
logger.info(
    "MarketStrategist raw output (first 800 chars): %s",
    (final_raw or "")[:800],
)
```

但项目使用的是 loguru，这种 `%s` 写法不会插值，所以日志里实际落的是字面量 `%s`。  
也就是说，**当前我们仍然无法直接看到模型原始输出到底是什么**。

因此这一层最准确的判断是：

- 不能武断地下结论说 kimi-k2.5 返回了“空 JSON”
- 当前能确认的只有：它的输出被 downstream 判成了 sparse
- 真正的 raw response 还没有被有效观测到

---

### 3.9 兜底层：双层模板闭环仍然成立

这一层旧版结论仍然成立。

当前闭环如下：

1. `normalize_daily_report_payload()` 在缺字段时填默认摘要
2. `_is_sparse_text()` 把默认摘要识别为稀疏文本
3. `ReportOrchestrator` 再用 event/theme brief 拼 fallback

于是最终输出会变成：

```text
模型稀疏输出
-> normalize 默认值
-> sparse 判定命中
-> fallback 二次模板化
-> test.txt 看起来像“AI 写了一篇模板文”
```

这解释了为什么最终成品读起来不像失败报错，而像“结构完整但信息密度很低的模板文案”。

---

## 四、当前优先级排序

| 优先级 | 根因 | 当前判断 |
|--------|------|---------|
| **P0** | 上游正文仍以 RSS 摘要为主，缺少全文抓取 | 这是全链路上限问题 |
| **P0** | Event brief 仍是 `rule_template_v1`，信息密度先天不足 | 当前输出模板化的直接来源 |
| **P0** | MarketStrategist raw output 观测链路失效 | 现在甚至看不到模型真实返回了什么 |
| **P1** | 候选事件集合仍以单信源、低佐证事件为主 | 当前 ranking/brief 同质化的直接原因 |
| **P1** | kimi-k2.5 在当前提示和输入质量下输出偏 sparse | 需要和 gpt-4o 做同输入对比 |
| **P2** | enrichment 的实体类型失真，regions/assets 提取弱 | 会持续拉低 brief 质量 |
| **P2** | 事件合并质量仍不足 | 但不应再简单归因到旧版阈值参数 |
| **P2** | context quota policy 限制了事件覆盖率 | 属于质量放大器，不是最初根因 |

---

## 五、改进建议

### P0：先修观测与输入上限

1. **修正 MarketStrategist raw output 日志**
   - 现状不是“没写日志”，而是“写了但格式错了”
   - 应改成 loguru 可用的写法，例如 f-string 或 `{}` 风格
   - 在修好之前，不要继续对模型行为做强判断

2. **补做同输入模型对比**
   - 用同一份 `strategist_input`
   - 分别跑 `kimi-k2.5` 与 `gpt-4o`
   - 比较 raw output、parsed JSON、fallback 命中情况

3. **优先补全文抓取能力**
   - 当前 normalizer 不会抓原文
   - 如果 collector 只能拿到摘要，后续再怎么调 prompt 都救不回来

### P1：修复 event brief 的信息上限

4. **不要再把“排序只取最近 100 条”当作当前主根因**
   - 这条是旧版代码结论
   - 现在应该改查“当前候选池为什么仍然全是单信源事件”

5. **对 brief 层引入 LLM 或混合摘要**
   - 当前 `rule_template_v1` 只适合占位，不适合承载 report 主输入
   - 即便先不全量替换，也应该先对 top events 做 richer summarization

6. **改进实体类型质量**
   - 当前 `phrase` 太多
   - 需要更稳定地映射到 location / asset / organization 等高价值类型

### P2：继续收敛聚类与上下文策略

7. **重新评估事件合并，而不是沿用旧版阈值结论**
   - 当前默认阈值已是 `0.45 / 0.60`
   - 下一步应基于真实样本评估 merge miss case，而不是继续盲调

8. **按目标决定是否放宽 context quota**
   - 如果目标是“覆盖更多事件”，可以调整 `max_events_per_theme`
   - 但这只能放大已有质量，不能替代上游输入修复

---

## 六、快速验证步骤

### 步骤 1：先修日志，再重跑一次 report

目标：拿到 `MarketStrategist` 的真实 raw output，而不是日志里的 `%s`。

---

### 步骤 2：核对当前候选池，不再沿用旧版 2088/100 假设

建议直接查当前事件池：

```sql
SELECT
  COUNT(*) AS total_events,
  COUNT(*) FILTER (WHERE status IN ('new','active','updated','escalating','stabilizing','resolved')) AS eligible_events,
  COUNT(*) FILTER (WHERE article_count = 1) AS single_article_events,
  COUNT(*) FILTER (WHERE source_count = 1) AS single_source_events
FROM events;
```

再看 report 候选的头部质量：

```sql
SELECT event_id, canonical_title, article_count, source_count, latest_article_at
FROM events
WHERE status IN ('new','active','updated','escalating','stabilizing','resolved')
ORDER BY article_count DESC, source_count DESC, latest_article_at DESC
LIMIT 20;
```

---

### 步骤 3：对比同一份 strategist_input 的双模型输出

目标：
- 判断问题主要来自 `kimi-k2.5`
- 还是来自 brief/context 本身太弱

如果 `gpt-4o` 同输入也只能产出稀疏内容，说明主要矛盾仍在输入质量。  
如果 `gpt-4o` 明显更稳定，则说明模型选择和 JSON 遵循能力是实质因素。

---

## 七、结论

当前代码下，最准确的一句话总结不是：

> “排序只取最近 100 条，所以高价值事件全被漏掉了。”

而是：

> **旧版排序问题已经被部分修正，但当前进入 report 的事件本身仍然稀薄；再叠加 rule-template brief、失效的 raw 日志观测和 normalize/fallback 双层模板化，最终产出了看起来完整、实则信息密度很低的研报。**
