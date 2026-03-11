# DeepCurrents (深流) 技术设计文档

**版本**: v2.1  
**状态**: 生产就绪 (Production Ready)  
**定位**: AI 驱动的全球情报聚合与宏观战略研报引擎

---

## 1. 系统概述 (System Overview)

DeepCurrents 是一个高性能的宏观情报系统，旨在从全球 30+ 个顶级资讯源中提取碎片化信息，并通过 AI 推理引擎将其转化为深度的宏观经济与投资策略报告。其核心逻辑在于：**从"新闻浪花"中识别底层的"宏观深流"**。

### 1.1 v2.1 核心改进

| 特性 | v1.0 | v2.1 |
|------|------|------|
| 标题去重 | 精确匹配 | trigram Dice + word Jaccard 模糊去重，倒排索引加速 |
| AI 上下文 | 硬截断 12000 字符 | Token 预算分配（新闻 70% / 聚类 15% / 趋势 15%） |
| 通知推送 | 无重试 | 指数退避重试 + 飞书/Telegram 并行推送 |
| 内存管理 | seenHeadlines 无限增长 | LRU 淘汰，上限可配 |
| 配置管理 | 硬编码 | 集中配置模块，15+ 参数可通过 .env 调整 |
| 进程管理 | 无退出处理 | SIGTERM/SIGINT 优雅关停 |
| 分词 | 仅英文 | Intl.Segmenter 多语言（中/日/韩/英） |
| 部署 | 仅 ts-node | Docker 两阶段构建 |

## 2. 系统架构 (System Architecture)

系统采用模块化设计，分为五个核心层：

### 2.1 数据收集层 (Collector Layer)

* **组件**: `DeepCurrentsEngine` + `rss-parser` + `RSSCircuitBreaker`
* **逻辑**:
  * 通过 `node-cron` 调度，默认每小时运行一次（可配 `CRON_COLLECT`）。
  * 使用 `p-limit` 限制并发抓取（默认 10，可配 `RSS_CONCURRENCY`），保护上游源。
  * **熔断器**: 每个源独立计数连续失败次数，超过阈值（可配 `CB_MAX_FAILURES`）自动进入冷却期，冷却期返回缓存数据。
  * 源按 tier 优先级排序处理，T1（通讯社）优先于 T4（聚合器）。

### 2.2 去重与存储层 (Dedup & Storage Layer)

* **组件**: `DBService` + `better-sqlite3`
* **逻辑**:
  * SQLite WAL 模式持久化。
  * **URL 去重**: Base64(URL) 作为主键，数据库级唯一约束。
  * **模糊标题去重** (v2.1 新增):
    * 标准化标题（去媒体归属、小写、保留 CJK 字符）。
    * 内存缓存近 24h 标题的 trigram 集合和词集合。
    * **倒排词索引**快速定位共享词汇的候选标题。
    * 对候选做 **word Jaccard** + **trigram Dice** 双重检测，任一超阈值即判重。
    * `saveNews()` 实时更新缓存，同一采集周期的后续条目立即参与去重。
  * **分页查询** (v2.1 新增): `getUnreportedNews(limit)` 加 `LIMIT`，防积压时内存溢出。
  * **优先级排序**: 按威胁等级 DESC → 源分级 ASC → 时间 DESC。

### 2.3 分析管线层 (Analysis Pipeline)

* **威胁分类器** (`classifier.ts`):
  * 排除非相关内容 → CRITICAL → HIGH → MEDIUM → LOW → INFO 级联匹配。
  * 复合升级规则: 军事关键词 + 地缘目标 → 自动升级为 CRITICAL。
  * 正则缓存优化，短词强制词边界匹配。

* **新闻聚类** (`clustering.ts`):
  * 多语言分词 → Jaccard 相似度 → 并查集分组。
  * 选最权威源（最低 tier）作为聚类主标题。
  * 聚合威胁评估（最高等级 + 加权平均置信度）。

* **趋势检测** (`trending.ts`):
  * 2 小时滚动窗口计数 vs 7 天基线比对。
  * 实体自动提取（CVE、APT、领导人名字）。
  * 跨源验证（至少 2 个独立源确认）。
  * 冷却期避免重复告警。
  * seenHeadlines Map + LRU 淘汰（上限可配），修复内存泄漏。

### 2.4 智能分析与生成层 (Intelligence Layer)

* **组件**: `AIService`
* **逻辑**:
  * **Token 预算管理** (v2.1 新增):
    * 总预算可配（默认 8000 token，`AI_MAX_CONTEXT_TOKENS`）。
    * 按信息类型分配: 新闻 70%、聚类 15%、趋势 15%。
    * 新闻按优先级（威胁等级→源分级）逐条填充到预算耗尽为止，不再粗暴截断。
    * 各段独立截断到行边界，避免信息断裂。
  * **多维上下文注入**: 原始新闻 + 聚类事件 + 趋势飙升 → CIO 角色 Prompt → 结构化 JSON。
  * **AI 回退链**: Primary → Fallback 提供商自动切换。
  * **Zod 严格校验**: 输出必须符合 `DailyReportSchema`。

### 2.5 分发层 (Notification Layer)

* **组件**: Feishu Webhook + Telegram Bot API
* **逻辑**:
  * 飞书/Telegram **并行推送**，各自独立（`Promise.allSettled`），一个失败不影响另一个。
  * **指数退避重试** (v2.1 新增): 每个通道独立重试，延迟 1s → 2s → 4s（可配）。
  * 飞书卡片含趋势告警、风险评估等 v2.0+ 新增字段。

---

## 3. 核心数据流 (Data Flow)

```
1. Ingestion (摄入)
   RSS Feed → rss-parser → CircuitBreaker → DBService.hasNews() 
   → DBService.hasSimilarTitle() [模糊去重] → classifyThreat() → saveNews()

2. Analysis (分析)
   getUnreportedNews(limit) → clusterNews() → detectSpikes()

3. Synthesis (合成)
   [新闻+聚类+趋势] → Token 预算分配 → AIService.generateDailyReport()
   → Zod 校验 → DailyReport

4. Delivery (投递)
   DailyReport → retryWithBackoff(sendToFeishu) ‖ retryWithBackoff(sendToTelegram)

5. Finalization (归档)
   DBService.markAsReported()
```

---

## 4. 深度优化特性 (Deep Optimizations)

### 4.1 模糊标题去重

* **目标**: 同一事件被不同源以不同措辞报道时自动合并。
* **方法**: 标准化标题 → 词倒排索引候选查找 → word Jaccard + trigram Dice 双重检测。
* **性能**: 倒排索引将全量比较降为候选集比较，5000 条缓存下 < 50ms。
* **CJK 支持**: `Intl.Segmenter` 原生中日韩分词，降级方案使用字符 bigram。

### 4.2 Token 预算管理

* **目标**: 充分利用 LLM 上下文窗口，高优信息优先保障。
* **方法**: 按信息类型分配配额，逐条填充直到预算耗尽，在行边界截断。
* **效果**: 避免旧版 `.substring(0, 12000)` 的粗暴截断导致信息断裂或浪费。

### 4.3 健壮性

* **异常隔离**: 每个 RSS 源、AI 调用、通知推送均独立 `try-catch`。
* **熔断器**: 连续失败源自动冷却，返回缓存数据，避免级联故障。
* **指数退避**: 通知推送失败自动重试 1s → 2s → 4s。
* **优雅退出**: SIGTERM/SIGINT 停止所有 cron 任务后安全退出。

### 4.4 内存管理

* `seenHeadlines` 从无限增长的 Set 改为 Map + LRU 淘汰（上限可配）。
* `termFrequency` 定期清理过期时间戳，超限时淘汰最不活跃条目。
* 标题去重缓存 5 分钟 TTL 自动刷新。

### 4.5 成本控制

* **并行度控制**: `p-limit` 严格限制 RSS 抓取和 AI 调用的并发。
* **Token 预算**: 精确分配 LLM 上下文空间，避免浪费。
* **分页查询**: 研报新闻条数有上限，防止积压导致 token 暴涨。

---

## 5. 多语言支持 (I18n)

### 5.1 共享分词器 (`utils/tokenizer.ts`)

* 检测文本是否包含 CJK 字符。
* **CJK 文本**: 使用 `Intl.Segmenter`（Node.js 18+ 内置）做词级分词。
* **降级方案**: 若 Segmenter 不可用，CJK 走字符 bigram，英文走空格分词。
* **停用词**: 内置英文 50+ 和中文 40+ 停用词，聚类和趋势检测自动过滤。
* 被 `clustering.ts`、`trending.ts`、`db.service.ts` 三个模块共享。

---

## 6. 配置体系 (Configuration)

### 6.1 集中配置模块 (`config/settings.ts`)

* 所有可调参数从环境变量读取，附合理默认值。
* `dotenv.config()` 在此处统一调用，其余模块通过 `CONFIG` 对象访问。
* 类型安全的 `envInt` / `envFloat` / `envStr` 解析函数。

### 6.2 环境变量 (.env)

| 分类 | 参数 | 默认值 | 说明 |
|------|------|--------|------|
| AI | `AI_API_URL` / `AI_API_KEY` / `AI_MODEL` | — | 主 AI 提供商（必填） |
| AI | `AI_FALLBACK_*` | — | 回退 AI 提供商（推荐） |
| 推送 | `FEISHU_WEBHOOK` | — | 飞书 Webhook |
| 推送 | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | Telegram Bot |
| 调度 | `CRON_COLLECT` / `CRON_REPORT` / `CRON_CLEANUP` | 见表 | Cron 表达式 |
| 采集 | `RSS_TIMEOUT_MS` / `RSS_CONCURRENCY` | 15000 / 10 | RSS 参数 |
| 熔断 | `CB_MAX_FAILURES` / `CB_COOLDOWN_MS` | 3 / 300000 | 熔断器参数 |
| AI | `AI_TIMEOUT_MS` / `AI_MAX_CONTEXT_TOKENS` | 90000 / 8000 | AI 参数 |
| 去重 | `DEDUP_SIMILARITY_THRESHOLD` / `DEDUP_HOURS_BACK` | 0.55 / 24 | 去重参数 |
| 研报 | `REPORT_MAX_NEWS` / `DATA_RETENTION_DAYS` | 500 / 30 | 数据管理 |
| 聚类 | `CLUSTER_SIMILARITY_THRESHOLD` | 0.3 | 聚类阈值 |
| 趋势 | `TRENDING_MAX_TRACKED_TERMS` / `TRENDING_MAX_SEEN_HEADLINES` | 5000 / 50000 | 趋势引擎 |
| 重试 | `NOTIFY_MAX_RETRIES` / `NOTIFY_BASE_DELAY_MS` | 3 / 1000 | 通知重试 |

---

## 7. 部署与运维 (Deployment & Ops)

### 7.1 Node.js 直接运行

```bash
npm install
cp .env.example .env  # 填写配置
npm start
```

### 7.2 Docker 部署

```bash
docker build -t deep-currents .
docker run -d --name deep-currents --env-file .env \
  -v deep-currents-data:/app/data \
  --restart unless-stopped deep-currents
```

* 两阶段构建：builder 编译 TS → 生产镜像仅含编译产物 + 生产依赖。
* `/app/data` 挂载为 Volume，持久化 `intel.db`。
* `--restart unless-stopped` 确保崩溃后自动重启。

### 7.3 运维要点

* `data/intel.db` 需定期备份（SQLite WAL 模式可安全热备）。
* 关注日志中的 `[熔断]` 和 `[ERR]` 标记，及时排查源故障。
* 调整 `AI_MAX_CONTEXT_TOKENS` 以匹配所用模型的上下文窗口。

---

## 8. 路线图 (Roadmap)

**已完成 (v2.1):**

* [x] 信息源分级 & 熔断容错
* [x] 威胁分类管线
* [x] 新闻聚类（碎片→宏观事件）
* [x] 趋势关键词检测
* [x] AI 回退链
* [x] Telegram 推送
* [x] 模糊标题去重
* [x] Token 预算管理
* [x] 通知指数退避重试
* [x] 配置外部化
* [x] 优雅退出
* [x] Docker 部署
* [x] 多语言分词（CJK）

**规划中:**

* [ ] **语义去重 (Embedding)**: 基于向量相似度的深层去重，处理完全改写的同事件报道。
* [ ] **多语言自动翻译**: 外文源翻译为中文后存储和分析。
* [ ] **情绪指数跟踪**: 24 小时新闻情绪分布（乐观/中性/悲观）。
* [ ] **自定义关注词**: 用户配置关键词（如"半导体"、"美联储"），AI 深度挖掘。
* [ ] **邮件订阅**: 定时邮件投递研报。
* [ ] **可观测性**: Prometheus Metrics + 健康检查 API。
* [ ] **研报存档**: 历史研报存储与质量回溯。

---
*DeepCurrents Intelligence Team*
