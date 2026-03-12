import pytest
import pytest_asyncio
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.scorer import PredictionScorer
from src.services.db_service import DBService

@pytest_asyncio.fixture
async def db_service():
    db_path = "data/test_scorer.db"
    if os.path.exists(db_path): os.remove(db_path)
    db = DBService(db_path)
    await db.connect()
    yield db
    await db.close()
    if os.path.exists(db_path): os.remove(db_path)

@pytest.mark.asyncio
async def test_scoring_logic(db_service):
    scorer = PredictionScorer(db_service)
    
    # 插入一条待评分记录（15秒前，以绕过 10s 检查）
    from datetime import datetime, timedelta
    old_time = (datetime.now() - timedelta(seconds=15)).isoformat()
    
    await db_service.save_prediction({
        'asset': 'GC=F',
        'type': 'bullish',
        'reasoning': 'Test',
        'price': 2000.0,
        'timestamp': old_time
    })

    # Mock 市场价格
    mock_market_data = {
        'symbol': 'GC=F',
        'price': 2100.0, # 涨了 5%
        'changePercent': 5.0,
        'timestamp': datetime.now().isoformat()
    }

    with patch('src.services.scorer.get_market_price', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_market_data
        await scorer.run_scoring_task()
        
        # 验证数据库是否已更新
        async with db_service._db.execute("SELECT score, status FROM predictions LIMIT 1") as cursor:
            row = await cursor.fetchone()
            assert row['status'] == 'scored'
            assert row['score'] >= 90 # 看涨且大涨，应得高分

if __name__ == "__main__":
    pytest.main([__file__])
