import Database from 'better-sqlite3';
import { join } from 'path';

/**
 * 新闻记录（增强版）
 * 借鉴 WorldMonitor 的信源分级和威胁分类元数据
 */
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

  constructor(dbPath: string = 'data/intel.db') {
    const fs = require('fs');
    const dir = join(process.cwd(), 'data');
    if (!fs.existsSync(dir)) fs.mkdirSync(dir);

    this.db = new Database(join(process.cwd(), dbPath));
    this.db.pragma('journal_mode = WAL'); // 性能优化：Write-Ahead Logging
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

    // 确保索引存在
    this.db.exec(`
      CREATE INDEX IF NOT EXISTS idx_raw_news_is_reported ON raw_news(is_reported);
      CREATE INDEX IF NOT EXISTS idx_raw_news_created_at ON raw_news(created_at);
      CREATE INDEX IF NOT EXISTS idx_raw_news_threat_level ON raw_news(threat_level);
    `);

    // 迁移：为旧表添加新列（如果不存在）
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
        try {
          this.db.exec(m.sql);
        } catch (e) {
          // 列已存在或其他错误，忽略
        }
      }
    }
  }

  /**
   * 检查是否已有该新闻（基于 URL 去重）
   */
  public hasNews(url: string): boolean {
    const row = this.db.prepare('SELECT id FROM raw_news WHERE url = ?').get(url);
    return !!row;
  }

  /**
   * 基于标题相似度去重（补充 URL 去重的不足）
   * 借鉴 WorldMonitor 的标题去重策略
   */
  public hasSimilarTitle(title: string, hoursBack: number = 24): boolean {
    // 简化版：精确标题匹配
    const cutoff = new Date(Date.now() - hoursBack * 60 * 60 * 1000).toISOString();
    const row = this.db.prepare(
      'SELECT id FROM raw_news WHERE title = ? AND created_at > ?'
    ).get(title, cutoff);
    return !!row;
  }

  /**
   * 保存新闻（增强版：附带分级和威胁元数据）
   */
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
  }

  /**
   * 获取未报告的新闻（携带分级和威胁元数据）
   */
  public getUnreportedNews(): NewsRecord[] {
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
    `).all() as NewsRecord[];
  }

  /**
   * 获取指定威胁等级的新闻
   */
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

  /**
   * 标记为已报告
   */
  public markAsReported(ids: string[]) {
    if (ids.length === 0) return;
    const placeholders = ids.map(() => '?').join(',');
    this.db.prepare(`UPDATE raw_news SET is_reported = 1 WHERE id IN (${placeholders})`).run(...ids);
  }

  /**
   * 获取统计摘要
   */
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

  /**
   * 清理旧数据（保留 N 天内的）
   */
  public cleanup(daysToKeep: number = 30) {
    const cutoff = new Date(Date.now() - daysToKeep * 24 * 60 * 60 * 1000).toISOString();
    const result = this.db.prepare('DELETE FROM raw_news WHERE created_at < ? AND is_reported = 1').run(cutoff);
    return result.changes;
  }
}
