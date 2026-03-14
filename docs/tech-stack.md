# Tech Stack: DeepCurrents (深流)

## 编程语言与核心环境
- **Python 3.10+**: 核心开发语言，利用其在 AI、数据科学领域的强大生态及异步 I/O 能力。
- **asyncio**: 异步非阻塞运行时，支撑大规模并发资讯采集。

## 数据基础设施与存储
- **SQLite**: 本地嵌入式数据库，用于存储全球资讯源、处理后的事件及生成的研报。
- **aiosqlite**: 异步 SQLite 驱动，确保 I/O 操作不阻塞主循环。

## 情报采集与处理管线
- **aiohttp**: 高性能异步 HTTP 客户端，负责 RSS 源抓取与正文提取。
- **feedparser**: 标准 RSS/Atom 解析库。
- **BeautifulSoup4 & lxml**: 自动化抓取并提取高质量网页正文。
- **Pydantic v2**: 提供严密的数据 Schema 验证，确保在数据处理和 AI 推理前的结构完整性。

## AI 推理与分析逻辑
- **多智能体协作流 (Multi-Agent Pipeline)**: 采用 Macro Analyst -> Sentiment Analyst -> Market Strategist 异步协作逻辑，实现深度宏观推演。
- **OpenAI Python SDK**: 核心 AI 引擎，支持 OpenAI 兼容接口，驱动事件聚类、威胁分类、趋势检测及研报合成。
- **yfinance**: 集成实时资产价格走势，辅助“预期差”分析。

## 运维、调度与可观测性
- **APScheduler**: 负责定时采集、研报合成、自动评分和数据清理任务。
- **Loguru**: 现代化的结构化日志系统，支持控制台彩色输出与本地日志文件落盘。
- **httpx**: 具备重试逻辑的异步 HTTP 客户端，用于 Webhook 推送。

## NLP/分词
- **Jieba**: 中文分词与处理。
- **NLTK**: 英文文本处理与停用词过滤。
