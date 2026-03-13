import os
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch

from src.services.prediction_repository import PredictionRepository
from src.services.scorer import PredictionScorer


@pytest_asyncio.fixture
async def prediction_repository(tmp_path):
    db_path = tmp_path / "test_predictions.db"
    repository = PredictionRepository(str(db_path))
    await repository.connect()
    yield repository
    await repository.close()
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.mark.asyncio
async def test_scoring_logic(prediction_repository):
    scorer = PredictionScorer(prediction_repository)
    old_time = (datetime.now() - timedelta(seconds=15)).isoformat()

    prediction_id = await prediction_repository.save_prediction(
        {
            "asset": "GC=F",
            "type": "bullish",
            "reasoning": "Test",
            "price": 2000.0,
            "timestamp": old_time,
        }
    )

    mock_market_data = {
        "symbol": "GC=F",
        "price": 2100.0,
        "changePercent": 5.0,
        "timestamp": datetime.now().isoformat(),
    }

    with patch("src.services.scorer.get_market_price", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_market_data
        await scorer.run_scoring_task()

    scored = await prediction_repository.get_prediction(prediction_id)
    assert scored is not None
    assert scored["status"] == "scored"
    assert scored["score"] >= 90


if __name__ == "__main__":
    pytest.main([__file__])
