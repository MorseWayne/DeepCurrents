from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.run_report import run_report


@pytest.mark.asyncio
async def test_run_report_bootstraps_runtime_before_report_only_flow():
    mock_engine = MagicMock()
    mock_engine.bootstrap_runtime = AsyncMock()
    mock_engine.collect_data = AsyncMock()
    mock_engine.generate_and_send_report = AsyncMock(return_value=None)
    mock_engine.stop = AsyncMock()

    args = SimpleNamespace(report_only=True, no_push=True, json=False, output=None)

    with patch("src.run_report.DeepCurrentsEngine", return_value=mock_engine):
        await run_report(args)

    mock_engine.bootstrap_runtime.assert_called_once()
    mock_engine.collect_data.assert_not_called()
    mock_engine.generate_and_send_report.assert_called_once()
    mock_engine.stop.assert_called_once()
