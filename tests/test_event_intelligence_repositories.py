from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from src.services.article_models import ArticleRecord
from src.services.article_repository import ArticleRepository
from src.services.brief_repository import BriefRepository
from src.services.event_repository import EventRepository
from src.services.feedback_repository import FeedbackRepository
from src.services.report_repository import ReportRepository


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self):
        self.fetchrow_results = []
        self.fetch_results = []
        self.execute_results = []
        self.calls = []
        self.transaction_calls = 0

    def transaction(self):
        self.transaction_calls += 1
        return FakeTransaction()

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", sql, args))
        if self.fetchrow_results:
            return self.fetchrow_results.pop(0)
        return None

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", sql, args))
        if self.fetch_results:
            return self.fetch_results.pop(0)
        return []

    async def execute(self, sql, *args):
        self.calls.append(("execute", sql, args))
        if self.execute_results:
            return self.execute_results.pop(0)
        return "OK"


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()
        self.acquire_calls = 0

    async def fetchrow(self, sql, *args):
        return await self.connection.fetchrow(sql, *args)

    async def fetch(self, sql, *args):
        return await self.connection.fetch(sql, *args)

    async def execute(self, sql, *args):
        return await self.connection.execute(sql, *args)

    def acquire(self):
        self.acquire_calls += 1
        return FakeAcquire(self.connection)


@pytest.mark.asyncio
async def test_article_repository_create_and_lookup_article():
    pool = FakePool()
    repo = ArticleRepository(pool)
    pool.connection.fetchrow_results = [
        {"article_id": "art_1", "canonical_url": "https://example.com/a", "title": "A"},
        {"article_id": "art_1", "canonical_url": "https://example.com/a", "title": "A"},
    ]

    created = await repo.create_article(
        {
            "article_id": "art_1",
            "source_id": "reuters",
            "canonical_url": "https://example.com/a",
            "title": "A",
        }
    )
    loaded = await repo.get_article_by_canonical_url("https://example.com/a")

    assert created["article_id"] == "art_1"
    assert loaded == created
    assert "INSERT INTO articles" in pool.connection.calls[0][1]
    assert (
        pool.connection.calls[1][1] == "SELECT * FROM articles WHERE canonical_url = $1"
    )


@pytest.mark.asyncio
async def test_article_repository_accepts_article_record_payload():
    pool = FakePool()
    repo = ArticleRepository(pool)
    pool.connection.fetchrow_results = [
        {"article_id": "art_2", "canonical_url": "https://example.com/b", "title": "B"}
    ]

    record = ArticleRecord(
        article_id="art_2",
        source_id="ap",
        canonical_url="https://example.com/b",
        title="B",
        content="body",
    )
    created = await repo.create_article(record.to_article_payload())

    assert created["article_id"] == "art_2"
    assert pool.connection.calls[0][2][4] == "B"
    assert pool.connection.calls[0][2][5] == "body"
    assert pool.connection.calls[0][2][6] == "body"


@pytest.mark.asyncio
async def test_article_repository_applies_article_record_style_fallbacks_for_raw_mapping():
    pool = FakePool()
    repo = ArticleRepository(pool)
    pool.connection.fetchrow_results = [
        {"article_id": "art_3", "canonical_url": "https://example.com/c", "title": "C"}
    ]

    await repo.create_article(
        {
            "article_id": "art_3",
            "source_id": "ap",
            "canonical_url": "https://example.com/c",
            "title": "C",
            "content": "body",
        }
    )

    assert pool.connection.calls[0][2][4] == "C"
    assert pool.connection.calls[0][2][5] == "body"
    assert pool.connection.calls[0][2][6] == "body"
    assert pool.connection.calls[0][2][14] == len("body")


@pytest.mark.asyncio
async def test_article_repository_upserts_features_and_lists_related_records():
    pool = FakePool()
    repo = ArticleRepository(pool)
    since = datetime(2026, 3, 13, tzinfo=timezone.utc)
    pool.connection.fetchrow_results = [
        {"article_id": "art_1", "embedding_model": "bge-m3"}
    ]
    pool.connection.fetch_results = [
        [{"article_id": "art_1"}],
        [{"link_id": "dup_1", "left_article_id": "art_1", "right_article_id": "art_2"}],
    ]

    features = await repo.upsert_article_features(
        {
            "article_id": "art_1",
            "embedding_model": "bge-m3",
            "keywords": ["oil"],
        }
    )
    recent = await repo.list_recent_articles(since=since, limit=5)
    dedup_links = await repo.list_dedup_links("art_1")

    assert features["embedding_model"] == "bge-m3"
    assert recent == [{"article_id": "art_1"}]
    assert dedup_links[0]["link_id"] == "dup_1"
    assert "ON CONFLICT (article_id)" in pool.connection.calls[0][1]
    assert "COALESCE(published_at, ingested_at) >= $1" in pool.connection.calls[1][1]
    assert (
        "left_article_id = $1 OR right_article_id = $1" in pool.connection.calls[2][1]
    )


@pytest.mark.asyncio
async def test_event_repository_crud_queries_and_updates():
    pool = FakePool()
    repo = EventRepository(pool)
    since = datetime(2026, 3, 13, tzinfo=timezone.utc)
    pool.connection.fetchrow_results = [
        {"event_id": "evt_1", "status": "new"},
        {"event_id": "evt_1", "status": "active"},
        {"event_id": "evt_1", "status": "active"},
    ]
    pool.connection.fetch_results = [[{"event_id": "evt_1", "status": "active"}]]

    created = await repo.create_event(
        {"event_id": "evt_1", "status": "new", "canonical_title": "Title"}
    )
    updated = await repo.update_event("evt_1", {"status": "active", "article_count": 3})
    events = await repo.list_recent_events(statuses=["active"], since=since, limit=10)
    loaded = await repo.get_event("evt_1")

    assert created["status"] == "new"
    assert updated["status"] == "active"
    assert events == [{"event_id": "evt_1", "status": "active"}]
    assert loaded == {"event_id": "evt_1", "status": "active"}
    assert "INSERT INTO events" in pool.connection.calls[0][1]
    assert "ON CONFLICT (event_id) DO NOTHING" in pool.connection.calls[0][1]
    assert "UPDATE events" in pool.connection.calls[1][1]
    assert "status = ANY($1::text[])" in pool.connection.calls[2][1]
    assert pool.connection.calls[3][1] == "SELECT * FROM events WHERE event_id = $1"


@pytest.mark.asyncio
async def test_event_repository_manages_members_scores_and_transitions():
    pool = FakePool()
    repo = EventRepository(pool)
    pool.connection.fetchrow_results = [
        {"event_id": "evt_1", "article_id": "art_1", "role": "primary"},
        {"event_id": "evt_1", "profile": "macro_daily", "total_score": 8.2},
        {"event_id": "evt_1", "profile": "macro_daily", "total_score": 8.2},
        {"transition_id": "tr_1", "event_id": "evt_1", "to_state": "updated"},
    ]
    pool.connection.fetch_results = [
        [{"event_id": "evt_1", "profile": "macro_daily", "total_score": 8.2}],
        [{"event_id": "evt_1", "article_id": "art_1"}],
        [{"transition_id": "tr_1", "event_id": "evt_1"}],
    ]

    member = await repo.add_event_member(
        {
            "event_id": "evt_1",
            "article_id": "art_1",
            "role": "primary",
            "is_primary": True,
        }
    )
    score = await repo.upsert_event_score(
        {"event_id": "evt_1", "profile": "macro_daily", "total_score": 8.2}
    )
    loaded_score = await repo.get_event_score("evt_1", "macro_daily")
    listed_scores = await repo.list_event_scores("evt_1")
    transition = await repo.record_state_transition(
        {"transition_id": "tr_1", "event_id": "evt_1", "to_state": "updated"}
    )
    members = await repo.list_event_members("evt_1")
    transitions = await repo.list_event_state_transitions("evt_1")

    assert member["role"] == "primary"
    assert score["total_score"] == 8.2
    assert loaded_score == score
    assert listed_scores == [{"event_id": "evt_1", "profile": "macro_daily", "total_score": 8.2}]
    assert transition["to_state"] == "updated"
    assert members == [{"event_id": "evt_1", "article_id": "art_1"}]
    assert transitions == [{"transition_id": "tr_1", "event_id": "evt_1"}]
    assert "ON CONFLICT (event_id, article_id)" in pool.connection.calls[0][1]
    assert "ON CONFLICT (event_id, profile)" in pool.connection.calls[1][1]
    assert "ON CONFLICT (transition_id) DO NOTHING" in pool.connection.calls[4][1]
    assert (
        pool.connection.calls[2][1]
        == "SELECT * FROM event_scores WHERE event_id = $1 AND profile = $2"
    )
    assert "FROM event_scores" in pool.connection.calls[3][1]


@pytest.mark.asyncio
async def test_event_repository_returns_existing_event_on_duplicate_create():
    pool = FakePool()
    repo = EventRepository(pool)
    pool.connection.fetchrow_results = [
        None,
        {"event_id": "evt_1", "status": "active", "canonical_title": "Existing"},
    ]

    created = await repo.create_event(
        {"event_id": "evt_1", "status": "new", "canonical_title": "Incoming"}
    )

    assert created == {
        "event_id": "evt_1",
        "status": "active",
        "canonical_title": "Existing",
    }
    assert "ON CONFLICT (event_id) DO NOTHING" in pool.connection.calls[0][1]
    assert pool.connection.calls[1][1] == "SELECT * FROM events WHERE event_id = $1"
    assert pool.connection.calls[1][2] == ("evt_1",)


@pytest.mark.asyncio
async def test_event_repository_returns_existing_transition_on_duplicate_record():
    pool = FakePool()
    repo = EventRepository(pool)
    pool.connection.fetchrow_results = [
        None,
        {"transition_id": "tr_1", "event_id": "evt_1", "to_state": "updated"},
    ]

    transition = await repo.record_state_transition(
        {"transition_id": "tr_1", "event_id": "evt_1", "to_state": "updated"}
    )

    assert transition == {
        "transition_id": "tr_1",
        "event_id": "evt_1",
        "to_state": "updated",
    }
    assert "ON CONFLICT (transition_id) DO NOTHING" in pool.connection.calls[0][1]
    assert (
        pool.connection.calls[1][1]
        == "SELECT * FROM event_state_transitions WHERE transition_id = $1"
    )
    assert pool.connection.calls[1][2] == ("tr_1",)


@pytest.mark.asyncio
async def test_brief_repository_upserts_and_reads_event_briefs():
    pool = FakePool()
    repo = BriefRepository(pool)
    pool.connection.fetchrow_results = [
        {"brief_id": "brief_1", "event_id": "evt_1", "version": "v1"},
        {"brief_id": "brief_1", "event_id": "evt_1", "version": "v1"},
    ]
    pool.connection.fetch_results = [[{"brief_id": "brief_1", "event_id": "evt_1"}]]

    brief = await repo.upsert_event_brief(
        {
            "brief_id": "brief_1",
            "event_id": "evt_1",
            "brief_json": {"stateChange": "new"},
        }
    )
    loaded = await repo.get_event_brief("evt_1")
    listed = await repo.list_event_briefs(["evt_1"])

    assert brief["brief_id"] == "brief_1"
    assert loaded == brief
    assert listed == [{"brief_id": "brief_1", "event_id": "evt_1"}]
    assert "ON CONFLICT (event_id, version)" in pool.connection.calls[0][1]
    assert (
        pool.connection.calls[1][1]
        == "SELECT * FROM event_briefs WHERE event_id = $1 AND version = $2"
    )
    assert await repo.list_event_briefs([]) == []


@pytest.mark.asyncio
async def test_brief_repository_upserts_and_reads_theme_briefs():
    pool = FakePool()
    repo = BriefRepository(pool)
    report_date = date(2026, 3, 13)
    pool.connection.fetchrow_results = [
        {
            "theme_brief_id": "theme_1",
            "theme_key": "energy",
            "report_date": report_date,
        },
        {
            "theme_brief_id": "theme_1",
            "theme_key": "energy",
            "report_date": report_date,
        },
    ]
    pool.connection.fetch_results = [
        [{"theme_brief_id": "theme_1", "theme_key": "energy"}]
    ]

    brief = await repo.upsert_theme_brief(
        {"theme_brief_id": "theme_1", "theme_key": "energy", "report_date": report_date}
    )
    loaded = await repo.get_theme_brief("energy", report_date)
    listed = await repo.list_theme_briefs(report_date)

    assert brief["theme_key"] == "energy"
    assert loaded == brief
    assert listed == [{"theme_brief_id": "theme_1", "theme_key": "energy"}]
    assert (
        "ON CONFLICT (theme_key, report_date, version)" in pool.connection.calls[0][1]
    )
    assert "report_date IS NOT DISTINCT FROM $2" in pool.connection.calls[1][1]


@pytest.mark.asyncio
async def test_report_repository_crud_queries_and_updates():
    pool = FakePool()
    repo = ReportRepository(pool)
    report_date = date(2026, 3, 13)
    pool.connection.fetchrow_results = [
        {"report_run_id": "run_1", "status": "pending"},
        {"report_run_id": "run_1", "status": "pending"},
        {"report_run_id": "run_1", "status": "completed"},
        {"report_run_id": "run_1", "status": "completed"},
    ]
    pool.connection.fetch_results = [
        [
            {"report_run_id": "run_1", "status": "completed"},
            {"report_run_id": "run_0", "status": "completed"},
        ]
    ]

    created = await repo.create_report_run(
        {"report_run_id": "run_1", "profile": "macro_daily", "report_date": report_date}
    )
    loaded = await repo.get_report_run_by_date("macro_daily", report_date)
    latest = await repo.get_latest_report_run("macro_daily")
    listed = await repo.list_report_runs(profile="macro_daily", status="completed", limit=2)
    updated = await repo.update_report_run(
        "run_1", {"status": "completed", "selected_event_count": 5}
    )

    assert created["status"] == "pending"
    assert loaded == {"report_run_id": "run_1", "status": "pending"}
    assert latest == {"report_run_id": "run_1", "status": "completed"}
    assert [item["report_run_id"] for item in listed] == ["run_1", "run_0"]
    assert updated["status"] == "completed"
    assert "INSERT INTO report_runs" in pool.connection.calls[0][1]
    assert "report_date IS NOT DISTINCT FROM $2" in pool.connection.calls[1][1]
    assert "ORDER BY report_date DESC NULLS LAST" in pool.connection.calls[2][1]
    assert "FROM report_runs" in pool.connection.calls[3][1]
    assert "profile = $1 AND status = $2" in pool.connection.calls[3][1]
    assert "UPDATE report_runs" in pool.connection.calls[4][1]


@pytest.mark.asyncio
async def test_report_repository_replaces_event_links_in_transaction():
    pool = FakePool()
    repo = ReportRepository(pool)
    pool.connection.fetchrow_results = [
        {"report_run_id": "run_1", "event_id": "evt_1", "rank": 1},
        {"report_run_id": "run_1", "event_id": "evt_2", "rank": 2},
    ]
    pool.connection.fetch_results = [
        [
            {"report_run_id": "run_1", "event_id": "evt_1", "rank": 1},
            {"report_run_id": "run_1", "event_id": "evt_2", "rank": 2},
        ]
    ]

    links = await repo.replace_report_event_links(
        "run_1",
        [
            {"event_id": "evt_1", "rank": 1},
            {"event_id": "evt_2", "rank": 2, "included": False},
        ],
    )
    listed = await repo.list_report_event_links("run_1")

    assert [link["event_id"] for link in links] == ["evt_1", "evt_2"]
    assert [link["rank"] for link in listed] == [1, 2]
    assert pool.acquire_calls == 1
    assert pool.connection.transaction_calls == 1
    assert pool.connection.calls[0][0] == "execute"
    assert "DELETE FROM report_event_links" in pool.connection.calls[0][1]
    assert "INSERT INTO report_event_links" in pool.connection.calls[1][1]


@pytest.mark.asyncio
async def test_feedback_repository_creates_and_lists_labels():
    pool = FakePool()
    repo = FeedbackRepository(pool)
    pool.connection.fetchrow_results = [
        {"label_id": "label_1", "label_type": "report_review", "subject_id": "run_1"}
    ]
    pool.connection.fetch_results = [
        [
            {
                "label_id": "label_1",
                "label_type": "report_review",
                "subject_id": "run_1",
            }
        ]
    ]

    created = await repo.create_label(
        {
            "label_id": "label_1",
            "label_type": "report_review",
            "subject_id": "run_1",
            "label_value": {"issue_type": "summary_distortion"},
            "source": "manual",
            "notes": "review notes",
        }
    )
    listed = await repo.list_labels(
        label_type="report_review",
        subject_id="run_1",
        source="manual",
        limit=5,
    )

    assert created["label_id"] == "label_1"
    assert listed == [
        {
            "label_id": "label_1",
            "label_type": "report_review",
            "subject_id": "run_1",
        }
    ]
    assert "INSERT INTO evaluation_labels" in pool.connection.calls[0][1]
    assert "FROM evaluation_labels" in pool.connection.calls[1][1]
    assert "label_type = $1 AND subject_id = $2 AND source = $3" in pool.connection.calls[1][1]
