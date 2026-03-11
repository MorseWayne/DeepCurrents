import Database from 'better-sqlite3';
import { join } from 'path';

export interface NewsRecord {
  id: string;
  url: string;
  title: string;
  content: string;
  category: string;
  timestamp: string;
}

export class DBService {
  private db: Database.Database;

  constructor(dbPath: string = 'data/intel.db') {
    const fs = require('fs');
    const dir = join(process.cwd(), 'data');
    if (!fs.existsSync(dir)) fs.mkdirSync(dir);

    this.db = new Database(join(process.cwd(), dbPath));
    this.init();
  }

  private init() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS raw_news (
        id TEXT PRIMARY KEY,
        url TEXT,
        title TEXT,
        content TEXT,
        source TEXT,
        is_reported INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      )
    `);
  }

  public hasNews(url: string): boolean {
    const row = this.db.prepare('SELECT id FROM raw_news WHERE url = ?').get(url);
    return !!row;
  }

  public saveNews(url: string, title: string, content: string, source: string) {
    this.db.prepare(
      'INSERT INTO raw_news (id, url, title, content, source) VALUES (?, ?, ?, ?, ?)'
    ).run(Buffer.from(url).toString('base64'), url, title, content, source);
  }

  public getUnreportedNews(): NewsRecord[] {
    return this.db.prepare('SELECT id, url, title, content, source as category, created_at as timestamp FROM raw_news WHERE is_reported = 0').all() as NewsRecord[];
  }

  public markAsReported(ids: string[]) {
    if (ids.length === 0) return;
    const placeholders = ids.map(() => '?').join(',');
    this.db.prepare(`UPDATE raw_news SET is_reported = 1 WHERE id IN (${placeholders})`).run(...ids);
  }
}
