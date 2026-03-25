import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.agent_state import AgentState
from src.services.langgraph_orchestrator import build_report_workflow


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


@pytest.fixture
def mock_ai_service():
    svc = AsyncMock()
    svc.call_agent = AsyncMock(return_value='{"test": "output"}')
    svc.parse_daily_report_json = AsyncMock(return_value={"date": "2026-03-24", "executiveSummary": "test"})
    return svc


@pytest.mark.asyncio
async def test_workflow_runs_all_agents(mock_ai_service):
    workflow = build_report_workflow(mock_ai_service)
    initial_state: AgentState = {
        "events": [{"id": "e1", "title": "Test"}],
        "themes": [],
        "combined_context_text": "context",
        "market_context_text": "market",
        "macro_output": None,
        "sentiment_output": None,
        "strategist_output": None,
        "risk_manager_output": None,
        "final_report_json": None,
        "errors": [],
        "retry_count": 0,
    }

    result = await workflow.ainvoke(initial_state)

    assert mock_ai_service.call_agent.call_count >= 3
    assert result["final_report_json"] is not None


@pytest.mark.asyncio
async def test_workflow_handles_agent_error(mock_ai_service):
    mock_ai_service.call_agent = AsyncMock(side_effect=Exception("LLM timeout"))
    mock_ai_service.parse_daily_report_json = AsyncMock(return_value={})

    workflow = build_report_workflow(mock_ai_service)
    initial_state: AgentState = {
        "events": [], "themes": [],
        "combined_context_text": "", "market_context_text": "",
        "macro_output": None, "sentiment_output": None,
        "strategist_output": None, "risk_manager_output": None,
        "final_report_json": None, "errors": [], "retry_count": 0,
    }

    result = await workflow.ainvoke(initial_state)
    assert len(result["errors"]) > 0
