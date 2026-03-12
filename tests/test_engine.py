import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from src.engine import DeepCurrentsEngine

@pytest.fixture
async def engine():
    with patch('src.services.db_service.DBService.connect', new_callable=AsyncMock):
        with patch('src.services.db_service.DBService.close', new_callable=AsyncMock):
            engine = DeepCurrentsEngine()
            yield engine

@pytest.mark.asyncio
async def test_engine_collect_data(engine):
    # Mock collector
    engine.collector.collect_all = AsyncMock(return_value={"new_items": 5, "errors": 0})
    
    await engine.collect_data()
    engine.collector.collect_all.assert_called_once()

@pytest.mark.asyncio
async def test_engine_generate_report_flow(engine):
    # Mock DB, AI, and Scorer
    engine.db.get_unreported_news = AsyncMock(return_value=[
        MagicMock(id='1', title='Gold up', url='u1', content='C1', category='C', tier=1, timestamp='2026-03-12T12:00:00')
    ])
    engine.ai.generate_daily_report = AsyncMock(return_value=MagicMock(date='2026-03-12'))
    engine.db.mark_as_reported = AsyncMock()
    
    await engine.generate_and_send_report()
    
    engine.ai.generate_daily_report.assert_called_once()
    engine.db.mark_as_reported.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])
