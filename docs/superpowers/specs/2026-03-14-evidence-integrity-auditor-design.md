# Design Spec: Evidence Integrity Auditor (证据一致性审计员)

**日期**: 2026-03-14
**状态**: Draft
**目标**: 在 Event Intelligence 架构中引入多智能体协作（Multi-agent Critique），通过专门的审计 Agent 为研报结论提供证据一致性标注，消除 AI 幻觉，提升研报的专业严谨性。

## 1. 背景与动机
当前的 `DeepCurrents` 已实现基于事件的研报生成，但 LLM 在处理复杂宏观逻辑时仍存在“过度推断”或“事实脱靶”的风险。为了达到机构级（Institutional Grade）的研报质量，需要引入类似人工审稿的“逻辑审计”环节，确保每一条核心结论都有迹可循。

## 2. 角色分工与协作模式 (模式 B: Logic Critique)

### 2.1 首席宏观分析师 (Lead Analyst Agent)
- **输入**: 由 `EvidenceSelector` 筛选的原始新闻片段（Snippets）。
- **职责**: 负责全局逻辑构建、因果路径推导和资产定价影响分析。
- **输出**: 结构化的 Markdown 研报初稿。

### 2.2 证据审计员 (Evidence Auditor Agent)
- **输入**: 研报初稿 + 原始新闻片段。
- **职责**: 逐句扫描报告中的核心命题（Claims），比对原始证据。
- **输出**: 结构化的审计 JSON，包含每个命题的置信度评分和证据引用。

## 3. 确定性等级标准 (Certainty Tiers)

| 等级 | 标签 | 定义 | 审计要求 |
| :--- | :--- | :--- | :--- |
| **Verified** | 🟢 已核实 | 结论在 Snippets 中有直接、明确的文字支撑。 | 必须关联具体的 Snippet ID 和原文引用。 |
| **Inferred** | 🟡 已推断 | 结论基于多个事实的逻辑推演，推导链条完整合理。 | 必须列出推导基础的多个 Snippet ID。 |
| **Weak** | 🔴 弱证据 | 结论属于过度推断、主观猜测或与事实脱节。 | 标注为“缺乏直接证据支持”，建议修正或删除。 |

## 4. 技术实现方案

### 4.1 System Prompt 设计 (`AUDITOR_SYSTEM_PROMPT`)
```markdown
# Role: 证据一致性审计员 (Evidence Integrity Auditor)
你是一个极其严谨的宏观研报审计专家。你的任务是核实分析师报告中的每一条“核心命题”。

## 审计准则
1. 提取报告中所有涉及市场预测、价格波动、政策影响的“核心命题”。
2. 将每个命题与提供的 [原始片段] 进行比对。
3. 严格按 Verified/Inferred/Weak 三级打分。
4. 杜绝任何没有证据支持的脑补。

## 输出格式 (JSON)
{
  "audit_results": [
    {
      "claim": "命题原文",
      "tier": "Verified | Inferred | Weak",
      "evidence_refs": ["Snippet_ID"],
      "audit_reasoning": "简短的审计逻辑说明"
    }
  ]
}
```

### 4.2 核心逻辑变更与性能优化 (`EventSummarizer`)
为应对审计调用带来的延迟，`EventSummarizer` 将进行并发化改造：
1. **并发执行**: 在 `summarize_ranked_events` 中，使用 `asyncio.gather` 并发启动每个事件的【摘要+审计】任务流。
2. **两阶段任务流**:
   - **Task A (Drafting)**: 调用 `ai_service` 生成 Markdown 初稿。
   - **Task B (Auditing)**: 获取初稿后立即启动审计 Agent。
3. **结构化合成**:
   - **不污染原文**: 审计结果（标签、理由、引用）存储在独立的 `audit_results` 列表中。
   - **动态生成脚注**: 在最终导出阶段，根据 `audit_results` 动态在 Markdown 文末附加【审计证据链】章节，并使用数字引用（如 `[1]`）与正文关联。

### 4.3 数据模型扩展 (`ReportModels`)
```python
class AuditResult(BaseModel):
    claim: str
    tier: Literal["Verified", "Inferred", "Weak"]
    evidence_refs: List[str] = Field(default_factory=list)
    audit_reasoning: str
    audit_status: str = "success"  # success | failed | timeout

class DailyReport(BaseModel):
    # ... 现有字段 ...
    audit_results: List[AuditResult] = Field(default_factory=list)
    has_audit_layer: bool = False
```

### 4.4 异常处理与降级策略 (Quality Guardrails)
- **Silent Pass 策略**: 如果审计 Agent 响应超时、返回非法 JSON 或达到速率限制，系统将捕获异常并记录日志。
- **行为表现**: 报告生成流程不会中断。最终报告将正常产出，但 `has_audit_layer` 设为 `False`，不显示任何置信度标签和审计脚注。
- **原子性限制**: 审计失败不会导致摘要任务回退到旧的模板模式。

## 5. 验证与测试策略
1. **并发压力测试**: 模拟 10+ 并发事件处理，验证 `asyncio.gather` 下的系统负载和超时处理。
2. **确定性对齐测试**: 构造一个“虚假结论”的 Mock 报告，验证审计员是否能准确识别并标注为 `Weak`。
3. **证据回溯测试**: 验证最终报告中的脚注链接是否能准确指向 `EvidenceSelector` 选出的原始文章。

## 6. 非目标 (Out of Scope)
- 本设计暂不涉及“自动打回重写”逻辑，仅做标注。
- 暂不引入针对“证据冲突”的多轮辩论。
