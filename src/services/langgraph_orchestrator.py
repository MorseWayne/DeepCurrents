"""LangGraph StateGraph 工作流编排器。

该模块实现了多智能体并行分析流水线：
  - macro_analyst_node 和 sentiment_analyst_node 并行执行
  - 两者完成后，strategist_node 汇总两路输出
  - risk_manager_node 对策略师草稿进行风险审核
  - 最终报告写入 state["final_report_json"]

所有节点均捕获异常，将错误信息追加到 state["errors"]，以确保工作流不会因单个智能体失败而中断。
"""
from __future__ import annotations

import json
from typing import Any

from langgraph.graph import END, START, StateGraph

from src.services.agent_state import AgentState
from src.services.prompts import (
    MACRO_ANALYST_PROMPT_V2,
    MARKET_STRATEGIST_PROMPT_V2,
    RISK_MANAGER_PROMPT,
    SENTIMENT_ANALYST_PROMPT_V2,
    build_macro_analyst_input,
    build_market_strategist_input,
    build_risk_manager_input,
    build_sentiment_analyst_input,
)


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    """尝试将字符串解析为 JSON 字典；失败时返回 None。"""
    if not raw:
        return None
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def build_report_workflow(ai_service: Any) -> Any:
    """构建并编译 LangGraph 多智能体报告工作流。

    工作流拓扑：
        START ──► macro_analyst_node ──┐
                                       ├──► strategist_node ──► risk_manager_node ──► END
        START ──► sentiment_analyst_node ──┘

    Args:
        ai_service: 提供 call_agent() 和 parse_daily_report_json() 方法的异步服务对象。

    Returns:
        已编译的 CompiledGraph，可通过 ainvoke(state) 调用。
    """

    async def macro_analyst_node(state: AgentState) -> dict[str, Any]:
        """宏观分析师节点：分析事件与市场背景，输出宏观逻辑 JSON。"""
        try:
            user_input = build_macro_analyst_input(state["combined_context_text"])
            raw = await ai_service.call_agent(MACRO_ANALYST_PROMPT_V2, user_input)
            return {"macro_output": raw}
        except Exception as exc:
            return {"macro_output": None, "errors": [f"macro_analyst_node: {exc}"]}

    async def sentiment_analyst_node(state: AgentState) -> dict[str, Any]:
        """情绪分析师节点：分析市场情绪，输出情绪状态 JSON。"""
        try:
            user_input = build_sentiment_analyst_input(
                state["combined_context_text"],
                state["market_context_text"],
            )
            raw = await ai_service.call_agent(SENTIMENT_ANALYST_PROMPT_V2, user_input)
            return {"sentiment_output": raw}
        except Exception as exc:
            return {"sentiment_output": None, "errors": [f"sentiment_analyst_node: {exc}"]}

    async def strategist_node(state: AgentState) -> dict[str, Any]:
        """策略师节点：汇总宏观与情绪输出，产出配置建议草稿 JSON。"""
        try:
            macro_json = _try_parse_json(state.get("macro_output") or "")
            sentiment_json = _try_parse_json(state.get("sentiment_output") or "")
            user_input = build_market_strategist_input(
                state["combined_context_text"],
                macro_json,
                sentiment_json,
                state["market_context_text"],
            )
            raw = await ai_service.call_agent(MARKET_STRATEGIST_PROMPT_V2, user_input)
            return {"strategist_output": raw}
        except Exception as exc:
            return {"strategist_output": None, "errors": [f"strategist_node: {exc}"]}

    async def risk_manager_node(state: AgentState) -> dict[str, Any]:
        """风险管理节点：审核策略师草稿，输出最终修正版报告 JSON。"""
        try:
            strategist_json = _try_parse_json(state.get("strategist_output") or "")
            if strategist_json is None:
                strategist_json = {}
            user_input = build_risk_manager_input(strategist_json, state["market_context_text"])
            raw = await ai_service.call_agent(RISK_MANAGER_PROMPT, user_input)
            parsed = await ai_service.parse_daily_report_json(raw)
            return {"risk_manager_output": raw, "final_report_json": parsed}
        except Exception as exc:
            return {
                "risk_manager_output": None,
                "final_report_json": None,
                "errors": [f"risk_manager_node: {exc}"],
            }

    # ── 图构建 ──────────────────────────────────────────────────────────────
    graph = StateGraph(AgentState)

    graph.add_node("macro_analyst", macro_analyst_node)
    graph.add_node("sentiment_analyst", sentiment_analyst_node)
    graph.add_node("strategist", strategist_node)
    graph.add_node("risk_manager", risk_manager_node)

    # 并行分支：START 同时触发宏观与情绪分析师
    graph.add_edge(START, "macro_analyst")
    graph.add_edge(START, "sentiment_analyst")

    # 两路并行完成后汇入策略师
    graph.add_edge("macro_analyst", "strategist")
    graph.add_edge("sentiment_analyst", "strategist")

    # 线性后段：策略师 → 风险管理员 → 结束
    graph.add_edge("strategist", "risk_manager")
    graph.add_edge("risk_manager", END)

    return graph.compile()


__all__ = ["build_report_workflow"]
