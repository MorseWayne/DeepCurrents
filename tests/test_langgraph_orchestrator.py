import pytest
from src.services.agent_state import AgentState


def test_agent_state_has_required_keys():
    state = AgentState(
        events=[],
        themes=[],
        combined_context_text="",
        market_context_text="",
        macro_output=None,
        sentiment_output=None,
        strategist_output=None,
        risk_manager_output=None,
        final_report_json=None,
        errors=[],
        retry_count=0,
    )
    assert state["retry_count"] == 0
    assert state["errors"] == []
    assert state["final_report_json"] is None
