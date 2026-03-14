# DeepCurrents (深流) 架构深度评估与演进战略白皮书 v3.0

**版本**: 3.0 (信息密度增强与全栈本地化版)
**日期**: 2026-03-14
**性质**: 核心架构审计、代码实现差距分析、前瞻性技术规划与分阶段执行路线图
**前置文档**: `report-quality-root-cause-2026-03-14.md` (生产质量根因分析)

---

## 0. 核心原则：混动智能 (Hybrid Intelligence)

DeepCurrents 严格遵循 **"本地算法优先，LLM 仅负责认知推理"** 的设计哲学。拒绝"大模型万能论"，通过确定性算法为系统构建坚实的逻辑底层，仅将最具挑战性的非线性推理任务交给 LLM。

本版新增两条补充原则：

1. **信息密度原则**: 系统质量的天花板由输入信息密度决定，而非模型能力。RSS 摘要的中位数仅 93 字符——再强的 LLM 也无法从 93 个字符中推导出宏观策略。信息密度增强是一切优化的前提。
2. **可观测性原则**: 无法观测的系统无法改进。当前生产环境中 loguru `%s` 占位符 bug 导致模型原始输出不可见，使得质量诊断退化为猜测。每一层处理都必须留下可审计的结构化痕迹。

---

## 1. 现状审计：代码实现与设计意图的差距分析

### 1.1 v2.2 白皮书承诺 vs 代码实现

| 白皮书 v2.2 承诺 | 目标文件 | 实现状态 | 差距级别 |
|:---|:---|:---|:---|
| AkShare 确定性行情抓取 | `utils/market_data.py` | 零代码，requirements.txt 中无 akshare | **完全缺失** |
| BGE-M3 本地 Embedding | `article_feature_extractor.py` | 仅有 OpenAI 实现，接口已抽象 | **完全缺失** |
| FinBERT/VADER 情绪分析 | 无对应文件 | 零代码 | **完全缺失** |
| 本地事件分类器 (Tier 1-4) | `event_ranker.py` | 规则评分，无 ML 分类器 | **完全缺失** |
| Ticker-Mapper 本地强匹配 | `event_enrichment.py` | `asset_symbols.json` 存在，但 `_extract_assets()` 弱——大量 `type="phrase"` | **部分实现** |
| Jaccard >0.8 快速预筛 | `semantic_deduper.py` | Jaccard 已用于 `_title_similarity()`，但无 >0.8 早退逻辑 | **微小差距** |
| 六大技术支柱 (3.1-3.5) | — | 占位符 "详见 v2.1"，从未填充 | **完全缺失** |

### 1.2 生产质量根因链路 (2026-03-14 实测)

```
[采集层] RSS 摘要正文，中位数 93 字符
    |
[标准化层] ArticleNormalizer 不抓全文，仅清洗 content/summary/description/body
    |
[聚类层] 短文本 -> 标题/语义相似度信号弱 -> 大量单文章事件
    |
[排序层] 12 个候选事件，single_source_event_ratio = 1.0
    |
[摘要层] EventSummarizer 仍是 rule_template_v1，brief 天花板很低
    |
[上下文组装] budget_utilization = 19.5%（上下文窗口严重浪费）
    |
[AI 生成层] MarketStrategist 输出被判定为 sparse
    |
[观测层缺口] loguru %s 占位符 bug -> 无法看到模型原始输出
    |
[兜底层] normalize() 默认值 + sparse fallback 二次模板化
    |
[最终输出] 模板拼接物，非 AI 深度研判
```

**核心结论**: 信息密度不足是系统性根因。93 字符的 RSS 摘要经过 12 级处理后，信息只会衰减不会增加。必须在 L1 层解决信息源头问题。

### 1.3 当前关键阈值参数 (来自代码审计)

| 参数 | 当前值 | 所在文件 | 说明 |
|:---|:---|:---|:---|
| `near_title_threshold` | 0.55 | `semantic_deduper.py` | 标题近似去重阈值 |
| `near_simhash_threshold` | 0.9 | `semantic_deduper.py` | SimHash 距离阈值 |
| `semantic_score_threshold` | 0.82 | `semantic_deduper.py` | 语义去重阈值 |
| `semantic_strong_score_threshold` | 0.92 | `semantic_deduper.py` | 强语义去重阈值 |
| `merge_score_threshold` | 0.45 | `event_builder.py` | 事件合并综合分阈值 |
| `semantic_score_threshold` | 0.60 | `event_builder.py` | 事件合并语义阈值 |
| `candidate_pool_size` | 500 | `event_ranker.py` | 候选事件池大小 |

---

## 2. 任务分配决策矩阵 (Decision Matrix)

| 任务类型 | 推荐方案 | 具体技术手段 | 目标文件 | 理由 |
|:---|:---|:---|:---|:---|
| **全文提取** | **本地静态算法** | `trafilatura` + `readability-lxml` fallback | `collector.py`, `utils/extractor.py` | 30+ 语言支持，MIT 协议，无 API 成本 |
| **文本去重 (Near)** | **本地硬算法** | `datasketch` MinHash+LSH + 现有 Jaccard/SimHash | `semantic_deduper.py` | O(1) 近似查询，百万级文章毫秒响应 |
| **文本去重 (Semantic)** | **本地 ML** | 本地 BGE-M3 embedding + Qdrant 向量搜索 | `article_feature_extractor.py` | 零 API 成本，隐私安全 |
| **资产/Ticker 映射** | **本地静态索引 + 模糊匹配** | `asset_symbols.json` (2000+ 条) + `rapidfuzz` | `event_enrichment.py` | 确定性优先，LLM 仅作最后尝试 |
| **金融实体识别 (NER)** | **本地零样本模型** | `GLiNER` (urchade/gliner_multi) | `event_enrichment.py` | 零样本 NER，无需微调，支持自定义实体类型 |
| **基础情绪极性** | **本地专业模型** | `ProsusAI/finbert` via transformers | 新文件 `services/sentiment.py` | 金融专用 3 分类，延迟低于 LLM 10x |
| **Embedding 生成** | **本地 ML** | `fastembed` + `BAAI/bge-m3` (ONNX) | `article_feature_extractor.py` | Qdrant 团队出品，ONNX 推理无需 PyTorch |
| **事件聚类** | **本地 ML** | `HDBSCAN` (scikit-learn-extra) | `event_builder.py` | 密度聚类，自动确定簇数，处理噪声点 |
| **A 股行情抓取** | **本地确定性库** | `akshare` | `utils/market_data.py` | 确定性数据，覆盖 A 股/港股/期货/宏观指标 |
| **金融数值计算** | **本地确定性库** | Pandas, Numpy, Statsmodels | `scorer.py`, `market_data.py` | 严禁 LLM 进行加减乘除 |
| **JSON 结构化输出** | **本地约束库** | `instructor` (patched OpenAI client) | `ai_service.py` | Pydantic schema 强制，消除 JSON 修复循环 |
| **跨事件因果推演** | **LLM Reasoning** | GPT-4o / DeepSeek-R1 / Kimi-K2 | `report_orchestrator.py` | 涉及复杂逻辑链，静态算法难以处理 |
| **策略对抗与纠偏** | **LLM Multi-Agent** | 自研编排 + 辩论模式 | `report_orchestrator.py` | 需要模拟分析师的"第二思考" |
| **LLM 调用追踪** | **开源可观测平台** | `langfuse` (self-hosted) | `ai_service.py`, `report_orchestrator.py` | 替代 broken loguru，全链路 token/cost/latency |
| **检索质量重排** | **本地 ML** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | `report_context_builder.py` | 对 Qdrant 粗检索结果做精排，提升上下文相关性 |

---

## 3. 核心架构：三层漏斗模型 (详细版)

### 3.1 L1: 确定性过滤层 (Local Static)

**职责**: 承担 90% 的低级任务，确保数据质量基线。所有操作必须具备确定性、可复现性和零 API 成本。

#### 3.1.1 全文提取管线 (解决 #1 根因)

当前 `ArticleNormalizer.normalize()` 仅从 RSS feed 字段中提取正文，中位数 93 字符。

**方案**: 在 `collector.py` 的 ingestion 阶段，对 T1/T2 源强制全文抓取：

```python
# 目标实现路径
import trafilatura

def extract_full_text(url: str, html: str | None = None) -> str | None:
    """L1 全文提取：trafilatura -> readability-lxml fallback"""
    downloaded = html or trafilatura.fetch_url(url)
    if not downloaded:
        return None
    text = trafilatura.extract(downloaded, include_comments=False,
                               include_tables=True, favor_precision=True)
    if text and len(text) > 200:
        return text
    # fallback to readability-lxml
    from readability import Document
    doc = Document(downloaded)
    return doc.summary()
```

**目标文件**: `collector.py` (调用点), `utils/extractor.py` (已有骨架，需增强)
**质量门控**: 提取后正文 < 200 字符的文章标记 `content_quality="low"`，在 EventBuilder 中降权。

#### 3.1.2 增强去重层

当前去重流程：exact (URL hash) -> near (title similarity) -> semantic (Qdrant)。

**增强方案**: 在 near 层之前插入 MinHash+LSH 预筛：

```python
# 目标实现路径 -- semantic_deduper.py
from datasketch import MinHash, MinHashLSH

class MinHashDeduper:
    def __init__(self, threshold=0.5, num_perm=128):
        self.lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        self.num_perm = num_perm

    def get_minhash(self, text: str) -> MinHash:
        m = MinHash(num_perm=self.num_perm)
        for word in text.lower().split():
            m.update(word.encode('utf8'))
        return m

    def query_and_insert(self, doc_id: str, text: str) -> list[str]:
        mh = self.get_minhash(text)
        candidates = self.lsh.query(mh)
        self.lsh.insert(doc_id, mh)
        return candidates
```

**优势**: MinHash+LSH 的查询复杂度为 O(1)，相比当前 pairwise Jaccard 的 O(n) 有数量级提升。当文章池超过 1000 篇时效果显著。

**目标文件**: `semantic_deduper.py`
**新增依赖**: `datasketch>=1.6.0`

#### 3.1.3 资产/Ticker 强映射

当前 `asset_symbols.json` 覆盖有限，`_extract_assets()` 中大量实体落入 `type="phrase"`。

**增强方案**:
1. 扩展 `asset_symbols.json` 至 2000+ 条目，覆盖主要 A 股/港股/美股/大宗商品/ETF
2. 增加别名表（中文名 -> ticker 映射，如 "贵州茅台" -> "600519.SH"）
3. 引入 `rapidfuzz` 做模糊匹配，阈值 > 85 时自动关联

```python
# event_enrichment.py 增强
from rapidfuzz import fuzz, process

def resolve_ticker(entity_text: str, asset_db: dict) -> str | None:
    """本地优先：精确匹配 -> 别名匹配 -> 模糊匹配 -> None (交给 LLM)"""
    # 1. 精确匹配
    if entity_text.upper() in asset_db:
        return asset_db[entity_text.upper()]
    # 2. 别名匹配
    if entity_text in alias_table:
        return alias_table[entity_text]
    # 3. 模糊匹配
    result = process.extractOne(entity_text, asset_db.keys(), scorer=fuzz.WRatio)
    if result and result[1] > 85:
        return asset_db[result[0]]
    return None  # 交给 L3 LLM
```

**目标文件**: `event_enrichment.py`, `config/asset_symbols.json`
**新增依赖**: `rapidfuzz>=3.0.0`

#### 3.1.4 异构行情网关

当前仅有 `yfinance`，无法获取 A 股数据。

**方案**: 实现 `AkShareAdapter`，与 yfinance 并行工作：

```python
# utils/market_data.py 新增
class MarketDataProvider(Protocol):
    async def get_quote(self, symbol: str) -> dict | None: ...
    async def get_history(self, symbol: str, period: str) -> pd.DataFrame | None: ...

class AkShareAdapter:
    """A 股/港股/期货/宏观指标数据适配器"""
    def is_cn_symbol(self, symbol: str) -> bool:
        return symbol.endswith(('.SH', '.SZ', '.HK'))

    async def get_quote(self, symbol: str) -> dict | None:
        import akshare as ak
        # A股实时行情
        df = ak.stock_zh_a_spot_em()
        ...
```

**目标文件**: `utils/market_data.py`
**新增依赖**: `akshare>=1.14.0`
**路由逻辑**: 根据 symbol 后缀自动选择 provider（.SH/.SZ -> AkShare, 其余 -> yfinance）

### 3.2 L2: 局部智能感知层 (Local ML)

**职责**: 负责特征工程、分类与聚类。所有模型在本地 CPU 推理，无需 GPU。

#### 3.2.1 本地 Embedding 引擎

当前每篇文章调用 OpenAI `text-embedding-3-small`，这是最大的 API 成本项。

**方案**: 实现 `LocalEmbeddingClient`，使用 Qdrant 团队的 `fastembed` 库：

```python
# article_feature_extractor.py 新增
from fastembed import TextEmbedding

class LocalEmbeddingClient:
    """本地 BGE-M3 embedding，符合 EmbeddingClient 协议"""
    def __init__(self, model_name: str = "BAAI/bge-m3"):
        self.model = TextEmbedding(model_name=model_name)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = list(self.model.embed(texts))
        return [e.tolist() for e in embeddings]
```

**关键参数**:
- 模型: `BAAI/bge-m3` -- MTEB 多语言排行榜前列，中英双语最佳选择
- 维度: 1024 (与当前 OpenAI text-embedding-3-small 的 1536 不同，需迁移 Qdrant collection)
- 推理: ONNX Runtime，无 PyTorch 依赖，CPU 推理速度约 50-100 docs/sec
- 配置: `settings.py` 新增 `EMBEDDING_PROVIDER: Literal["local", "openai"] = "local"`

**目标文件**: `article_feature_extractor.py`, `config/settings.py`
**新增依赖**: `fastembed>=0.4.0`
**迁移注意**: 切换模型后需重建 Qdrant collection（维度变化），建议提供迁移脚本

#### 3.2.2 本地金融 NER

当前 `_extract_assets()` 依赖正则和简单匹配，大量实体漏提或标记为 `phrase`。

**方案**: 引入 GLiNER 零样本 NER：

```python
# event_enrichment.py 增强
from gliner import GLiNER

class FinancialNER:
    LABELS = ["company", "stock_ticker", "commodity", "currency",
              "index", "central_bank", "country", "economic_indicator"]

    def __init__(self):
        self.model = GLiNER.from_pretrained("urchade/gliner_multi-v2.1")

    def extract(self, text: str) -> list[dict]:
        entities = self.model.predict_entities(text, self.LABELS, threshold=0.5)
        return [{"text": e["text"], "type": e["label"], "score": e["score"]}
                for e in entities]
```

**优势**: 零样本——无需标注数据和微调，自定义实体类型列表即可工作。对金融领域实体（公司名、ticker、大宗商品）的识别精度远超正则。

**目标文件**: `event_enrichment.py`
**新增依赖**: `gliner>=0.2.0`

#### 3.2.3 金融情绪分析

当前系统无独立情绪信号，完全依赖 L3 LLM 的 SentimentAnalyst agent。

**方案**: 引入 FinBERT 作为 L2 前置信号：

```python
# 新文件: services/sentiment.py
from transformers import pipeline

class FinancialSentimentAnalyzer:
    def __init__(self):
        self.pipe = pipeline("sentiment-analysis",
                           model="ProsusAI/finbert",
                           max_length=512, truncation=True)

    def analyze(self, text: str) -> dict:
        result = self.pipe(text)[0]
        return {"label": result["label"], "score": result["score"]}
        # label: "positive" | "negative" | "neutral"
```

**用途**: 在 EventRanker 中作为评分信号；在 ReportContextBuilder 中注入事件情绪标签，减轻 SentimentAnalyst 的负担。

**目标文件**: 新文件 `services/sentiment.py`, 集成至 `event_ranker.py`
**新增依赖**: `transformers>=4.40.0`, `torch>=2.0.0` (CPU only)

#### 3.2.4 事件聚类增强

当前 `EventBuilder` 使用 pairwise 合并（标题相似度 + 语义相似度），阈值 merge=0.45, semantic=0.60。短文本下相似度信号弱，导致大量单文章事件。

**方案**: 引入 HDBSCAN 作为补充聚类策略：

```python
# event_builder.py 增强
import hdbscan

def cluster_events_hdbscan(embeddings: np.ndarray, min_cluster_size: int = 3):
    """密度聚类：自动确定簇数，单文章自动标记为噪声"""
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size,
                                 metric='cosine',
                                 cluster_selection_method='eom')
    labels = clusterer.fit_predict(embeddings)
    return labels  # -1 = noise (singleton)
```

**策略**: 先用现有 pairwise 合并，再对剩余单文章事件运行 HDBSCAN 二次聚类。两轮合并可显著降低 single_source_event_ratio。

**目标文件**: `event_builder.py`
**新增依赖**: `hdbscan>=0.8.33`

### 3.3 L3: 认知推理决策层 (Cloud Reasoning)

**职责**: 负责最终的"灵魂生成"——跨事件因果推演、策略合成、风险审查。L1/L2 提供结构化证据，L3 进行非线性推理。

#### 3.3.1 结构化输出约束

当前 `ai_service.py` 使用 `response_format={"type": "json_object"}` + JSON 修复重试链路。极端情况下修复仍失败。

**方案**: 引入 `instructor` 库，用 Pydantic 模型强制约束输出：

```python
# ai_service.py 增强
import instructor
from pydantic import BaseModel

client = instructor.from_openai(AsyncOpenAI(...))

class MacroAnalysis(BaseModel):
    key_themes: list[str]
    risk_factors: list[str]
    market_outlook: str
    confidence: float

response = await client.chat.completions.create(
    model="gpt-4o",
    response_model=MacroAnalysis,
    messages=[...]
)
# response 直接是 MacroAnalysis 实例，无需 JSON 解析/修复
```

**优势**: 消除 JSON 修复循环，类型安全，自动重试（instructor 内置 retry 逻辑），支持 streaming。

**目标文件**: `ai_service.py`, `report_orchestrator.py`
**新增依赖**: `instructor>=1.4.0`

#### 3.3.2 多智能体编排优化

当前 4-agent 架构（MacroAnalyst, SentimentAnalyst, MarketStrategist, RiskManager）基本合理，保持自研编排。

**增强方向**:
1. **辩论模式**: MarketStrategist 输出后，RiskManager 不仅审查，还生成反论。将反论回传给 Strategist 做第二轮修正，形成 "论点-反论-综合" 三段式。
2. **证据引用**: 要求每个 agent 在输出中标注证据来源（事件 ID），便于溯源。
3. **Budget 优化**: 当前 budget_utilization=19.5%，说明上下文窗口严重浪费。将 L1/L2 的全文提取结果直接注入上下文，预期 utilization 提升至 60-80%。

**目标文件**: `report_orchestrator.py`

#### 3.3.3 检索增强：Qdrant 混合搜索 + Cross-Encoder 重排

当前 `report_context_builder.py` 从 Qdrant 做纯向量检索组装上下文。

**增强方案**:
1. **混合搜索**: Qdrant 原生支持 sparse+dense 双向量。使用 BM25 sparse vector + BGE-M3 dense vector，融合检索提升召回率。
2. **Cross-Encoder 重排**: 对 Qdrant 返回的 top-50 候选，用 `cross-encoder/ms-marco-MiniLM-L-6-v2` 精排，取 top-20 注入上下文。

```python
# report_context_builder.py 增强
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def rerank(query: str, documents: list[str], top_k: int = 20) -> list[str]:
    pairs = [(query, doc) for doc in documents]
    scores = reranker.predict(pairs)
    ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
    return [doc for doc, _ in ranked[:top_k]]
```

**目标文件**: `report_context_builder.py`
**新增依赖**: `sentence-transformers>=3.0.0`

---

## 4. 六大技术支柱演进路线

### 4.1 信息密度增强 (解决 #1 根因)

**现状**: RSS 摘要中位数 93 字符，是整个系统质量的硬瓶颈。

**演进路线**:

| 阶段 | 措施 | 目标文件 | 预期效果 |
|:---|:---|:---|:---|
| 立即 | `trafilatura` 全文提取，T1/T2 源强制抓取 | `collector.py`, `utils/extractor.py` | 正文中位数提升至 500-2000 字符 |
| 立即 | 内容质量门控：< 200 字符标记 `low` 并降权 | `collector.py`, `event_builder.py` | 过滤低质量噪声 |
| 短期 | `readability-lxml` 作为 trafilatura 的 fallback | `utils/extractor.py` | 提升全文提取覆盖率至 90%+ |
| 中期 | 对 T3/T4 源也启用全文提取（降低并发以控制带宽） | `collector.py` | 全源覆盖 |

**关键指标**: 正文中位长度从 93 -> 800+ 字符，budget_utilization 从 19.5% -> 60%+。

### 4.2 确定性去重与事件归并

**现状**: exact -> near (Jaccard/Dice/SimHash) -> semantic (Qdrant) 三层去重已建立，但短文本下相似度信号弱。

**演进路线**:

| 阶段 | 措施 | 目标文件 | 预期效果 |
|:---|:---|:---|:---|
| 短期 | MinHash+LSH 预筛层 (`datasketch`) | `semantic_deduper.py` | O(1) 查询，支持百万级文章 |
| 短期 | Jaccard > 0.8 早退优化 | `semantic_deduper.py` | 减少不必要的 embedding 调用 |
| 中期 | HDBSCAN 二次聚类处理单文章事件 | `event_builder.py` | single_source_event_ratio 从 1.0 降至 0.3 以下 |
| 中期 | 跨语言去重（BGE-M3 多语言 embedding） | `semantic_deduper.py` | 中英文同一事件自动合并 |

### 4.3 本地 Embedding 与向量检索

**现状**: 每篇文章调用 OpenAI embedding API，这是最大的外部依赖和成本项。

**演进路线**:

| 阶段 | 措施 | 目标文件 | 预期效果 |
|:---|:---|:---|:---|
| 短期 | `LocalEmbeddingClient` (fastembed + BGE-M3) | `article_feature_extractor.py` | 零 API 成本，~50 docs/sec |
| 短期 | Qdrant collection 迁移脚本（1536 -> 1024 维） | 新脚本 `scripts/migrate_qdrant.py` | 数据平滑迁移 |
| 短期 | `EMBEDDING_PROVIDER` 配置开关 | `config/settings.py` | 支持 local/openai 切换 |
| 中期 | Qdrant 混合搜索（BM25 sparse + dense） | `report_context_builder.py` | 召回率提升 20-30% |
| 中期 | Cross-encoder 重排 | `report_context_builder.py` | 上下文相关性提升 |

### 4.4 金融实体识别与资产映射

**现状**: 正则 + `asset_symbols.json` 简单匹配，大量实体标记为 `type="phrase"`。

**演进路线**:

| 阶段 | 措施 | 目标文件 | 预期效果 |
|:---|:---|:---|:---|
| 短期 | 扩展 `asset_symbols.json` 至 2000+ 条目 | `config/asset_symbols.json` | 覆盖主要全球标的 |
| 短期 | 别名表（中文名/简称 -> ticker） | `config/asset_symbols.json` 或 PostgreSQL | "茅台" -> 600519.SH |
| 短期 | `rapidfuzz` 模糊匹配 (阈值 85) | `event_enrichment.py` | 减少 phrase 标记率 |
| 中期 | GLiNER 零样本 NER | `event_enrichment.py` | 结构化实体提取 |
| 中期 | LLM 仅处理 L1/L2 未命中实体 | `event_enrichment.py` | 确定性优先链路完整 |

### 4.5 异构行情网关 (A 股深度集成)

**现状**: 仅有 `yfinance`，无法获取 A 股/港股/期货数据。

**演进路线**:

| 阶段 | 措施 | 目标文件 | 预期效果 |
|:---|:---|:---|:---|
| 中期 | `MarketDataProvider` Protocol 定义 | `utils/market_data.py` | 统一接口，支持多 provider |
| 中期 | `AkShareAdapter` 实现 | `utils/market_data.py` | A 股实时行情 + 财务数据 |
| 中期 | 自动路由 (.SH/.SZ -> AkShare, 其余 -> yfinance) | `utils/market_data.py` | 透明切换 |
| 后期 | 宏观指标注入（社融、PMI、CPI via AkShare） | `report_context_builder.py` | 丰富 L3 宏观背景 |

### 4.6 可观测性与质量评估体系

**现状**: loguru `%s` 占位符 bug 导致模型原始输出不可见；无 LLM 调用级追踪；无报告质量评分。

**演进路线**:

| 阶段 | 措施 | 目标文件 | 预期效果 |
|:---|:---|:---|:---|
| 立即 | 修复 loguru `%s` -> f-string 或 `logger.info("...", output)` | 全项目 | 恢复日志可见性 |
| 短期 | `langfuse` 集成：所有 LLM 调用自动追踪 | `ai_service.py` | token/cost/latency 全链路可视 |
| 短期 | `structlog` 替代 raw loguru（机器可解析日志） | 全项目 | 结构化日志，便于告警 |
| 中期 | 报告质量评分框架 | 新文件 `services/report_evaluator.py` | 自动化质量基线 |
| 后期 | RAGAS 评估集成 | 新文件 `services/rag_evaluator.py` | faithfulness, relevancy, precision |

**报告质量评分维度**:
- **覆盖率**: 报告提及的事件数 / 候选事件总数
- **深度**: 每个事件的平均分析字数
- **可操作性**: 含具体 ticker 的预测数
- **引用密度**: 每个论点的证据引用数
- **budget_utilization**: 上下文窗口使用率

---

## 5. Shock-Chain-Thread 研究引擎 (前瞻)

基于 `docs/superpowers/specs/` 中的设计草案，DeepCurrents 计划在三层漏斗之上构建更高层的语义抽象：

### 5.1 三层研究语义模型

```
Shock Candidate (冲击候选)
    | 因果推演
Transmission Chain (传导链)
    | 深度分析
Chain Thread (链式线索)
```

- **Shock Candidate**: 从事件流中识别具有宏观冲击潜力的事件（如：央行意外加息、地缘冲突升级）
- **Transmission Chain**: 推演冲击的传导路径（如：加息 -> 美元走强 -> 新兴市场资本外流 -> 大宗商品承压）
- **Chain Thread**: 将传导链拆解为可追踪的投资线索，映射到具体标的

### 5.2 与三层漏斗的关系

Shock-Chain-Thread 建立在 L1/L2/L3 之上：
- L1/L2 负责数据采集、去重、实体识别、情绪标注
- L3 负责 Shock 识别和 Chain 推演（需要 LLM 非线性推理）
- Thread 生成是 L3 的延伸，融合 AkShare 行情数据做定量验证

### 5.3 Macro Transmission Report

计划在研报 JSON schema 中新增：
- `macroTransmissionChain`: 宏观传导链路图
- `assetTransmissionBreakdowns`: 按资产维度的传导分解

此功能依赖 Phase 1-3 的基础能力就绪后方可启动。

---

## 6. 执行计划：分阶段实施路线图

### Phase 1 (P0 -- 1-2 周): 信息密度修复

这是唯一的 P0 阶段——不解决信息密度问题，后续所有优化的效果都会被瓶颈压制。

| 任务 | 目标文件 | 新增依赖 | 工作量预估 |
|:---|:---|:---|:---|
| trafilatura 全文提取管线 | `collector.py`, `utils/extractor.py` | `trafilatura`, `readability-lxml` | 2-3 天 |
| 内容质量门控 (< 200 字符降权) | `collector.py`, `event_builder.py` | 无 | 0.5 天 |
| 修复 loguru `%s` 占位符 bug | 全项目 (grep `%s` in logger calls) | 无 | 0.5 天 |
| `instructor` 结构化输出替换 JSON 修复链路 | `ai_service.py` | `instructor` | 1-2 天 |
| EventSummarizer brief 模板升级 | `event_summarizer.py` | 无 | 1 天 |

**Phase 1 验收标准**:
- 正文中位长度 > 500 字符
- loguru 日志可见模型原始输出
- AI 调用不再触发 JSON repair fallback
- budget_utilization > 40%

### Phase 2 (P0 -- 2-4 周): 本地化迁移

| 任务 | 目标文件 | 新增依赖 | 工作量预估 |
|:---|:---|:---|:---|
| `LocalEmbeddingClient` (fastembed + BGE-M3) | `article_feature_extractor.py` | `fastembed` | 2-3 天 |
| Qdrant collection 迁移 (1536 -> 1024 维) | 新脚本 `scripts/migrate_qdrant.py` | 无 | 1 天 |
| `EMBEDDING_PROVIDER` 配置开关 | `config/settings.py` | 无 | 0.5 天 |
| MinHash+LSH 去重预筛层 | `semantic_deduper.py` | `datasketch` | 1-2 天 |
| GLiNER 金融 NER | `event_enrichment.py` | `gliner` | 2-3 天 |
| 扩展 asset_symbols.json + rapidfuzz | `config/asset_symbols.json`, `event_enrichment.py` | `rapidfuzz` | 1-2 天 |

**Phase 2 验收标准**:
- Embedding 调用零 API 成本
- 实体 `type="phrase"` 比率从 >50% 降至 <20%
- 去重吞吐量提升 10x (MinHash+LSH)

### Phase 3 (P1 -- 4-8 周): 深度集成

| 任务 | 目标文件 | 新增依赖 | 工作量预估 |
|:---|:---|:---|:---|
| AkShareAdapter 实现 | `utils/market_data.py` | `akshare` | 2-3 天 |
| MarketDataProvider Protocol + 路由 | `utils/market_data.py` | 无 | 1 天 |
| FinBERT 情绪分析管线 | 新文件 `services/sentiment.py` | `transformers`, `torch` | 2-3 天 |
| Langfuse 可观测性集成 | `ai_service.py`, `report_orchestrator.py` | `langfuse` | 2-3 天 |
| Qdrant 混合搜索 (BM25 + dense) | `report_context_builder.py` | 无 (Qdrant 原生) | 2-3 天 |
| 辩论模式 (Strategist <-> RiskManager 二轮) | `report_orchestrator.py` | 无 | 2-3 天 |

**Phase 3 验收标准**:
- A 股标的可查询实时行情
- 每个事件附带 FinBERT 情绪标签
- Langfuse dashboard 可查看全部 LLM 调用
- RiskManager 输出包含对 Strategist 论点的反驳

### Phase 4 (P2 -- 8-12 周): 高级能力

| 任务 | 目标文件 | 新增依赖 | 工作量预估 |
|:---|:---|:---|:---|
| HDBSCAN 事件二次聚类 | `event_builder.py` | `hdbscan` | 2-3 天 |
| Cross-encoder 重排 | `report_context_builder.py` | `sentence-transformers` | 1-2 天 |
| 报告质量评分框架 | 新文件 `services/report_evaluator.py` | 无 | 3-5 天 |
| RAGAS 评估集成 | 新文件 `services/rag_evaluator.py` | `ragas` | 2-3 天 |
| Shock-Chain-Thread 引擎骨架 | 新目录 `services/shock_chain/` | 无 | 5-7 天 |
| structlog 迁移 | 全项目 | `structlog` | 2-3 天 |

**Phase 4 验收标准**:
- single_source_event_ratio < 0.3
- 报告质量评分自动化输出
- Shock-Chain 可识别冲击候选并生成初步传导链

---

## 7. 技术选型速查表

| 库名 | 版本 | 用途 | 目标文件 | License | 备注 |
|:---|:---|:---|:---|:---|:---|
| `trafilatura` | >=1.8.0 | 全文提取 | `collector.py`, `utils/extractor.py` | Apache-2.0 | 30+ 语言，生产验证 |
| `readability-lxml` | >=0.8.0 | 全文提取 fallback | `utils/extractor.py` | Apache-2.0 | Mozilla Readability 移植 |
| `fastembed` | >=0.4.0 | 本地 embedding 推理 | `article_feature_extractor.py` | Apache-2.0 | Qdrant 团队，ONNX 推理 |
| `datasketch` | >=1.6.0 | MinHash+LSH 去重 | `semantic_deduper.py` | MIT | 百万级文档毫秒查询 |
| `rapidfuzz` | >=3.0.0 | 模糊字符串匹配 | `event_enrichment.py` | MIT | C++ 底层，极快 |
| `gliner` | >=0.2.0 | 零样本 NER | `event_enrichment.py` | Apache-2.0 | 无需微调 |
| `instructor` | >=1.4.0 | LLM 结构化输出 | `ai_service.py` | MIT | Pydantic 强制约束 |
| `langfuse` | >=2.0.0 | LLM 可观测性 | `ai_service.py` | MIT | 可自建部署 |
| `akshare` | >=1.14.0 | A 股/港股行情 | `utils/market_data.py` | MIT | 覆盖沪深港 + 期货 + 宏观 |
| `transformers` | >=4.40.0 | FinBERT 情绪分析 | `services/sentiment.py` | Apache-2.0 | HuggingFace 生态 |
| `hdbscan` | >=0.8.33 | 密度聚类 | `event_builder.py` | BSD-3 | 自动确定簇数 |
| `sentence-transformers` | >=3.0.0 | Cross-encoder 重排 | `report_context_builder.py` | Apache-2.0 | 精排模型 |
| `structlog` | >=24.0.0 | 结构化日志 | 全项目 | Apache-2.0 | 机器可解析 |
| `ragas` | >=0.2.0 | RAG 质量评估 | `services/rag_evaluator.py` | Apache-2.0 | 标准化 RAG 评估 |

---

## 附录 A: 当前 LLM 调用热力图

| 调用点 | 所在文件 | 频率 | 单次成本估算 | 可替代性 | 替代方案 |
|:---|:---|:---|:---|:---|:---|
| Embedding 生成 | `article_feature_extractor.py` | 每篇文章 (~200/天) | ~$0.002/篇 | **可完全替代** | fastembed + BGE-M3 |
| 事件富化 (可选) | `event_enrichment.py` | 每事件 (~30/天) | ~$0.01/事件 | **部分替代** | GLiNER NER + 规则优先 |
| 事件摘要 (llm_v1) | `event_summarizer.py` | Top 事件 (~10/天) | ~$0.02/事件 | **部分替代** | 全文提取后模板更有效 |
| MacroAnalyst | `report_orchestrator.py` | 1 次/天 | ~$0.10 | **不可替代** | 核心认知推理 |
| SentimentAnalyst | `report_orchestrator.py` | 1 次/天 | ~$0.08 | **部分替代** | FinBERT 前置可减轻负担 |
| MarketStrategist | `report_orchestrator.py` | 1 次/天 | ~$0.15 | **不可替代** | 核心策略合成 |
| RiskManager | `report_orchestrator.py` | 1 次/天 | ~$0.10 | **不可替代** | 核心风险审查 |
| JSON 修复重试 | `ai_service.py` | 失败时 (~5/天) | ~$0.05/次 | **可消除** | instructor 结构化输出 |

**当前日均 API 成本估算**: ~$1.00-1.50/天 (以 gpt-4o pricing 计)
**Phase 2 完成后估算**: ~$0.50-0.70/天 (消除 embedding + 减少修复重试)

---

## 附录 B: 关键接口与注入点

### B.1 EmbeddingClient 协议

```python
# article_feature_extractor.py 中已定义
class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**注入点**: `ArticleFeatureExtractor.__init__(embedding_client=...)` -- 实现 `LocalEmbeddingClient` 即可切换。

### B.2 AIServiceLike 协议

被 `EventEnrichment`, `EventSummarizer`, `ReportOrchestrator` 共用。

**注入点**: 各服务的 `__init__` 方法接收 `ai_service` 参数。引入 instructor 时，在 `AIService` 内部替换调用方式即可，外部接口不变。

### B.3 MarketDataProvider 模式 (待实现)

```python
# 目标设计
class MarketDataProvider(Protocol):
    async def get_quote(self, symbol: str) -> dict | None: ...
    async def get_history(self, symbol: str, period: str) -> pd.DataFrame | None: ...
    def supports(self, symbol: str) -> bool: ...
```

**注入点**: `market_data.py` 当前直接调用 yfinance，需重构为 Provider 模式。路由逻辑根据 symbol 后缀选择 provider。

### B.4 EventBuilder 评分信号

```python
# event_builder.py 中 _build_merge_signals()
signals = {
    "title_similarity": float,   # Jaccard/Dice/SimHash
    "semantic_similarity": float, # Qdrant 向量距离
    "time_proximity": float,      # 时间接近度
    "source_overlap": float,      # 来源重叠度
}
```

**扩展点**: 可新增 `minhash_similarity`, `entity_overlap`, `sentiment_alignment` 等信号，丰富合并决策依据。

---

*Powered by DeepCurrents Intelligence Engine v3.0 -- "Deterministic-First, Density-Driven" Strategy*
