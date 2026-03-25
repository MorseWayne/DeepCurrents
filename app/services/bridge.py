"""桥接 src/services 到 FastAPI 路由层。

封装数据库连接和服务初始化，提供简单的查询接口。
"""
from __future__ import annotations

from typing import Any

from src.utils.logger import get_logger

logger = get_logger("api-bridge")

_pool = None


async def get_pool():
    """惰性获取 asyncpg 连接池。"""
    global _pool
    if _pool is None:
        import asyncpg
        from src.config.settings import CONFIG

        dsn = CONFIG.event_intelligence_postgres_dsn
        _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=5)
    return _pool


async def list_reports(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    try:
        pool = await get_pool()
        rows = await pool.fetch(
            "SELECT id, report_date, content, created_at "
            "FROM report_runs ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning(f"list_reports query failed (tables may not exist): {exc}")
        return []


async def get_report(report_id: str) -> dict[str, Any] | None:
    try:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT * FROM report_runs WHERE id = $1", report_id
        )
        return dict(row) if row else None
    except Exception as exc:
        logger.warning(f"get_report query failed: {exc}")
        return None


async def list_events(
    limit: int = 50, status: str | None = None
) -> list[dict[str, Any]]:
    try:
        pool = await get_pool()
        if status:
            rows = await pool.fetch(
                "SELECT id, title, status, article_count, updated_at "
                "FROM events WHERE status = $1 ORDER BY updated_at DESC LIMIT $2",
                status,
                limit,
            )
        else:
            rows = await pool.fetch(
                "SELECT id, title, status, article_count, updated_at "
                "FROM events ORDER BY updated_at DESC LIMIT $1",
                limit,
            )
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning(f"list_events query failed (tables may not exist): {exc}")
        return []


async def get_source_statuses() -> list[dict[str, Any]]:
    try:
        from src.config.sources import SOURCES

        return [
            {
                "name": s.name,
                "url": s.url,
                "tier": s.tier,
                "ok": True,
                "failure_count": 0,
            }
            for s in SOURCES
        ]
    except Exception as exc:
        logger.warning(f"get_source_statuses failed: {exc}")
        return []
