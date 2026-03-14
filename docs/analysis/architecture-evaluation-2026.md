# 🌊 DeepCurrents (深流) 架构深度评估与演进战略白皮书 v2.2

**版本**: 2.2 (混动智能与确定性增强版)
**日期**: 2026-03-14
**性质**: 核心架构审计、前瞻性技术规划与“混动智能”分层蓝图

---

## 0. 核心原则：混动智能 (Hybrid Intelligence)
DeepCurrents 严格遵循 **“本地算法优先，LLM 仅负责认知推理”** 的设计哲学。拒绝“大模型万能论”，通过确定性算法为系统构建坚实的逻辑底层，仅将最具挑战性的非线性推理任务交给 LLM。

---

## 1. 任务分配决策矩阵 (Decision Matrix)

| 任务类型 | 推荐方案 | 技术手段 | 理由 |
| :--- | :--- | :--- | :--- |
| **网页解析与清洗** | **本地静态算法** | BeautifulSoup, Regex, XPath | 规则明确，LLM 处理速度慢且易丢失标签 |
| **文本去重 (Dedup)** | **本地硬算法** | Trigram, SimHash, Jaccard | 毫秒级响应，结果可复现，零 API 成本 |
| **资产/Ticker 映射** | **本地静态索引** | Ticker-Mapper (Json/SQLite) | 绝对确定性，防止 LLM 生成虚假 Symbol |
| **金融数值计算** | **本地确定性库** | Pandas, Numpy, Statsmodels | 严禁 LLM 进行加减乘除，防止算术幻觉 |
| **基础情绪极性** | **局部专业模型** | FinBERT, VADER (Local) | 延迟低，语境专注度高于通用 LLM |
| **跨事件因果推演** | **LLM Reasoning** | GPT-4o, DeepSeek-R1 | 涉及复杂逻辑链，静态算法难以处理 |
| **策略对抗与纠偏** | **LLM Multi-Agent** | Reasoning Chains (o1/R1) | 需要模拟人类分析师的“第二思考” |

---

## 2. 核心架构演进：三层漏斗模型

### 2.1 L1：确定性过滤层 (Local Static)
*   **职责**: 负责 90% 的低级任务。
*   **静态能力**: 
    *   **AkShare/yfinance**: 确定性的行情抓取。
    *   **Semantic Dedup (Static)**: 基于文本重叠度的初步剔除。
    *   **Entity Linker**: 优先通过本地 `asset_symbols.json` 进行强匹配。

### 2.2 L2：局部智能感知层 (Local ML)
*   **职责**: 负责特征工程与分类。
*   **静态能力**: 
    *   **BGE/Sentence-Transformers**: 本地 Embedding 生成，支持毫秒级语义检索。
    *   **Local Classifier**: 对事件进行重要性分级（Tier 1-4）。

### 2.3 L3：认知推理决策层 (Cloud Reasoning)
*   **职责**: 负责最终的“灵魂生成”。
*   **LLM 能力**: 
    *   **Strategic Synthesis**: 将 L1/L2 准备好的结构化证据合成策略。
    *   **Scenario Analysis**: 情景假设分析（如果 A 发生，B 会怎样）。

---

## 3. 未来演进：六大核心技术支柱 (保持 v2.1 结构)

*(此处保留 3.1 - 3.5 章节，详见 v2.1)*

### 3.6 异构行情与 A 股深度集成 (确定性增强)
*   **集成策略**: 
    *   **静态库优先**: 优先使用 `AkShare` 获取 A 股财务报表、换手率等硬指标。
    *   **LLM 辅助解读**: 仅在需要解读“财报中的语气”或“管理层讨论”时使用 LLM。

---

## 4. 执行建议：去 LLM 泡沫行动 (Actionable Plan)

1.  **[P0] 确定性映射**: 重构 `src/services/event_enrichment.py`，将 Ticker 识别逻辑改为“本地词典匹配 + 模糊匹配算法”，LLM 仅作为词典未命中时的最后尝试。
2.  **[P0] 本地去重**: 在 `semantic_deduper.py` 中增加基于 Jaccard 相似度的快速预筛，相似度高于 0.8 的直接判定为重复，无需调用 Embedding/LLM。
3.  **[P0] 异构行情网关**: 实现 `AkShareAdapter`，确保 A 股数据的获取链路是 100% 确定性的。
4.  **[P1] 本地 Embedding 迁移**: 将目前依赖 OpenAI 的 Embedding 任务迁移到本地 **Ollama (BGE-M3)**，提升隐私性并降低成本。

---
*Powered by DeepCurrents Intelligence Engine v2.2 - "Deterministic-First" Strategy*
