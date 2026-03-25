"""LangGraph Multi-Agent 状态模型。

所有节点读写此 TypedDict；LangGraph 自动管理状态快照与回溯。
"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    # ── 输入上下文 ──
    events: list[dict[str, Any]]
    themes: list[dict[str, Any]]
    combined_context_text: str
    market_context_text: str

    # ── Agent 输出（按调用顺序填充）──
    macro_output: str | None
    sentiment_output: str | None
    strategist_output: str | None
    risk_manager_output: str | None

    # ── 最终结果 ──
    final_report_json: dict[str, Any] | None

    # ── 元数据 ──
    errors: list[str]
    retry_count: int
