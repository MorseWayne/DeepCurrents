import pytest
import pytest_asyncio
import os
import asyncio
from src.services.db_service import DBService, NewsRecord

@pytest_asyncio.fixture(scope="function")
async def db_service():
    db_path = "data/test_intel.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = DBService(db_path)
    await db.connect()
    yield db
    await db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

@pytest.mark.asyncio
async def test_save_and_get_news(db_service):
    url = "https://example.com/news1"
    title = "Market rally in Asia"
    content = "Detailed content about the market rally..."
    source = "Reuters"
    
    await db_service.save_news(url, title, content, source, meta={'tier': 1, 'threatLevel': 'high'})
    
    unreported = await db_service.get_unreported_news()
    assert len(unreported) == 1
    assert unreported[0].url == url
    assert unreported[0].title == title
    assert unreported[0].tier == 1
    assert unreported[0].threatLevel == 'high'

@pytest.mark.asyncio
async def test_fuzzy_deduplication(db_service):
    await db_service.save_news(
        "https://example.com/news1", 
        "Global gold prices surge amid tensions", 
        "Content...", 
        "Reuters"
    )
    
    # 完全相同的标题
    assert await db_service.has_similar_title("Global gold prices surge amid tensions") == True
    
    # 稍微不同的措辞（模糊去重应捕获）
    assert await db_service.has_similar_title("Gold prices surge as global tensions rise") == True
    
    # 完全不同的标题
    assert await db_service.has_similar_title("Oil production increases in OPEC") == False

@pytest.mark.asyncio
async def test_mark_as_reported(db_service):
    await db_service.save_news("https://ex.com/1", "Title 1", "Content", "S")
    news = await db_service.get_unreported_news()
    news_id = news[0].id
    
    await db_service.mark_as_reported([news_id])
    unreported = await db_service.get_unreported_news()
    assert len(unreported) == 0

@pytest.mark.asyncio
async def test_save_and_get_prediction(db_service):
    pred_data = {
        'asset': 'GC=F',
        'type': 'bullish',
        'reasoning': 'Inflation rising',
        'price': 2000.5,
        'timestamp': '2026-03-12T12:00:00'
    }
    await db_service.save_prediction(pred_data)
    
    pending = await db_service.get_pending_predictions()
    assert len(pending) == 1
    assert pending[0]['asset_symbol'] == 'GC=F'
    assert pending[0]['base_price'] == 2000.5

if __name__ == "__main__":
    pytest.main([__file__])
