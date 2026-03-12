# DeepCurrents (深流) 技术设计文档

**版本**: v2.2 (Python)  
**状态**: 可运行 / 持续迭代中  
**定位**: AI 驱动的全球情报聚合与宏观策略研报引擎

---

## 1. 系统概述

DeepCurrents 从多源 RSS/RSSHub 信息流中抓取新闻，进行去重、威胁分类、事件聚类，并通过多智能体 LLM 流程生成每日结构化研报，再投递到飞书与 Telegram。

当前主实现位于 `src/`（Python）；`src_ts/` 为历史 TypeScript 版本参考，不是默认运行链路。

---

## 2. 代码架构（Python 主链路）

### 2.1 入口与调度

- 入口: `src/main.py`
- 调度器: `APScheduler.AsyncIOScheduler`
- 默认任务:
  - 数据采集: `CRON_COLLECT`（默认 `0 * * * *`）
  - 报告生成: `CRON_REPORT`（默认 `0 8 * * *`）
  - 自动评分: 固定 interval 4 小时
  - 数据清理: `CRON_CLEANUP`（默认 `0 3 * * *`）

说明: 当前实现仅从 cron 字符串中解析小时/分钟字段，不支持完整 crontab 语法的所有组合。

### 2.2 业务编排层

- 编排器: `src/engine.py` (`DeepCurrentsEngine`)
- 责任:
  - 启动时连接 DB、触发首轮采集与评分
  - 采集 -> 聚类上下文构建 -> AI 生成 -> 推送 -> 标记已报告
  - 定时清理历史数据

### 2.3 采集层

- 模块: `src/services/collector.py`
- 技术: `aiohttp` + `feedparser` + `asyncio.Semaphore`
- 关键机制:
  - 按信源 tier 优先级抓取
  - URL 去重 + 标题模糊去重双重拦截
  - T1/T2 信源尝试正文提取（`src/utils/extractor.py`）
  - 熔断器（`src/services/circuit_breaker.py`）按源级别计数失败并冷却

### 2.4 存储与去重层

- 模块: `src/services/db_service.py`
- 存储: `aiosqlite`（文件 `data/intel.db`）
- 数据表:
  - `raw_news`: 原始新闻、分级、威胁字段、已报告标记
  - `predictions`: 资产预测、基准价格、评分状态
- 去重:
  - URL 唯一约束
  - 标题标准化 + 词集 Jaccard + trigram Dice
  - 近窗口标题缓存与倒排索引

### 2.5 分析层

- 威胁分类: `src/services/classifier.py`
  - 关键词级联（critical/high/medium/low/info）
  - 地缘升级规则（行为词 + 目标词）
- 事件聚类: `src/services/clustering.py`
  - 多语言分词后计算 Jaccard，相似标题并查集合并
  - 聚类后聚合威胁级别与来源信息

### 2.6 AI 生成层

- 模块: `src/services/ai_service.py`
- 角色流程:
  - MacroAnalyst（宏观）并行
  - SentimentAnalyst（情绪）并行
  - MarketStrategist（总整合）
- 支持主/备模型回退
- 上下文预算: `AI_MAX_CONTEXT_TOKENS`（默认 16000）

当前实现状态:

- 最终 Strategist 调用使用自由文本输出后做 JSON 提取，偶发 JSON 结构不合法会导致 `json.loads` 失败。
- 市场数据在 AI 阶段仍为占位文本（未直接接入实时 `yfinance` 结果）。
- 预测自动持久化逻辑已预留注释，但默认未启用。

### 2.7 评分层

- 模块: `src/services/scorer.py`
- 行情读取: `src/utils/market_data.py`（`yfinance`）
- 评分流程:
  - 轮询 `predictions` 中 `pending` 记录
  - 获取当前价格并按方向与涨跌幅打分
  - 更新 `status=scored`

当前为演示窗口: 预测后 10 秒即可评分；生产建议改为 12h/24h 窗口。

### 2.8 推送层

- 模块: `src/services/notifier.py`
- 通道:
  - 飞书卡片（`aiohttp`）
  - Telegram Bot（`httpx`，支持代理）
- 特性:
  - 通道并行
  - 指数退避重试
  - 单通道失败不阻塞其他通道

---

## 3. 信息源配置

- 文件: `src/config/sources.py`
- 当前配置规模: 73 个 source（含原生 RSS 与 RSSHub 扩展）
- 关键字段:
  - `tier`（1-4）
  - `type`（wire/gov/intel/mainstream/market/other）
  - `is_rss_hub`（是否走 RSSHub 重写）
- URL 重写规则:
  - 若 `is_rss_hub=True` 且设置了 `RSSHUB_BASE_URL`
  - 将 `https://rsshub.app/...` 替换为自建地址

---

## 4. 配置体系

- 文件: `src/config/settings.py`（Pydantic Settings）
- 来源: `.env` + 环境变量
- 核心配置组:
  - 采集并发/超时
  - 熔断参数
  - AI 主备提供商
  - 去重与聚类阈值
  - 推送重试与代理
  - 日志输出

---

## 5. 测试与质量现状

- 测试目录: `tests/`
- 当前用例数: 21
- 覆盖模块: 配置、分词、DB、采集、引擎、AI、评分、通知、分类与聚类

注意:

- `src/test_tools.py` 以脚本方式运行，`pytest` 会给出 `PytestCollectionWarning`（不是功能性失败）。

---

## 6. 运行与部署

### 6.1 本地运行

```bash
uv pip install -r requirements.txt
cp .env.example .env
uv run -m src.main
```

### 6.2 手动报告命令

```bash
uv run -m src.run_report
uv run -m src.run_report --report-only --no-push
uv run -m src.run_report --json
```

### 6.3 Docker Compose

- 文件: `docker-compose.yml`
- 当前配置使用 `network_mode: host`
- `deep-currents` 默认注入 `RSSHUB_BASE_URL=http://127.0.0.1:1200`

---

## 7. 已知限制与改进建议

1. 报告最终 JSON 解析脆弱:
   - 建议将 Strategist 调用切换为 `response_format={"type":"json_object"}` 或失败后自动重试 JSON 修复链路。
2. 预测闭环未打通:
   - 建议在 `AIService.generate_daily_report` 后解析 `investmentTrends` 并写入 `predictions`。
3. 调度 cron 解析过于简化:
   - 建议直接把完整 cron 交给 APScheduler 的 `CronTrigger.from_crontab`。
4. 采集器对部分异常缺乏结构化原因分类:
   - 建议区分 HTTP 状态、TLS、超时、解析错误并统计输出。

---

*Last aligned with codebase on 2026-03-12.*
