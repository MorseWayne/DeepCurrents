from __future__ import annotations

from typing import Any, Dict, Sequence

from ..utils.logger import get_logger

logger = get_logger("schema-bootstrap")


class SchemaBootstrap:
    TABLE_NAMES: Sequence[str] = (
        "articles",
        "article_features",
        "article_dedup_links",
        "events",
        "event_members",
        "event_scores",
        "event_state_transitions",
        "event_briefs",
        "theme_briefs",
        "report_runs",
        "report_event_links",
        "evaluation_labels",
    )

    def __init__(self, pool: Any):
        self._pool = pool

    async def initialize(self) -> Dict[str, Any]:
        if self._pool is None:
            raise RuntimeError("SchemaBootstrap requires a connected PostgreSQL pool")

        async with self._pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(self._ddl_script())

        logger.info("Event Intelligence schema bootstrap 已完成。")
        return {
            "backend": "postgresql",
            "healthy": True,
            "schema_ready": True,
            "table_count": len(self.TABLE_NAMES),
        }

    def _ddl_script(self) -> str:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS articles (
                article_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                canonical_url TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                clean_content TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                published_at TIMESTAMPTZ,
                ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                tier INTEGER NOT NULL DEFAULT 4,
                source_type TEXT NOT NULL DEFAULT 'other',
                exact_hash TEXT NOT NULL DEFAULT '',
                simhash TEXT NOT NULL DEFAULT '',
                content_length INTEGER NOT NULL DEFAULT 0,
                quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at)",
            "CREATE INDEX IF NOT EXISTS idx_articles_ingested_at ON articles(ingested_at)",
            "CREATE INDEX IF NOT EXISTS idx_articles_normalized_title ON articles(normalized_title)",
            "CREATE INDEX IF NOT EXISTS idx_articles_exact_hash ON articles(exact_hash)",
            """
            CREATE TABLE IF NOT EXISTS article_features (
                article_id TEXT PRIMARY KEY REFERENCES articles(article_id) ON DELETE CASCADE,
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_vector_id TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                simhash TEXT NOT NULL DEFAULT '',
                entities JSONB NOT NULL DEFAULT '[]'::jsonb,
                keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
                quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                feature_version TEXT NOT NULL DEFAULT 'v1',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_article_features_embedding_model ON article_features(embedding_model)",
            """
            CREATE TABLE IF NOT EXISTS article_dedup_links (
                link_id TEXT PRIMARY KEY,
                left_article_id TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
                right_article_id TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
                relation_type TEXT NOT NULL,
                confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
                reason JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(left_article_id, right_article_id, relation_type),
                CHECK (left_article_id <> right_article_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_article_dedup_links_left_article_id ON article_dedup_links(left_article_id)",
            "CREATE INDEX IF NOT EXISTS idx_article_dedup_links_right_article_id ON article_dedup_links(right_article_id)",
            "CREATE INDEX IF NOT EXISTS idx_article_dedup_links_relation_type ON article_dedup_links(relation_type)",
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                canonical_title TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                primary_region TEXT NOT NULL DEFAULT '',
                event_type TEXT NOT NULL DEFAULT '',
                started_at TIMESTAMPTZ,
                last_updated_at TIMESTAMPTZ,
                latest_article_at TIMESTAMPTZ,
                article_count INTEGER NOT NULL DEFAULT 0,
                source_count INTEGER NOT NULL DEFAULT 0,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_events_status ON events(status)",
            "CREATE INDEX IF NOT EXISTS idx_events_latest_article_at ON events(latest_article_at)",
            """
            CREATE TABLE IF NOT EXISTS event_members (
                event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                article_id TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
                role TEXT NOT NULL DEFAULT 'supporting',
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(event_id, article_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_event_members_article_id ON event_members(article_id)",
            "CREATE INDEX IF NOT EXISTS idx_event_members_role ON event_members(role)",
            """
            CREATE TABLE IF NOT EXISTS event_scores (
                event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                profile TEXT NOT NULL,
                threat_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                market_impact_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                novelty_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                corroboration_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                source_quality_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                velocity_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                uncertainty_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                total_score DOUBLE PRECISION NOT NULL DEFAULT 0,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(event_id, profile)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_event_scores_total_score ON event_scores(total_score)",
            """
            CREATE TABLE IF NOT EXISTS event_state_transitions (
                transition_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                from_state TEXT NOT NULL DEFAULT '',
                to_state TEXT NOT NULL,
                trigger_article_id TEXT REFERENCES articles(article_id) ON DELETE SET NULL,
                reason TEXT NOT NULL DEFAULT '',
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_event_state_transitions_event_id ON event_state_transitions(event_id)",
            "CREATE INDEX IF NOT EXISTS idx_event_state_transitions_created_at ON event_state_transitions(created_at)",
            """
            CREATE TABLE IF NOT EXISTS event_briefs (
                brief_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                version TEXT NOT NULL DEFAULT 'v1',
                summary TEXT NOT NULL DEFAULT '',
                brief_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                model TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(event_id, version)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS theme_briefs (
                theme_brief_id TEXT PRIMARY KEY,
                theme_key TEXT NOT NULL,
                report_date DATE,
                version TEXT NOT NULL DEFAULT 'v1',
                brief_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(theme_key, report_date, version)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_theme_briefs_theme_key ON theme_briefs(theme_key)",
            """
            CREATE TABLE IF NOT EXISTS report_runs (
                report_run_id TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                report_date DATE,
                status TEXT NOT NULL DEFAULT 'pending',
                budget_tokens INTEGER NOT NULL DEFAULT 0,
                input_event_count INTEGER NOT NULL DEFAULT 0,
                selected_event_count INTEGER NOT NULL DEFAULT 0,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(report_date, profile)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS report_event_links (
                report_run_id TEXT NOT NULL REFERENCES report_runs(report_run_id) ON DELETE CASCADE,
                event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
                rank INTEGER NOT NULL DEFAULT 0,
                included BOOLEAN NOT NULL DEFAULT TRUE,
                rationale TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(report_run_id, event_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_report_event_links_event_id ON report_event_links(event_id)",
            """
            CREATE TABLE IF NOT EXISTS evaluation_labels (
                label_id TEXT PRIMARY KEY,
                label_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                label_value JSONB NOT NULL DEFAULT '{}'::jsonb,
                source TEXT NOT NULL DEFAULT 'manual',
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_evaluation_labels_subject ON evaluation_labels(label_type, subject_id)",
        ]
        return (
            ";\n".join(
                statement.strip() for statement in statements if statement.strip()
            )
            + ";\n"
        )
