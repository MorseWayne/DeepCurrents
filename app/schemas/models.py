"""API 请求/响应 Pydantic 模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportSummary(BaseModel):
    id: str
    date: str
    title: str = ""
    event_count: int = 0
    created_at: datetime | None = None


class ReportDetail(BaseModel):
    id: str
    date: str
    content: dict[str, Any] = Field(default_factory=dict)
    markdown: str = ""
    created_at: datetime | None = None


class EventSummary(BaseModel):
    id: str
    title: str
    status: str = "active"
    article_count: int = 0
    sentiment_score: float | None = None
    updated_at: datetime | None = None


class SourceStatus(BaseModel):
    name: str
    url: str
    tier: int = 3
    ok: bool = True
    last_fetched: datetime | None = None
    failure_count: int = 0


class SystemStatus(BaseModel):
    uptime_seconds: float
    last_collection: datetime | None = None
    last_report: datetime | None = None
    source_count: int = 0
    event_count: int = 0
    report_count: int = 0
