import Database from 'better-sqlite3';
import { join } from 'path';
import { CONFIG } from '../config/settings';
import { tokenize as sharedTokenize, stripSourceAttribution, containsCJK } from '../utils/tokenizer';

// ── 标题模糊去重工具函数 ──

/**
 * 标准化标题：去掉末尾媒体归属、转小写、保留 CJK 字符
 */
function normalizeTitle(title: string): string {
  let t = stripSourceAttribution(title).toLowerCase();
  // 保留字母、数字、CJK 字符和空格
  t = t.replace(/[^\w\s\u2e80-\u9fff\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]/g, ' ');
  return t.replace(/\s+/g, ' ').trim();
}

/**
 * 提取有意义的词（委托给共享多语言分词器）
 */
function extractSignificantWords(normalized: string): Set<string> {
  return sharedTokenize(normalized, 2);
}

function generateTrigrams(text: string): Set<string> {
  const grams = new Set<string>();
  const padded = `  ${text} `;
  for (let i = 0; i < padded.length - 2; i++) {
    grams.add(padded.slice(i, i + 3));
  }
  return grams;
}

function setIntersectionSize(a: Set<string>, b: Set<string>): number {
  let count = 0;
  const [smaller, larger] = a.size <= b.size ? [a, b] : [b, a];
  for (const item of smaller) {
    if (larger.has(item)) count++;
  }
  return count;
}

function jaccardSimilarity(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  if (a.size === 0 || b.size === 0) return 0;
  const inter = setIntersectionSize(a, b);
  return inter / (a.size + b.size - inter);
}

function diceCoefficient(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 && b.size === 0) return 1;
  if (a.size === 0 || b.size === 0) return 0;
  const inter = setIntersectionSize(a, b);
  return (2 * inter) / (a.size + b.size);
}

// ── 内部缓存条目 ──

interface TitleCacheEntry {
  normalized: string;
  words: Set<string>;
  trigrams: Set<string>;
}

// ── 类型定义 ──

export interface NewsRecord {
  id: string;
  url: string;
  title: string;
  content: string;
  category: string;
  timestamp: string;
  tier?: number;
  sourceType?: string;
  threatLevel?: string;
  threatCategory?: string;
  threatConfidence?: number;
}

export class DBService {
  private db: Database.Database;

  // 标题模糊去重缓存 — 倒排索引加速候选查找
  private titleCacheEntries: TitleCacheEntry[] = [];
  private wordIndex = new Map<string, number[]>();
  private titleCacheTimestamp = 0;
  private static TITLE_CACHE_TTL_MS = 5 * 60 * 1000;

  constructor(dbPath: string = 'data/intel.db') {
    const fs = require('fs');
    const dir = join(process.cwd(), 'data');
    if (!fs.existsSync(dir)) fs.mkdirSync(dir);

    this.db = new Database(join(process.cwd(), dbPath));
    this.db.pragma('journal_mode = WAL');
    this.init();
  }

  private init() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS raw_news (
        id TEXT PRIMARY KEY,
        url TEXT UNIQUE,
        title TEXT,
        content TEXT,
        source TEXT,
        source_tier INTEGER DEFAULT 4,
        source_type TEXT DEFAULT 'other',
        threat_level TEXT DEFAULT 'info',
        threat_category TEXT DEFAULT 'general',
        threat_confidence REAL DEFAULT 0.3,
        is_reported INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    this.db.exec(`
      CREATE INDEX IF NOT EXISTS idx_raw_news_is_reported ON raw_news(is_reported);
      CREATE INDEX IF NOT EXISTS idx_raw_news_created_at ON raw_news(created_at);
      CREATE INDEX IF NOT EXISTS idx_raw_news_threat_level ON raw_news(threat_level);
    `);

    this.db.exec(`
      CREATE TABLE IF NOT EXISTS predictions (
        id TEXT PRIMARY KEY,
        asset_symbol TEXT,
        prediction_type TEXT,
        reasoning TEXT,
        base_price REAL,
        base_timestamp DATETIME,
        status TEXT DEFAULT 'pending',
        score REAL,
        actual_price REAL,
        scored_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);

    this.migrateSchema();
  }

  private migrateSchema() {
    const columns = this.db.prepare("PRAGMA table_info(raw_news)").all() as Array<{ name: string }>;
    const colNames = new Set(columns.map(c => c.name));

    const migrations: Array<{ column: string; sql: string }> = [
      { column: 'source_tier', sql: 'ALTER TABLE raw_news ADD COLUMN source_tier INTEGER DEFAULT 4' },
      { column: 'source_type', sql: "ALTER TABLE raw_news ADD COLUMN source_type TEXT DEFAULT 'other'" },
      { column: 'threat_level', sql: "ALTER TABLE raw_news ADD COLUMN threat_level TEXT DEFAULT 'info'" },
      { column: 'threat_category', sql: "ALTER TABLE raw_news ADD COLUMN threat_category TEXT DEFAULT 'general'" },
      { column: 'threat_confidence', sql: 'ALTER TABLE raw_news ADD COLUMN threat_confidence REAL DEFAULT 0.3' },
    ];

    for (const m of migrations) {
      if (!colNames.has(m.column)) {
        try { this.db.exec(m.sql); } catch (_) { /* ignore */ }
      }
    }
  }

  // ── 标题去重缓存管理 ──

  private ensureTitleCache(hoursBack: number): void {
    const now = Date.now();
    if (this.titleCacheEntries.length > 0 && now - this.titleCacheTimestamp < DBService.TITLE_CACHE_TTL_MS) return;

    const cutoff = new Date(now - hoursBack * 3600_000).toISOString();
    const rows = this.db.prepare(
      'SELECT title FROM raw_news WHERE created_at > ? ORDER BY created_at DESC LIMIT 5000'
    ).all(cutoff) as Array<{ title: string }>;

    this.titleCacheEntries = [];
    this.wordIndex = new Map();

    for (const row of rows) {
      this.pushToTitleCache(row.title);
    }
    this.titleCacheTimestamp = now;
  }

  private pushToTitleCache(title: string): void {
    const normalized = normalizeTitle(title);
    if (!normalized) return;

    const words = extractSignificantWords(normalized);
    const trigrams = generateTrigrams(normalized);
    const idx = this.titleCacheEntries.length;
    this.titleCacheEntries.push({ normalized, words, trigrams });

    for (const word of words) {
      const list = this.wordIndex.get(word);
      if (list) list.push(idx);
      else this.wordIndex.set(word, [idx]);
    }
  }

  // ── 公共 API ──

  public hasNews(url: string): boolean {
    const row = this.db.prepare('SELECT id FROM raw_news WHERE url = ?').get(url);
    return !!row;
  }

  /**
   * 模糊标题去重（trigram Dice + word Jaccard 双重检测）
   *
   * 利用词倒排索引快速定位候选，再做精确相似度比较。
   * 相比原来的精确匹配，能有效合并同一事件的不同措辞报道。
   */
  public hasSimilarTitle(
    title: string,
    hoursBack: number = CONFIG.DEDUP_HOURS_BACK,
    threshold: number = CONFIG.DEDUP_SIMILARITY_THRESHOLD,
  ): boolean {
    this.ensureTitleCache(hoursBack);

    const normalized = normalizeTitle(title);
    if (!normalized) return false;

    // 快速路径：标准化后精确匹配
    for (const entry of this.titleCacheEntries) {
      if (entry.normalized === normalized) return true;
    }

    const words = extractSignificantWords(normalized);
    const trigrams = generateTrigrams(normalized);

    // 通过词倒排索引找候选（共享词计数）
    const candidateHits = new Map<number, number>();
    for (const word of words) {
      const indices = this.wordIndex.get(word);
      if (!indices) continue;
      for (const idx of indices) {
        candidateHits.set(idx, (candidateHits.get(idx) ?? 0) + 1);
      }
    }

    // 仅对共享 1+ 词的候选做精确比较
    for (const [idx, _hitCount] of candidateHits) {
      const entry = this.titleCacheEntries[idx]!;
      if (jaccardSimilarity(words, entry.words) >= threshold) return true;
      if (diceCoefficient(trigrams, entry.trigrams) >= threshold) return true;
    }

    return false;
  }

  public saveNews(
    url: string,
    title: string,
    content: string,
    source: string,
    meta?: {
      tier?: number;
      sourceType?: string;
      threatLevel?: string;
      threatCategory?: string;
      threatConfidence?: number;
    }
  ) {
    this.db.prepare(
      `INSERT OR IGNORE INTO raw_news 
        (id, url, title, content, source, source_tier, source_type, threat_level, threat_category, threat_confidence) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).run(
      Buffer.from(url).toString('base64'),
      url,
      title,
      content,
      source,
      meta?.tier ?? 4,
      meta?.sourceType ?? 'other',
      meta?.threatLevel ?? 'info',
      meta?.threatCategory ?? 'general',
      meta?.threatConfidence ?? 0.3
    );

    // 同步更新内存缓存，当前采集周期内的后续去重立即生效
    this.pushToTitleCache(title);
  }

  /**
   * 获取未报告的新闻（按威胁等级 → 源权威度 → 时间排序）
   *
   * @param limit 最大返回条数，防止积压时内存溢出和 LLM 上下文爆炸
   */
  public getUnreportedNews(limit: number = CONFIG.REPORT_MAX_NEWS): NewsRecord[] {
    return this.db.prepare(`
      SELECT id, url, title, content, source as category, created_at as timestamp,
             source_tier as tier, source_type as sourceType,
             threat_level as threatLevel, threat_category as threatCategory, 
             threat_confidence as threatConfidence
      FROM raw_news 
      WHERE is_reported = 0
      ORDER BY 
        CASE threat_level 
          WHEN 'critical' THEN 5
          WHEN 'high' THEN 4
          WHEN 'medium' THEN 3
          WHEN 'low' THEN 2
          ELSE 1
        END DESC,
        source_tier ASC,
        created_at DESC
      LIMIT ?
    `).all(limit) as NewsRecord[];
  }

  public getNewsByThreatLevel(level: string, hoursBack: number = 24): NewsRecord[] {
    const cutoff = new Date(Date.now() - hoursBack * 60 * 60 * 1000).toISOString();
    return this.db.prepare(`
      SELECT id, url, title, content, source as category, created_at as timestamp,
             source_tier as tier, threat_level as threatLevel
      FROM raw_news 
      WHERE threat_level = ? AND created_at > ?
      ORDER BY created_at DESC
    `).all(level, cutoff) as NewsRecord[];
  }

  public markAsReported(ids: string[]) {
    if (ids.length === 0) return;
    const placeholders = ids.map(() => '?').join(',');
    this.db.prepare(`UPDATE raw_news SET is_reported = 1 WHERE id IN (${placeholders})`).run(...ids);
  }

  public getStats(): { total: number; unreported: number; byThreat: Record<string, number>; byTier: Record<string, number> } {
    const total = (this.db.prepare('SELECT COUNT(*) as count FROM raw_news').get() as any).count;
    const unreported = (this.db.prepare('SELECT COUNT(*) as count FROM raw_news WHERE is_reported = 0').get() as any).count;
    
    const threatRows = this.db.prepare('SELECT threat_level, COUNT(*) as count FROM raw_news GROUP BY threat_level').all() as Array<{ threat_level: string; count: number }>;
    const byThreat: Record<string, number> = {};
    for (const row of threatRows) byThreat[row.threat_level] = row.count;

    const tierRows = this.db.prepare('SELECT source_tier, COUNT(*) as count FROM raw_news GROUP BY source_tier').all() as Array<{ source_tier: number; count: number }>;
    const byTier: Record<string, number> = {};
    for (const row of tierRows) byTier[`T${row.source_tier}`] = row.count;

    return { total, unreported, byThreat, byTier };
  }

  public cleanup(daysToKeep: number = CONFIG.DATA_RETENTION_DAYS) {
    const cutoff = new Date(Date.now() - daysToKeep * 24 * 60 * 60 * 1000).toISOString();
    const result = this.db.prepare('DELETE FROM raw_news WHERE created_at < ? AND is_reported = 1').run(cutoff);
    return result.changes;
  }

  // ── 预测与评分 API ──

  public savePrediction(data: {
    asset: string;
    type: 'bullish' | 'bearish' | 'neutral';
    reasoning: string;
    price: number;
    timestamp: string;
  }) {
    const id = Buffer.from(`${data.asset}-${data.timestamp}`).toString('base64');
    this.db.prepare(`
      INSERT OR REPLACE INTO predictions (id, asset_symbol, prediction_type, reasoning, base_price, base_timestamp)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(id, data.asset, data.type, data.reasoning, data.price, data.timestamp);
  }

  public getPendingPredictions(): any[] {
    return this.db.prepare(`
      SELECT * FROM predictions WHERE status = 'pending'
    `).all();
  }

  public updatePredictionScore(id: string, score: number, actualPrice: number) {
    this.db.prepare(`
      UPDATE predictions 
      SET score = ?, actual_price = ?, status = 'scored', scored_at = CURRENT_TIMESTAMP 
      WHERE id = ?
    `).run(score, actualPrice, id);
  }
}
