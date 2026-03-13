import pytest
import pytest_asyncio

from src.services.prediction_repository import PredictionRepository


@pytest_asyncio.fixture
async def prediction_repository(tmp_path):
    repository = PredictionRepository(str(tmp_path / "predictions.db"))
    await repository.connect()
    yield repository
    await repository.close()


@pytest.mark.asyncio
async def test_prediction_repository_saves_and_lists_pending_predictions(
    prediction_repository,
):
    prediction_id = await prediction_repository.save_prediction(
        {
            "asset": "GC=F",
            "type": "bullish",
            "reasoning": "Inflation hedge",
            "price": 2500.0,
            "timestamp": "2026-03-12T12:00:00",
        }
    )

    pending = await prediction_repository.get_pending_predictions()

    assert len(pending) == 1
    assert pending[0]["id"] == prediction_id
    assert pending[0]["asset_symbol"] == "GC=F"
    assert pending[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_prediction_repository_updates_scores(prediction_repository):
    prediction_id = await prediction_repository.save_prediction(
        {
            "asset": "CL=F",
            "type": "bearish",
            "reasoning": "Demand destruction",
            "price": 80.0,
            "timestamp": "2026-03-12T12:00:00",
        }
    )

    await prediction_repository.update_prediction_score(prediction_id, 91.0, 75.0)

    stored = await prediction_repository.get_prediction(prediction_id)
    assert stored is not None
    assert stored["status"] == "scored"
    assert stored["score"] == 91.0
    assert stored["actual_price"] == 75.0


if __name__ == "__main__":
    pytest.main([__file__])
