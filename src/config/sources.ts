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
}

// ── 信息源分级系统 ──
// Tier 1: 通讯社 - 最快、最可靠的突发新闻
// Tier 2: 主流媒体 - 高质量新闻报道
// Tier 3: 专业领域 - 深度专业分析
// Tier 4: 聚合器/博客 - 有用但权威性较低

export const SOURCES: Source[] = [
  // ── 地缘政治 & 冲突 (Geopolitics & Conflicts) ──
  
  // Tier 1 - 通讯社
  { name: 'Reuters World', url: 'https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en', category: 'Geopolitics', tier: 1, type: 'wire', propagandaRisk: 'low', note: '通讯社，严格编辑标准' },
  { name: 'AP News', url: 'https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com/article&hl=en-US&gl=US&ceid=US:en', category: 'Geopolitics', tier: 1, type: 'wire', propagandaRisk: 'low', note: '通讯社，非营利合作社' },
  
  // Tier 2 - 主流媒体
  { name: 'BBC World', url: 'https://feeds.bbci.co.uk/news/world/rss.xml', category: 'Geopolitics', tier: 2, type: 'mainstream', propagandaRisk: 'low', note: '公共广播，编辑独立章程' },
  { name: 'Guardian World', url: 'https://www.theguardian.com/world/rss', category: 'Geopolitics', tier: 2, type: 'mainstream', propagandaRisk: 'low' },
  { name: 'Al Jazeera', url: 'https://www.aljazeera.com/xml/rss/all.xml', category: 'Geopolitics', tier: 2, type: 'mainstream', propagandaRisk: 'medium', stateAffiliated: 'Qatar', note: '卡塔尔资助，编辑独立' },
  { name: 'France 24', url: 'https://www.france24.com/en/rss', category: 'Geopolitics', tier: 2, type: 'mainstream', propagandaRisk: 'medium', stateAffiliated: 'France' },
  
  // Tier 3 - 专业领域
  { name: 'Foreign Policy', url: 'https://foreignpolicy.com/feed/', category: 'Geopolitics', tier: 3, type: 'intel' },
  { name: 'Conflict News', url: 'http://feeds.feedburner.com/ConflictNews', category: 'Geopolitics', tier: 3, type: 'intel' },

  // ── 中东 & 特色地区 (Middle East & Regional) ──
  { name: 'BBC Middle East', url: 'https://feeds.bbci.co.uk/news/world/middle_east/rss.xml', category: 'MiddleEast', tier: 2, type: 'mainstream' },
  { name: 'Guardian ME', url: 'https://www.theguardian.com/world/middleeast/rss', category: 'MiddleEast', tier: 2, type: 'mainstream' },

  // ── 经济 & 金融 (Economics & Finance) ──
  
  // Tier 1
  { name: 'Bloomberg', url: 'https://news.google.com/rss/search?q=site:bloomberg.com+markets+economy+when:1d&hl=en-US&gl=US&ceid=US:en', category: 'Economics', tier: 1, type: 'wire' },
  { name: 'Reuters Business', url: 'https://news.google.com/rss/search?q=site:reuters.com+business+markets&hl=en-US&gl=US&ceid=US:en', category: 'Economics', tier: 1, type: 'wire' },
  
  // Tier 2
  { name: 'CNBC', url: 'https://www.cnbc.com/id/100003114/device/rss/rss.html', category: 'Economics', tier: 2, type: 'market' },
  { name: 'Financial Times', url: 'https://www.ft.com/rss/home', category: 'Economics', tier: 2, type: 'market' },
  { name: 'MarketWatch', url: 'https://news.google.com/rss/search?q=site:marketwatch.com+markets+when:1d&hl=en-US&gl=US&ceid=US:en', category: 'Economics', tier: 2, type: 'market' },
  
  // Tier 4
  { name: 'Yahoo Finance', url: 'https://finance.yahoo.com/news/rssindex', category: 'Economics', tier: 4, type: 'market' },

  // ── 政府 & 央行 (Government & Central Banks) ──
  { name: 'Federal Reserve', url: 'https://www.federalreserve.gov/feeds/press_all.xml', category: 'CentralBank', tier: 1, type: 'gov', note: '美联储官方' },
  { name: 'FRED Economic Release', url: 'https://fred.stlouisfed.org/rss/releases.xml', category: 'CentralBank', tier: 1, type: 'gov', note: '联储经济数据' },
  { name: 'White House', url: 'https://news.google.com/rss/search?q=site:whitehouse.gov&hl=en-US&gl=US&ceid=US:en', category: 'Government', tier: 1, type: 'gov' },
  { name: 'Pentagon', url: 'https://news.google.com/rss/search?q=site:defense.gov+OR+Pentagon&hl=en-US&gl=US&ceid=US:en', category: 'Government', tier: 1, type: 'gov' },

  // ── 智库 & 国际组织 (Think Tanks & International Orgs) ──
  { name: 'CrisisWatch', url: 'https://www.crisisgroup.org/rss', category: 'ThinkTank', tier: 3, type: 'intel', note: 'International Crisis Group' },
  { name: 'IAEA', url: 'https://www.iaea.org/feeds/topnews', category: 'ThinkTank', tier: 1, type: 'gov', note: '国际原子能机构' },
  { name: 'UN News', url: 'https://news.un.org/feed/subscribe/en/news/all/rss.xml', category: 'ThinkTank', tier: 1, type: 'gov' },
  { name: 'Atlantic Council', url: 'https://www.atlanticcouncil.org/feed/', category: 'ThinkTank', tier: 3, type: 'intel' },
  { name: 'Brookings', url: 'https://news.google.com/rss/search?q=site:brookings.edu+when:7d&hl=en-US&gl=US&ceid=US:en', category: 'ThinkTank', tier: 3, type: 'intel' },

  // ── 能源 & 大宗商品 (Energy & Commodities) ──
  { name: 'Oil & Gas', url: 'https://news.google.com/rss/search?q=(oil+price+OR+OPEC+OR+"natural+gas"+OR+pipeline+OR+LNG)+when:2d&hl=en-US&gl=US&ceid=US:en', category: 'Energy', tier: 3, type: 'market' },
  { name: 'Nuclear Energy', url: 'https://news.google.com/rss/search?q=("nuclear+energy"+OR+"nuclear+power"+OR+uranium+OR+IAEA)+when:3d&hl=en-US&gl=US&ceid=US:en', category: 'Energy', tier: 3, type: 'market' },

  // ── 网络安全 (Cybersecurity) ──
  { name: 'CISA Advisories', url: 'https://www.cisa.gov/cybersecurity-advisories/all.xml', category: 'Cyber', tier: 1, type: 'gov', note: 'US CISA 官方安全公告' },

  // ── 亚太地区 (Asia-Pacific) ──
  { name: 'BBC Asia', url: 'https://feeds.bbci.co.uk/news/world/asia/rss.xml', category: 'AsiaPacific', tier: 2, type: 'mainstream' },
  { name: 'Nikkei Asia', url: 'https://news.google.com/rss/search?q=site:asia.nikkei.com+when:3d&hl=en-US&gl=US&ceid=US:en', category: 'AsiaPacific', tier: 2, type: 'market' },

  // ── 特色实时源 (Special Real-Time) ──
  { name: 'GDELT Breaking News', url: 'http://data.gdeltproject.org/gdeltv2/lastupdate.txt', category: 'Alert', tier: 4, type: 'other', note: '需要特殊处理' },
];

// ── 分级查询函数 ──

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

/**
 * 按类别获取源
 */
export function getSourcesByCategory(category: string): Source[] {
  return SOURCES.filter(s => s.category === category);
}

/**
 * 获取所有类别列表
 */
export function getCategories(): string[] {
  return [...new Set(SOURCES.map(s => s.category))];
}

/**
 * 仅获取高质量源（Tier 1 & 2）
 */
export function getHighQualitySources(): Source[] {
  return SOURCES.filter(s => s.tier <= 2);
}
