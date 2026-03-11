/**
 * 信息源配置 (Source Configuration)
 * 
 * 借鉴 WorldMonitor 的信息源管理体系：
 * 1. 4 级可信度分级 (Tier 1-4)
 * 2. 源类型标注 (wire/gov/intel/mainstream/market)
 * 3. 宣传风险评估
 * 4. 多维分类
 */

export type SourceType = 'wire' | 'gov' | 'intel' | 'mainstream' | 'market' | 'other';
export type PropagandaRisk = 'low' | 'medium' | 'high';

export interface Source {
  name: string;
  url: string;
  category: string;
  tier: number;         // 1=通讯社, 2=主流大媒, 3=专业领域, 4=聚合/博客
  type: SourceType;
  propagandaRisk?: PropagandaRisk;
  stateAffiliated?: string;
  note?: string;
  isRssHub?: boolean;   // 是否通过 RSSHub 转换的非标源
}

export const SOURCES: Source[] = [
  // ── 地缘政治 & 冲突 (Geopolitics & Conflicts) ──
  { name: 'Reuters World', url: 'https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en', category: 'Geopolitics', tier: 1, type: 'wire' },
  { name: 'AP News', url: 'https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com/article&hl=en-US&gl=US&ceid=US:en', category: 'Geopolitics', tier: 1, type: 'wire' },
  { name: 'BBC World', url: 'https://feeds.bbci.co.uk/news/world/rss.xml', category: 'Geopolitics', tier: 2, type: 'mainstream' },
  { name: 'Guardian World', url: 'https://www.theguardian.com/world/rss', category: 'Geopolitics', tier: 2, type: 'mainstream' },
  { name: 'Al Jazeera', url: 'https://www.aljazeera.com/xml/rss/all.xml', category: 'Geopolitics', tier: 2, type: 'mainstream', propagandaRisk: 'medium', stateAffiliated: 'Qatar' },
  { name: 'France 24', url: 'https://www.france24.com/en/rss', category: 'Geopolitics', tier: 2, type: 'mainstream', propagandaRisk: 'medium', stateAffiliated: 'France' },
  { name: 'Politico Europe', url: 'https://www.politico.eu/feed/', category: 'Geopolitics', tier: 2, type: 'mainstream' },
  { name: 'TASS World', url: 'https://tass.com/rss/v2.xml', category: 'Geopolitics', tier: 2, type: 'mainstream', propagandaRisk: 'high', stateAffiliated: 'Russia' },
  { name: 'Foreign Policy', url: 'https://foreignpolicy.com/feed/', category: 'Geopolitics', tier: 3, type: 'intel' },
  { name: 'Conflict News', url: 'http://feeds.feedburner.com/ConflictNews', category: 'Geopolitics', tier: 3, type: 'intel' },
  { name: 'Defense News', url: 'https://www.defensenews.com/arc/outboundfeeds/rss/?outputType=xml', category: 'Geopolitics', tier: 3, type: 'intel' },

  // ── 经济 & 金融 (Economics & Finance) ──
  { name: 'Bloomberg', url: 'https://news.google.com/rss/search?q=site:bloomberg.com+markets+economy+when:1d&hl=en-US&gl=US&ceid=US:en', category: 'Economics', tier: 1, type: 'wire' },
  { name: 'Reuters Business', url: 'https://news.google.com/rss/search?q=site:reuters.com+business+markets&hl=en-US&gl=US&ceid=US:en', category: 'Economics', tier: 1, type: 'wire' },
  { name: 'CNBC', url: 'https://www.cnbc.com/id/100003114/device/rss/rss.html', category: 'Economics', tier: 2, type: 'market' },
  { name: 'Financial Times', url: 'https://www.ft.com/rss/home', category: 'Economics', tier: 2, type: 'market' },
  { name: 'MarketWatch', url: 'https://news.google.com/rss/search?q=site:marketwatch.com+markets+when:1d&hl=en-US&gl=US&ceid=US:en', category: 'Economics', tier: 2, type: 'market' },
  { name: 'gCaptain', url: 'https://gcaptain.com/feed/', category: 'Economics', tier: 3, type: 'market', note: '航运安全' },
  { name: 'DigiTimes Asia', url: 'https://news.google.com/rss/search?q=site:digitimes.com+semiconductor+OR+TSMC+when:2d&hl=en-US&gl=US&ceid=US:en', category: 'Economics', tier: 3, type: 'market' },

  // ── 政府 & 央行 (Government & Central Banks) ──
  { name: 'Federal Reserve', url: 'https://www.federalreserve.gov/feeds/press_all.xml', category: 'CentralBank', tier: 1, type: 'gov' },
  { name: 'White House', url: 'https://news.google.com/rss/search?q=site:whitehouse.gov&hl=en-US&gl=US&ceid=US:en', category: 'Government', tier: 1, type: 'gov' },
  { name: 'Pentagon', url: 'https://news.google.com/rss/search?q=site:defense.gov+OR+Pentagon&hl=en-US&gl=US&ceid=US:en', category: 'Government', tier: 1, type: 'gov' },

  // ── 智库 & 国际组织 (Think Tanks & International Orgs) ──
  { name: 'CrisisWatch', url: 'https://www.crisisgroup.org/rss', category: 'ThinkTank', tier: 3, type: 'intel' },
  { name: 'UN News', url: 'https://news.google.com/rss/search?q=site:un.org+news+OR+united+nations+when:1d&hl=en-US&gl=US&ceid=US:en', category: 'ThinkTank', tier: 1, type: 'gov' },
  { name: 'WHO News', url: 'https://www.who.int/rss-feeds/news-english.xml', category: 'ThinkTank', tier: 1, type: 'gov' },
  { name: 'Atlantic Council', url: 'https://www.atlanticcouncil.org/feed/', category: 'ThinkTank', tier: 3, type: 'intel' },
  { name: 'Brookings', url: 'https://news.google.com/rss/search?q=site:brookings.edu+when:7d&hl=en-US&gl=US&ceid=US:en', category: 'ThinkTank', tier: 3, type: 'intel' },
  { name: 'IAEA', url: 'https://www.iaea.org/feeds/topnews', category: 'ThinkTank', tier: 1, type: 'gov', note: '可能无摘要，需全文提取' },

  // ── 能源 & 大宗商品 (Energy & Commodities) ──
  { name: 'Oil & Gas', url: 'https://news.google.com/rss/search?q=(oil+price+OR+OPEC+OR+"natural+gas"+OR+pipeline+OR+LNG)+when:2d&hl=en-US&gl=US&ceid=US:en', category: 'Energy', tier: 3, type: 'market' },
  { name: 'Nuclear Energy', url: 'https://news.google.com/rss/search?q=("nuclear+energy"+OR+"nuclear+power"+OR+uranium+OR+IAEA)+when:3d&hl=en-US&gl=US&ceid=US:en', category: 'Energy', tier: 3, type: 'market' },

  // ── 网络安全 & 技术 (Cybersecurity & Tech) ──
  { name: 'CISA Advisories', url: 'https://www.cisa.gov/cybersecurity-advisories/all.xml', category: 'Cyber', tier: 1, type: 'gov' },
  { name: 'MIT Tech Review', url: 'https://www.technologyreview.com/feed/', category: 'Cyber', tier: 3, type: 'intel' },

  // ── 亚太地区 (Asia-Pacific) ──
  { name: 'BBC Asia', url: 'https://feeds.bbci.co.uk/news/world/asia/rss.xml', category: 'AsiaPacific', tier: 2, type: 'mainstream' },
  { name: 'Nikkei Asia', url: 'https://news.google.com/rss/search?q=site:asia.nikkei.com+when:3d&hl=en-US&gl=US&ceid=US:en', category: 'AsiaPacific', tier: 2, type: 'market' },

  // ── 🔌 RSSHub 扩展源 (万能抓取 - 推荐自建以规避 403) ──
  { 
    name: 'Intel Slava Z', 
    url: 'https://rsshub.app/telegram/channel/intelslava', 
    category: 'Geopolitics', tier: 3, type: 'intel', isRssHub: true 
  },
  { 
    name: 'Liveuamap TG', 
    url: 'https://rsshub.app/telegram/channel/liveuamap', 
    category: 'Geopolitics', tier: 1, type: 'wire', isRssHub: true 
  },
  { 
    name: '华尔街见闻实时', 
    url: 'https://rsshub.app/wallstreetcn/news/global', 
    category: 'Economics', tier: 2, type: 'market', isRssHub: true 
  },

  // ── 🔌 RSSHub 扩展: 地缘 Telegram 频道 ──
  { name: 'NEXTA Live', url: 'https://rsshub.app/telegram/channel/nexta_live', category: 'Geopolitics', tier: 2, type: 'wire', isRssHub: true },
  { name: 'Rybar', url: 'https://rsshub.app/telegram/channel/ryaboronka', category: 'Geopolitics', tier: 3, type: 'intel', isRssHub: true, propagandaRisk: 'high', stateAffiliated: 'Russia' },
  { name: 'War Monitor', url: 'https://rsshub.app/telegram/channel/warmonitor3', category: 'Geopolitics', tier: 3, type: 'intel', isRssHub: true },
  { name: 'South China Sea Wave', url: 'https://rsshub.app/telegram/channel/SouthChinaSeaWave', category: 'AsiaPacific', tier: 3, type: 'intel', isRssHub: true },

  // ── 🔌 RSSHub 扩展: 中文财经 ──
  { name: '财联社电报', url: 'https://rsshub.app/cls/telegraph', category: 'Economics', tier: 2, type: 'market', isRssHub: true },
  { name: '金十数据', url: 'https://rsshub.app/jin10/flash', category: 'Economics', tier: 2, type: 'market', isRssHub: true },
  { name: '格隆汇', url: 'https://rsshub.app/gelonghui/live', category: 'Economics', tier: 3, type: 'market', isRssHub: true },

  // ── 🔌 RSSHub 扩展: 亚太 & 中文媒体 ──
  { name: '联合早报', url: 'https://rsshub.app/zaobao/realtime/world', category: 'AsiaPacific', tier: 2, type: 'mainstream', isRssHub: true },
  { name: '财新网', url: 'https://rsshub.app/caixin/latest', category: 'Economics', tier: 2, type: 'mainstream', isRssHub: true },

  // ── 🔌 RSSHub 扩展: Telegram 新闻频道 (来源: itgoyo/TelegramGroup) ──
  { name: '竹新社', url: 'https://rsshub.app/telegram/channel/tnews365', category: 'Geopolitics', tier: 2, type: 'mainstream', isRssHub: true, note: '高质量中文新闻聚合' },
  { name: '乌鸦观察', url: 'https://rsshub.app/telegram/channel/bigcrowdev', category: 'AsiaPacific', tier: 3, type: 'intel', isRssHub: true, note: '中国政治社会事件监测' },
  { name: '7×24投资快讯', url: 'https://rsshub.app/telegram/channel/golden_wind_news', category: 'Economics', tier: 3, type: 'market', isRssHub: true },
  { name: '中国数字时代', url: 'https://rsshub.app/telegram/channel/cdtchinesefeed', category: 'AsiaPacific', tier: 3, type: 'intel', isRssHub: true, note: '中国审查与政策追踪' },
  { name: 'Solidot', url: 'https://rsshub.app/telegram/channel/solidot', category: 'Cyber', tier: 3, type: 'intel', isRssHub: true, note: '中文科技资讯' },
  { name: '路透中文', url: 'https://rsshub.app/telegram/channel/lutouzhongwen_rss', category: 'Geopolitics', tier: 1, type: 'wire', isRssHub: true },
  { name: 'BBC中文', url: 'https://rsshub.app/telegram/channel/bbczhongwen_rss', category: 'Geopolitics', tier: 2, type: 'mainstream', isRssHub: true },
  { name: 'FT中文网', url: 'https://rsshub.app/telegram/channel/ftzhongwen_rss', category: 'Economics', tier: 2, type: 'market', isRssHub: true },
  { name: '新闻联播', url: 'https://rsshub.app/telegram/channel/CCTVNewsBroadcast', category: 'Government', tier: 2, type: 'gov', isRssHub: true, propagandaRisk: 'high', stateAffiliated: 'China', note: '追踪PRC官方叙事' },

  // ── 🐦 RSSHub 扩展: Twitter/X 关键人物 (需自建RSSHub+Twitter API) ──
  // 维度1: 地缘政治 & 关键政治人物
  { name: 'Elon Musk', url: 'https://rsshub.app/twitter/user/elonmusk', category: 'Geopolitics', tier: 2, type: 'other', isRssHub: true, note: '市场推动者，AI/星链/DOGE政策' },
  { name: 'Nayib Bukele', url: 'https://rsshub.app/twitter/user/nayibbukele', category: 'Geopolitics', tier: 2, type: 'gov', isRssHub: true, note: '萨尔瓦多总统，BTC法定化先驱' },
  { name: 'Javier Milei', url: 'https://rsshub.app/twitter/user/JMilei', category: 'Economics', tier: 2, type: 'gov', isRssHub: true, note: '阿根廷总统，激进经济改革' },
  { name: 'Donald Trump', url: 'https://rsshub.app/twitter/user/realDonaldTrump', category: 'Geopolitics', tier: 1, type: 'gov', isRssHub: true, note: '美国贸易/关税/制裁政策' },

  // 维度2: 宏观策略 & 货币政策思想家
  { name: 'Arthur Hayes', url: 'https://rsshub.app/twitter/user/CryptoHayes', category: 'Economics', tier: 3, type: 'intel', isRssHub: true, note: '央行政策/美元霸权/日元套利宏观分析' },
  { name: 'Balaji Srinivasan', url: 'https://rsshub.app/twitter/user/balajis', category: 'Geopolitics', tier: 3, type: 'intel', isRssHub: true, note: '网络国家论/宏观科技地缘预测' },
  { name: 'Cathie Wood', url: 'https://rsshub.app/twitter/user/CathieDWood', category: 'Economics', tier: 3, type: 'market', isRssHub: true, note: 'ARK颠覆性创新+货币政策分析' },
  { name: 'Michael Saylor', url: 'https://rsshub.app/twitter/user/saylor', category: 'Economics', tier: 3, type: 'market', isRssHub: true, note: '企业金库策略/货币贬值论' },
  { name: 'Jeremy Allaire', url: 'https://rsshub.app/twitter/user/jerallaire', category: 'Economics', tier: 3, type: 'market', isRssHub: true, note: 'Circle/USDC稳定币监管与全球支付' },

  // 维度3: 金融监管 & 政策追踪
  { name: 'Coin Center', url: 'https://rsshub.app/twitter/user/coincenter', category: 'Government', tier: 3, type: 'intel', isRssHub: true, note: '华盛顿DC金融政策智库' },
  { name: 'Jake Chervinsky', url: 'https://rsshub.app/twitter/user/jchervinsky', category: 'Government', tier: 3, type: 'intel', isRssHub: true, note: '实时跟踪美国国会金融法案' },
  { name: 'Hester Peirce', url: 'https://rsshub.app/twitter/user/HesterPeirce', category: 'Government', tier: 2, type: 'gov', isRssHub: true, note: 'SEC委员，监管政策信号' },
  { name: 'Sen. Warren', url: 'https://rsshub.app/twitter/user/SenWarren', category: 'Government', tier: 2, type: 'gov', isRssHub: true, note: '参议员，金融监管鹰派风向标' },

  // 维度4: AI & 科技前沿
  { name: 'Sam Altman', url: 'https://rsshub.app/twitter/user/sama', category: 'Cyber', tier: 2, type: 'intel', isRssHub: true, note: 'OpenAI CEO，AI治理与产业政策' },
  { name: 'Jack Dorsey', url: 'https://rsshub.app/twitter/user/jack', category: 'Cyber', tier: 3, type: 'intel', isRssHub: true, note: 'Block支付/去中心化社交/Lightning' },

  // 维度5: 亚洲 & 中国情报
  { name: 'Wu Blockchain', url: 'https://rsshub.app/twitter/user/WuBlockchain', category: 'AsiaPacific', tier: 2, type: 'intel', isRssHub: true, note: '中国金融政策双语快讯' },
  { name: 'Dovey Wan', url: 'https://rsshub.app/twitter/user/DoveyWan', category: 'AsiaPacific', tier: 3, type: 'intel', isRssHub: true, note: '中国市场跨文化洞察' },
  { name: 'SlowMist余弦', url: 'https://rsshub.app/twitter/user/eaboricua', category: 'Cyber', tier: 3, type: 'intel', isRssHub: true, note: '链上安全事件与漏洞预警' },

  // 维度6: 链上宏观数据
  { name: 'Glassnode', url: 'https://rsshub.app/twitter/user/glassnode', category: 'Economics', tier: 3, type: 'market', isRssHub: true, note: '链上宏观指标与资金流图表' },
  { name: 'CryptoQuant', url: 'https://rsshub.app/twitter/user/cryptoquant_com', category: 'Economics', tier: 3, type: 'market', isRssHub: true, note: '交易所资金流与矿工行为监控' },

  // ── 🔌 RSSHub 扩展: 博客/Substack/独立媒体 ──
  { name: 'Arthur Hayes Blog', url: 'https://cryptohayes.substack.com/feed', category: 'Economics', tier: 3, type: 'intel', note: '深度宏观长文，比Twitter更有价值' },
  { name: 'Kyiv Independent', url: 'https://news.google.com/rss/search?q=site:kyivindependent.com+when:3d&hl=en-US&gl=US&ceid=US:en', category: 'Geopolitics', tier: 2, type: 'mainstream' },
  { name: 'Nick Timiraos (WSJ Fed)', url: 'https://news.google.com/rss/search?q="Nick+Timiraos"+OR+site:wsj.com+%22Nick+Timiraos%22+when:2d&hl=en-US&gl=US&ceid=US:en', category: 'CentralBank', tier: 2, type: 'wire', note: '美联储政策第一信号人' },
];

// ── 工具函数 ──

export function resolveSourceUrl(source: Source): string {
  if (source.isRssHub && process.env.RSSHUB_BASE_URL) {
    return source.url.replace('https://rsshub.app', process.env.RSSHUB_BASE_URL);
  }
  return source.url;
}

export function getSourceTier(sourceName: string): number {
  const source = SOURCES.find(s => s.name === sourceName);
  return source?.tier ?? 4;
}

export function getSourceType(sourceName: string): SourceType {
  const source = SOURCES.find(s => s.name === sourceName);
  return source?.type ?? 'other';
}

export function getSourcePropagandaRisk(sourceName: string): PropagandaRisk {
  const source = SOURCES.find(s => s.name === sourceName);
  return source?.propagandaRisk ?? 'low';
}

export function isStateAffiliated(sourceName: string): boolean {
  const source = SOURCES.find(s => s.name === sourceName);
  return !!source?.stateAffiliated;
}

export function getSourcesByCategory(category: string): Source[] {
  return SOURCES.filter(s => s.category === category);
}

export function getCategories(): string[] {
  return [...new Set(SOURCES.map(s => s.category))];
}

export function getHighQualitySources(): Source[] {
  return SOURCES.filter(s => s.tier <= 2);
}
