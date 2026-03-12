import os
from typing import List, Optional, Literal
from pydantic import BaseModel

SourceType = Literal['wire', 'gov', 'intel', 'mainstream', 'market', 'other']
PropagandaRisk = Literal['low', 'medium', 'high']

class Source(BaseModel):
    name: str
    url: str
    category: str
    tier: int         # 1=通讯社, 2=主流大媒, 3=专业领域, 4=聚合/博客
    type: SourceType
    propaganda_risk: PropagandaRisk = 'low'
    state_affiliated: Optional[str] = None
    note: Optional[str] = None
    is_rss_hub: bool = False

SOURCES: List[Source] = [
    # ── 地缘政治 & 冲突 (Geopolitics & Conflicts) ──
    Source(name='Reuters World', url='https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en', category='Geopolitics', tier=1, type='wire'),
    Source(name='AP News', url='https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com/article&hl=en-US&gl=US&ceid=US:en', category='Geopolitics', tier=1, type='wire'),
    Source(name='BBC World', url='https://feeds.bbci.co.uk/news/world/rss.xml', category='Geopolitics', tier=2, type='mainstream'),
    Source(name='Guardian World', url='https://www.theguardian.com/world/rss', category='Geopolitics', tier=2, type='mainstream'),
    Source(name='Al Jazeera', url='https://www.aljazeera.com/xml/rss/all.xml', category='Geopolitics', tier=2, type='mainstream', propaganda_risk='medium', state_affiliated='Qatar'),
    Source(name='France 24', url='https://www.france24.com/en/rss', category='Geopolitics', tier=2, type='mainstream', propaganda_risk='medium', state_affiliated='France'),
    Source(name='Politico Europe', url='https://www.politico.eu/feed/', category='Geopolitics', tier=2, type='mainstream'),
    Source(name='TASS World', url='https://tass.com/rss/v2.xml', category='Geopolitics', tier=2, type='mainstream', propaganda_risk='high', state_affiliated='Russia'),
    Source(name='Foreign Policy', url='https://foreignpolicy.com/feed/', category='Geopolitics', tier=3, type='intel'),
    Source(name='Conflict News', url='http://feeds.feedburner.com/ConflictNews', category='Geopolitics', tier=3, type='intel'),
    Source(name='Defense News', url='https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml', category='Geopolitics', tier=3, type='intel'),

    # ── 经济 & 金融 (Economics & Finance) ──
    Source(name='Bloomberg', url='https://news.google.com/rss/search?q=site:bloomberg.com+markets+economy+when:1d&hl=en-US&gl=US&ceid=US:en', category='Economics', tier=1, type='wire'),
    Source(name='Reuters Business', url='https://news.google.com/rss/search?q=site:reuters.com+business+markets&hl=en-US&gl=US&ceid=US:en', category='Economics', tier=1, type='wire'),
    Source(name='CNBC', url='https://www.cnbc.com/id/100003114/device/rss/rss.html', category='Economics', tier=2, type='market'),
    Source(name='Financial Times', url='https://www.ft.com/rss/home', category='Economics', tier=2, type='market'),
    Source(name='MarketWatch', url='https://news.google.com/rss/search?q=site:marketwatch.com+markets+when:1d&hl=en-US&gl=US&ceid=US:en', category='Economics', tier=2, type='market'),
    Source(name='gCaptain', url='https://gcaptain.com/feed/', category='Economics', tier=3, type='market', note='航运安全'),
    Source(name='DigiTimes Asia', url='https://news.google.com/rss/search?q=site:digitimes.com+semiconductor+OR+TSMC+when:2d&hl=en-US&gl=US&ceid=US:en', category='Economics', tier=3, type='market'),

    # ── 政府 & 央行 (Government & Central Banks) ──
    Source(name='Federal Reserve', url='https://www.federalreserve.gov/feeds/press_all.xml', category='CentralBank', tier=1, type='gov'),
    Source(name='White House', url='https://news.google.com/rss/search?q=site:whitehouse.gov&hl=en-US&gl=US&ceid=US:en', category='Government', tier=1, type='gov'),
    Source(name='Pentagon', url='https://news.google.com/rss/search?q=site:defense.gov+OR+Pentagon&hl=en-US&gl=US&ceid=US:en', category='Government', tier=1, type='gov'),

    # 智库等略 (实际代码中应补全)
    Source(name='CrisisWatch', url='https://www.crisisgroup.org/rss', category='ThinkTank', tier=3, type='intel'),
]

def resolve_source_url(source: Source) -> str:
    rsshub_base = os.getenv('RSSHUB_BASE_URL')
    if source.is_rss_hub and rsshub_base:
        return source.url.replace('https://rsshub.app', rsshub_base)
    return source.url
