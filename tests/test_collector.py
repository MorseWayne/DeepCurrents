import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.services.collector import RSSCollector
from src.config.sources import Source

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.has_news = AsyncMock(return_value=False)
    db.has_similar_title = AsyncMock(return_value=False)
    db.save_news = AsyncMock(return_value=True)
    return db

@pytest.mark.asyncio
async def test_fetch_source_success(mock_db):
    collector = RSSCollector(mock_db)
    source = Source(name='Test Source', url='http://mock.rss', category='Test', tier=1, type='wire')
    
    mock_rss_content = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0">
    <channel>
      <title>Mock RSS</title>
      <item>
        <title>News 1</title>
        <link>http://news1.com</link>
        <description>Content 1</description>
      </item>
    </channel>
    </rss>"""

    with patch('aiohttp.ClientSession.get') as mock_get:
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text.return_value = mock_rss_content
        mock_get.return_value.__aenter__.return_value = mock_response
        
        result = await collector.fetch_source(source)
        
        assert result['new_count'] == 1
        mock_db.save_news.assert_called_once()

@pytest.mark.asyncio
async def test_circuit_breaker_cooldown(mock_db):
    collector = RSSCollector(mock_db)
    source = Source(name='Failure Source', url='http://fail.rss', category='Test', tier=1, type='wire')
    
    # 模拟连续失败
    with patch('aiohttp.ClientSession.get', side_effect=Exception("Network Error")):
        for _ in range(3):
            await collector.fetch_source(source)
    
    # 此时应进入冷却
    result = await collector.fetch_source(source)
    assert result.get('skipped') == True

if __name__ == "__main__":
    pytest.main([__file__])
