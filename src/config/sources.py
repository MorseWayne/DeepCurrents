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

    # ── 智库 & 国际组织 (Think Tanks & International Orgs) ──
    Source(name='CrisisWatch', url='https://www.crisisgroup.org/rss', category='ThinkTank', tier=3, type='intel'),
    Source(name='UN News', url='https://news.google.com/rss/search?q=site:un.org+news+OR+united+nations+when:1d&hl=en-US&gl=US&ceid=US:en', category='ThinkTank', tier=1, type='gov'),
    Source(name='WHO News', url='https://www.who.int/rss-feeds/news-english.xml', category='ThinkTank', tier=1, type='gov'),
    Source(name='Atlantic Council', url='https://www.atlanticcouncil.org/feed/', category='ThinkTank', tier=3, type='intel'),
    Source(name='Brookings', url='https://news.google.com/rss/search?q=site:brookings.edu+when:7d&hl=en-US&gl=US&ceid=US:en', category='ThinkTank', tier=3, type='intel'),
    Source(name='IAEA', url='https://www.iaea.org/feeds/topnews', category='ThinkTank', tier=1, type='gov', note='可能无摘要，需全文提取'),

    # ── 能源 & 大宗商品 (Energy & Commodities) ──
    Source(name='Oil & Gas', url='https://news.google.com/rss/search?q=(oil+price+OR+OPEC+OR+"natural+gas"+OR+pipeline+OR+LNG)+when:2d&hl=en-US&gl=US&ceid=US:en', category='Energy', tier=3, type='market'),
    Source(name='Nuclear Energy', url='https://news.google.com/rss/search?q=("nuclear+energy"+OR+"nuclear+power"+OR+uranium+OR+IAEA)+when:3d&hl=en-US&gl=US&ceid=US:en', category='Energy', tier=3, type='market'),

    # ── 网络安全 & 技术 (Cybersecurity & Tech) ──
    Source(name='CISA Advisories', url='https://www.cisa.gov/cybersecurity-advisories/all.xml', category='Cyber', tier=1, type='gov'),
    Source(name='MIT Tech Review', url='https://www.technologyreview.com/feed/', category='Cyber', tier=3, type='intel'),

    # ── 亚太地区 (Asia-Pacific) ──
    Source(name='BBC Asia', url='https://feeds.bbci.co.uk/news/world/asia/rss.xml', category='AsiaPacific', tier=2, type='mainstream'),
    Source(name='Nikkei Asia', url='https://news.google.com/rss/search?q=site:asia.nikkei.com+when:3d&hl=en-US&gl=US&ceid=US:en', category='AsiaPacific', tier=2, type='market'),

    # ── 🔌 RSSHub 扩展源 (万能抓取 - 推荐自建以规避 403) ──
    Source(name='Intel Slava Z', url='https://rsshub.app/telegram/channel/intelslava', category='Geopolitics', tier=3, type='intel', is_rss_hub=True),
    Source(name='Liveuamap TG', url='https://rsshub.app/telegram/channel/liveuamap', category='Geopolitics', tier=1, type='wire', is_rss_hub=True),
    Source(name='华尔街见闻实时', url='https://rsshub.app/wallstreetcn/news/global', category='Economics', tier=2, type='market', is_rss_hub=True),

    # ── 🔌 RSSHub 扩展: 地缘 Telegram 频道 ──
    Source(name='NEXTA Live', url='https://rsshub.app/telegram/channel/nexta_live', category='Geopolitics', tier=2, type='wire', is_rss_hub=True),

    # ── 🔌 RSSHub 扩展: 中文财经 ──
    Source(name='财联社电报', url='https://rsshub.app/cls/telegraph', category='Economics', tier=2, type='market', is_rss_hub=True),
    Source(name='金十数据', url='https://rsshub.app/jin10', category='Economics', tier=2, type='market', is_rss_hub=True, note='flash 路由易空数据返回 503，改用稳定主路由'),
    Source(name='格隆汇', url='https://rsshub.app/gelonghui/live', category='Economics', tier=3, type='market', is_rss_hub=True),

    # ── 🔌 RSSHub 扩展: 亚太 & 中文媒体 ──
    Source(name='联合早报', url='https://rsshub.app/zaobao/realtime/world', category='AsiaPacific', tier=2, type='mainstream', is_rss_hub=True),
    Source(name='财新网', url='https://rsshub.app/caixin/latest', category='Economics', tier=2, type='mainstream', is_rss_hub=True),

    # ── 🔌 RSSHub 扩展: Telegram 新闻频道 ──
    Source(name='竹新社', url='https://rsshub.app/telegram/channel/tnews365', category='Geopolitics', tier=2, type='mainstream', is_rss_hub=True, note='高质量中文新闻聚合'),
    Source(name='乌鸦观察', url='https://rsshub.app/telegram/channel/bigcrowdev', category='AsiaPacific', tier=3, type='intel', is_rss_hub=True, note='中国政治社会事件监测'),
    Source(name='7×24投资快讯', url='https://rsshub.app/telegram/channel/golden_wind_news', category='Economics', tier=3, type='market', is_rss_hub=True),
    Source(name='中国数字时代', url='https://rsshub.app/telegram/channel/cdtchinesefeed', category='AsiaPacific', tier=3, type='intel', is_rss_hub=True, note='中国审查与政策追踪'),
    Source(name='Solidot', url='https://rsshub.app/telegram/channel/solidot', category='Cyber', tier=3, type='intel', is_rss_hub=True, note='中文科技资讯'),
    Source(name='路透中文', url='https://rsshub.app/telegram/channel/lutouzhongwen_rss', category='Geopolitics', tier=1, type='wire', is_rss_hub=True),
    Source(name='BBC中文', url='https://rsshub.app/telegram/channel/bbczhongwen_rss', category='Geopolitics', tier=2, type='mainstream', is_rss_hub=True),
    Source(name='FT中文网', url='https://rsshub.app/telegram/channel/ftzhongwen_rss', category='Economics', tier=2, type='market', is_rss_hub=True),
    Source(name='新闻联播', url='https://rsshub.app/telegram/channel/CCTVNewsBroadcast', category='Government', tier=2, type='gov', is_rss_hub=True, propaganda_risk='high', state_affiliated='China', note='追踪PRC官方叙事'),

    # ── 🐦 RSSHub 扩展: Twitter/X 关键人物 (需自建RSSHub+Twitter API) ──
    Source(name='Elon Musk', url='https://rsshub.app/twitter/user/elonmusk', category='Geopolitics', tier=2, type='other', is_rss_hub=True, note='市场推动者，AI/星链/DOGE政策'),
    Source(name='Nayib Bukele', url='https://rsshub.app/twitter/user/nayibbukele', category='Geopolitics', tier=2, type='gov', is_rss_hub=True, note='萨尔瓦多总统，BTC法定化先驱'),
    Source(name='Javier Milei', url='https://rsshub.app/twitter/user/JMilei', category='Economics', tier=2, type='gov', is_rss_hub=True, note='阿根廷总统，激进经济改革'),
    Source(name='Donald Trump', url='https://rsshub.app/twitter/user/realDonaldTrump', category='Geopolitics', tier=1, type='gov', is_rss_hub=True, note='美国贸易/关税/制裁政策'),
    Source(name='Arthur Hayes', url='https://rsshub.app/twitter/user/CryptoHayes', category='Economics', tier=3, type='intel', is_rss_hub=True, note='央行政策/美元霸权/日元套利宏观分析'),
    Source(name='Balaji Srinivasan', url='https://rsshub.app/twitter/user/balajis', category='Geopolitics', tier=3, type='intel', is_rss_hub=True, note='网络国家论/宏观科技地缘预测'),
    Source(name='Cathie Wood', url='https://rsshub.app/twitter/user/CathieDWood', category='Economics', tier=3, type='market', is_rss_hub=True, note='ARK颠覆性创新+货币政策分析'),
    Source(name='Michael Saylor', url='https://rsshub.app/twitter/user/saylor', category='Economics', tier=3, type='market', is_rss_hub=True, note='企业金库策略/货币贬值论'),
    Source(name='Jeremy Allaire', url='https://rsshub.app/twitter/user/jerallaire', category='Economics', tier=3, type='market', is_rss_hub=True, note='Circle/USDC稳定币监管与全球支付'),
    Source(name='Coin Center', url='https://rsshub.app/twitter/user/coincenter', category='Government', tier=3, type='intel', is_rss_hub=True, note='华盛顿DC金融政策智库'),
    Source(name='Jake Chervinsky', url='https://rsshub.app/twitter/user/jchervinsky', category='Government', tier=3, type='intel', is_rss_hub=True, note='实时跟踪美国国会金融法案'),
    Source(name='Hester Peirce', url='https://rsshub.app/twitter/user/HesterPeirce', category='Government', tier=2, type='gov', is_rss_hub=True, note='SEC委员，监管政策信号'),
    Source(name='Sen. Warren', url='https://rsshub.app/twitter/user/SenWarren', category='Government', tier=2, type='gov', is_rss_hub=True, note='参议员，金融监管鹰派风向标'),
    Source(name='Sam Altman', url='https://rsshub.app/twitter/user/sama', category='Cyber', tier=2, type='intel', is_rss_hub=True, note='OpenAI CEO，AI治理与产业政策'),
    Source(name='Jack Dorsey', url='https://rsshub.app/twitter/user/jack', category='Cyber', tier=3, type='intel', is_rss_hub=True, note='Block支付/去中心化社交/Lightning'),
    Source(name='Wu Blockchain', url='https://rsshub.app/twitter/user/WuBlockchain', category='AsiaPacific', tier=2, type='intel', is_rss_hub=True, note='中国金融政策双语快讯'),
    Source(name='Dovey Wan', url='https://rsshub.app/twitter/user/DoveyWan', category='AsiaPacific', tier=3, type='intel', is_rss_hub=True, note='中国市场跨文化洞察'),
    Source(name='Glassnode', url='https://rsshub.app/twitter/user/glassnode', category='Economics', tier=3, type='market', is_rss_hub=True, note='链上宏观指标与资金流图表'),
    Source(name='CryptoQuant', url='https://rsshub.app/twitter/user/cryptoquant_com', category='Economics', tier=3, type='market', is_rss_hub=True, note='交易所资金流与矿工行为监控'),

    # ── 🔌 RSSHub 扩展: 博客/Substack/独立媒体 ──
    Source(name='Arthur Hayes Blog', url='https://cryptohayes.substack.com/feed', category='Economics', tier=3, type='intel', note='深度宏观长文，比Twitter更有价值'),
    Source(name='Kyiv Independent', url='https://news.google.com/rss/search?q=site:kyivindependent.com+when:3d&hl=en-US&gl=US&ceid=US:en', category='Geopolitics', tier=2, type='mainstream'),
    Source(name='Nick Timiraos (WSJ Fed)', url='https://news.google.com/rss/search?q="Nick+Timiraos"+OR+site:wsj.com+%22Nick+Timiraos%22+when:2d&hl=en-US&gl=US&ceid=US:en', category='CentralBank', tier=2, type='wire', note='美联储政策第一信号人'),
]

def resolve_source_url(source: Source) -> str:
    from .settings import CONFIG
    if source.is_rss_hub and CONFIG.rsshub_base_url:
        return source.url.replace('https://rsshub.app', CONFIG.rsshub_base_url.rstrip('/'))
    return source.url

def get_source_tier(source_name: str) -> int:
    source = next((s for s in SOURCES if s.name == source_name), None)
    return source.tier if source else 4

def get_source_type(source_name: str) -> SourceType:
    source = next((s for s in SOURCES if s.name == source_name), None)
    return source.type if source else 'other'

def get_source_propaganda_risk(source_name: str) -> PropagandaRisk:
    source = next((s for s in SOURCES if s.name == source_name), None)
    return source.propaganda_risk if source else 'low'

def is_state_affiliated(source_name: str) -> bool:
    source = next((s for s in SOURCES if s.name == source_name), None)
    return bool(source and source.state_affiliated)

def get_sources_by_category(category: str) -> List[Source]:
    return [s for s in SOURCES if s.category == category]

def get_categories() -> List[str]:
    return list(set(s.category for s in SOURCES))

def get_high_quality_sources() -> List[Source]:
    return [s for s in SOURCES if s.tier <= 2]
