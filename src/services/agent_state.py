"""LangGraph Multi-Agent 状态模型。

所有节点读写此 TypedDict；LangGraph 自动管理状态快照与回溯。

注意：`errors` 字段使用 Annotated + operator.add 作为 reducer，
以支持并行节点同步写入而不触发 InvalidUpdateError。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


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
    # 使用 operator.add 作为 reducer，允许并行节点同时追加错误消息
    errors: Annotated[list[str], operator.add]
    retry_count: int
