export const SOURCES = [
  // 地缘政治 & 冲突 (重大事件)
  { name: 'Reuters World', url: 'https://www.reutersagency.com/feed/?best-topics=world-news&post_type=best', category: 'Geopolitics' },
  { name: 'AP News', url: 'https://news.google.com/rss/search?q=when:24h+allinurl:apnews.com/article&hl=en-US&gl=US&ceid=US:en', category: 'Geopolitics' },
  { name: 'Financial Times World', url: 'https://www.ft.com/?format=rss', category: 'Geopolitics' },
  
  // 经济 & 金融 (影响经济)
  { name: 'Bloomberg Markets', url: 'https://www.bloomberg.com/feeds/markets/index.xml', category: 'Economics' },
  { name: 'Yahoo Finance News', url: 'https://finance.yahoo.com/news/rssindex', category: 'Economics' },
  { name: 'MarketWatch Top Stories', url: 'http://feeds.marketwatch.com/marketwatch/topstories', category: 'Economics' },
  { name: 'FRED Economic Release', url: 'https://fred.stlouisfed.org/rss/releases.xml', category: 'Economics' },
  
  // 特色源 (从 WorldMonitor 提取)
  { name: 'GDELT Breaking News', url: 'http://data.gdeltproject.org/gdeltv2/lastupdate.txt', category: 'Alert' }, // 需处理
  { name: 'Conflict News', url: 'http://feeds.feedburner.com/ConflictNews', category: 'Geopolitics' }
];
