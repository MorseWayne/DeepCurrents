import aiosqlite
import os
import base64
from datetime import datetime, timedelta
from typing import List, Set, Optional, Dict, Any
from dataclasses import dataclass, asdict
from ..config.settings import CONFIG
from ..utils.tokenizer import tokenize, strip_source_attribution, contains_cjk
from ..utils.logger import get_logger

logger = get_logger("db-service")

@dataclass
class NewsRecord:
    id: str
    url: str
    title: str
    content: str
    category: str  # 对应 TS 中的 source
    timestamp: str # 对应 TS 中的 created_at
    tier: int = 4
    sourceType: str = "other"
    threatLevel: str = "info"
    threatCategory: str = "general"
    threatConfidence: float = 0.3
    is_reported: int = 0

@dataclass
class TitleCacheEntry:
    normalized: str
    words: Set[str]
    trigrams: Set[str]


def to_sqlite_timestamp(dt: datetime) -> str:
    """Format datetime to SQLite CURRENT_TIMESTAMP-compatible text."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def normalize_title(title: str) -> str:
    """标准化标题：去掉末尾媒体归属、转小写、保留关键字符"""
    t = strip_source_attribution(title).lower()
    # 保留字母、数字、CJK 字符和空格
    t = re.sub(r'[^\w\s\u2e80-\u9fff\uf900-\ufaff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

import re

def generate_trigrams(text: str) -> Set[str]:
    grams = set()
    padded = f"  {text} "
    for i in range(len(padded) - 2):
        grams.add(padded[i:i+3])
    return grams

def jaccard_similarity(a: Set[Any], b: Set[Any]) -> float:
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union

def dice_coefficient(a: Set[Any], b: Set[Any]) -> float:
    if not a and not b: return 1.0
    if not a or not b: return 0.0
    inter = len(a & b)
    return (2 * inter) / (len(a) + len(b))

class DBService:
    TITLE_CACHE_TTL_SECONDS = 5 * 60

    def __init__(self, db_path: str = "data/intel.db"):
        self.db_path = db_path
        self._db = None
        self._title_cache: List[TitleCacheEntry] = []
        self._word_index: Dict[str, List[int]] = {}
        self._cache_timestamp = 0
        
        # 确保数据目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        if not self._db:
            self._db = await aiosqlite.connect(self.db_path)
            self._db.row_factory = aiosqlite.Row
            await self._init_db()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def _init_db(self):
        await self._db.executescript("""
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
            );
            
            CREATE INDEX IF NOT EXISTS idx_raw_news_is_reported ON raw_news(is_reported);
            CREATE INDEX IF NOT EXISTS idx_raw_news_created_at ON raw_news(created_at);
            CREATE INDEX IF NOT EXISTS idx_raw_news_threat_level ON raw_news(threat_level);

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
            );
        """)
        await self._db.commit()

    async def _ensure_title_cache(self, hours_back: int):
        now = datetime.now().timestamp()
        if self._title_cache and (now - self._cache_timestamp < self.TITLE_CACHE_TTL_SECONDS):
            return

        cutoff = to_sqlite_timestamp(datetime.utcnow() - timedelta(hours=hours_back))
        async with self._db.execute(
            "SELECT title FROM raw_news WHERE created_at > ? ORDER BY created_at DESC LIMIT 5000",
            (cutoff,)
        ) as cursor:
            rows = await cursor.fetchall()

        self._title_cache = []
        self._word_index = {}
        for row in rows:
            self._push_to_title_cache(row['title'])
        
        self._cache_timestamp = now

    def _push_to_title_cache(self, title: str):
        normalized = normalize_title(title)
        if not normalized: return

        words = tokenize(normalized, 2)
        trigrams = generate_trigrams(normalized)
        idx = len(self._title_cache)
        self._title_cache.append(TitleCacheEntry(normalized, words, trigrams))

        for word in words:
            if word not in self._word_index:
                self._word_index[word] = []
            self._word_index[word].append(idx)

    async def has_news(self, url: str) -> bool:
        async with self._db.execute("SELECT id FROM raw_news WHERE url = ?", (url,)) as cursor:
            return await cursor.fetchone() is not None

    async def has_similar_title(self, title: str, hours_back: int = None, threshold: float = None) -> bool:
        hours_back = hours_back or CONFIG.dedup_hours_back
        threshold = threshold or CONFIG.dedup_similarity_threshold
        
        await self._ensure_title_cache(hours_back)
        normalized = normalize_title(title)
        if not normalized: return False

        # 快速路径
        for entry in self._title_cache:
            if entry.normalized == normalized: return True

        words = tokenize(normalized, 2)
        trigrams = generate_trigrams(normalized)

        # 倒排索引
        candidate_hits = {}
        for word in words:
            indices = self._word_index.get(word, [])
            for idx in indices:
                candidate_hits[idx] = candidate_hits.get(idx, 0) + 1

        for idx in candidate_hits:
            entry = self._title_cache[idx]
            if jaccard_similarity(words, entry.words) >= threshold: return True
            if dice_coefficient(trigrams, entry.trigrams) >= threshold: return True

        return False

    async def save_news(self, url: str, title: str, content: str, source: str, meta: Dict[str, Any] = None) -> bool:
        news_id = base64.b64encode(url.encode()).decode()
        meta = meta or {}
        cursor = await self._db.execute(
            """INSERT OR IGNORE INTO raw_news 
               (id, url, title, content, source, source_tier, source_type, threat_level, threat_category, threat_confidence) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                news_id, url, title, content, source,
                meta.get('tier', 4),
                meta.get('sourceType', 'other'),
                meta.get('threatLevel', 'info'),
                meta.get('threatCategory', 'general'),
                meta.get('threatConfidence', 0.3)
            )
        )
        await self._db.commit()
        inserted = cursor.rowcount == 1
        if inserted:
            self._push_to_title_cache(title)
        return inserted

    async def get_unreported_news(self, limit: int = None) -> List[NewsRecord]:
        limit = limit or CONFIG.report_max_news
        query = """
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
        """
        async with self._db.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [NewsRecord(**dict(row)) for row in rows]

    async def mark_as_reported(self, ids: List[str]):
        if not ids: return
        placeholders = ','.join(['?'] * len(ids))
        await self._db.execute(f"UPDATE raw_news SET is_reported = 1 WHERE id IN ({placeholders})", ids)
        await self._db.commit()

    async def save_prediction(self, data: Dict[str, Any]):
        pred_id = base64.b64encode(f"{data['asset']}-{data['timestamp']}".encode()).decode()
        await self._db.execute(
            """INSERT OR REPLACE INTO predictions 
               (id, asset_symbol, prediction_type, reasoning, base_price, base_timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pred_id, data['asset'], data['type'], data['reasoning'], data['price'], data['timestamp'])
        )
        await self._db.commit()

    async def get_pending_predictions(self) -> List[Dict[str, Any]]:
        async with self._db.execute("SELECT * FROM predictions WHERE status = 'pending'") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_prediction_score(self, pred_id: str, score: float, actual_price: float):
        await self._db.execute(
            """UPDATE predictions 
               SET score = ?, actual_price = ?, status = 'scored', scored_at = CURRENT_TIMESTAMP 
               WHERE id = ?""",
            (score, actual_price, pred_id)
        )
        await self._db.commit()

    async def cleanup(self, days_to_keep: int = None):
        days_to_keep = days_to_keep or CONFIG.data_retention_days
        cutoff = to_sqlite_timestamp(datetime.utcnow() - timedelta(days=days_to_keep))
        async with self._db.execute("DELETE FROM raw_news WHERE created_at < ? AND is_reported = 1", (cutoff,)) as cursor:
            changes = cursor.rowcount
            await self._db.commit()
            return changes
