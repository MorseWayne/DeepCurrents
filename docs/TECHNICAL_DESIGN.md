# DeepCurrents (深流) 技术设计文档

**版本**: v1.0.0  
**状态**: 生产就绪 (Production Ready)  
**定位**: AI 驱动的全球情报聚合与宏观战略研报引擎

---

## 1. 系统概述 (System Overview)

DeepCurrents 是一个高性能的宏观情报系统，旨在从全球 400+ 个顶级资讯源中提取碎片化信息，并通过 AI 推理引擎将其转化为深度的宏观经济与投资策略报告。其核心逻辑在于：**从“新闻浪花”中识别底层的“宏观深流”**。

## 2. 系统架构 (System Architecture)

系统采用模块化设计，主要由以下三个核心服务组成：

### 2.1 数据收集层 (Collector Layer)

* **组件**: `DeepCurrentsEngine` + `rss-parser`
* **逻辑**:
  * 通过 `node-cron` 调度，每小时运行一次。
  * 使用 `p-limit` 限制并发抓取（10 并发），保护上游源并防止 IP 被封。
  * 源配置存储于 `src/config/sources.ts`，借鉴了顶级 OSINT 源筛选策略。

### 2.2 持久化存储层 (Storage Layer)

* **组件**: `DBService` + `better-sqlite3`
* **逻辑**:
  * 使用 SQLite 本地数据库进行持久化。
  * **幂等性校验**: 通过 URL 的 Base64 编码作为唯一 ID，确保即使源重复，数据库中也只有一份记录。
  * **状态管理**: 使用 `is_reported` 字段标记新闻是否已被包含在生成的研报中。

### 2.3 智能分析与分发层 (Intelligence & Notification Layer)

* **组件**: `AIService` + `Lark API`
* **逻辑**:
  * 每天早晨 08:00 提取所有 `is_reported = 0` 的原始新闻。
  * **Token 优化**: 只截取每条新闻的前 500 个字符，并在 Context 中只保留标题和关键摘要。
  * **Prompt 工程**: 引导 AI 扮演 CIO (首席投资官) 角色，生成包含【核心主线】、【经济深度分析】和【资产类别研判】的结构化 JSON。
  * **格式化推送**: 使用飞书卡片格式 (Indigo 主题) 进行专业排版分发。

---

## 3. 核心数据流 (Data Flow)

1. **Ingestion (摄入)**:
    RSS Feed → `rss-parser` → `DBService.saveNews()` (去重入库)
2. **Synthesis (合成)**:
    `DBService.getUnreportedNews()` → `AIService.generateDailyReport()` (大模型推理)
3. **Delivery (投递)**:
    JSON Report → Markdown Formatter → Feishu Webhook
4. **Finalization (归档)**:
    `DBService.markAsReported()` (状态更新)

---

## 4. 深度优化特性 (Deep Optimizations)

### 4.1 健壮性与可观测性

* **异常隔离**: 每个 RSS 源和 AI 调用都包装在独立的 `try-catch` 中，确保单点故障不影响全局。
* **结构化日志**: 接入 `pino` 日志系统，支持实时追踪收集进度、分析状态和投递结果。

### 4.2 语义去重 (未来增强)

* 计划引入 `semantic_hash`：计算标题的向量（Embeddings），在数据库层面合并描述同一事件的不同报道。

### 4.3 成本与频率限制

* **并行度控制**: `p-limit` 严格限制了 AI 接口的并发调用，避免触发 API 供应商的速率限制。
* **Token 截断**: 在向 LLM 提供上下文时进行强制截断，确保长文本处理的稳定性和经济性。

---

## 5. 部署与运维 (Deployment & Ops)

### 5.1 运行环境

* 推荐使用 Node.js 18+ 环境。
* 持久化文件 `data/intel.db` 需定期备份。

### 5.2 环境变量 (.env)

* `AI_API_URL`: 支持 OpenAI 兼容格式。
* `AI_MODEL`: 推荐使用 GPT-4o 或同级别的长上下文模型。
* `FEISHU_WEBHOOK`: 飞书群机器人自定义 Webhook。

---

## 6. 路线图 (Roadmap)

* [ ] **多语言自动翻译**: 自动将外文源翻译为中文再存储。
* [ ] **情绪指数跟踪**: 统计过去 24 小时全球新闻的情绪中性/乐观/悲观分布。
* [ ] **多端推送**: 增加 Telegram 和邮件订阅支持。
* [ ] **自定义关注词**: 允许用户配置特定关键词（如“半导体”、“美联储”），AI 会在报告中对相关内容进行深度挖掘。

---
*DeepCurrents Intelligence Team*
