from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os


class Settings(BaseSettings):
    # ── Cron 调度 ──
    cron_collect: str = Field(default="0 * * * *", validation_alias="CRON_COLLECT")
    cron_report: str = Field(default="0 8 * * *", validation_alias="CRON_REPORT")
    cron_events: str = Field(default="", validation_alias="CRON_EVENTS")
    cron_cleanup: str = Field(default="0 3 * * *", validation_alias="CRON_CLEANUP")

    # ── RSS 采集 ──
    rss_timeout_ms: int = Field(default=15000, validation_alias="RSS_TIMEOUT_MS")
    rss_concurrency: int = Field(default=10, validation_alias="RSS_CONCURRENCY")
    rsshub_base_url: str = Field(default="", validation_alias="RSSHUB_BASE_URL")

    # ── 熔断器 ──
    cb_max_failures: int = Field(default=3, validation_alias="CB_MAX_FAILURES")
    cb_cooldown_ms: int = Field(
        default=5 * 60 * 1000, validation_alias="CB_COOLDOWN_MS"
    )

    # ── AI ──
    ai_api_url: str = Field(
        default="https://api.openai.com/v1/chat/completions",
        validation_alias="AI_API_URL",
    )
    ai_api_key: str = Field(default="", validation_alias="AI_API_KEY")
    ai_model: str = Field(default="gpt-4o", validation_alias="AI_MODEL")
    ai_fallback_url: str = Field(default="", validation_alias="AI_FALLBACK_URL")
    ai_fallback_key: str = Field(default="", validation_alias="AI_FALLBACK_KEY")
    ai_fallback_model: str = Field(
        default="gpt-4o-mini", validation_alias="AI_FALLBACK_MODEL"
    )
    ai_timeout_ms: int = Field(default=20000, validation_alias="AI_TIMEOUT_MS")
    ai_max_context_tokens: int = Field(
        default=128000, validation_alias="AI_MAX_CONTEXT_TOKENS"
    )
    ai_use_realtime_market_context: bool = Field(
        default=True, validation_alias="AI_USE_REALTIME_MARKET_CONTEXT"
    )
    ai_market_context_symbols_limit: int = Field(
        default=6, validation_alias="AI_MARKET_CONTEXT_SYMBOLS_LIMIT"
    )
    ai_symbol_search_enabled: bool = Field(
        default=True, validation_alias="AI_SYMBOL_SEARCH_ENABLED"
    )
    ai_symbol_search_timeout_ms: int = Field(
        default=3000, validation_alias="AI_SYMBOL_SEARCH_TIMEOUT_MS"
    )
    asset_symbols_file: str = Field(
        default="src/config/asset_symbols.json", validation_alias="ASSET_SYMBOLS_FILE"
    )

    # ── Alpha Vantage ──
    alpha_vantage_api_key: str = Field(default="", validation_alias="ALPHA_VANTAGE_API_KEY")
    alpha_vantage_cache_ttl_s: int = Field(default=3600, validation_alias="ALPHA_VANTAGE_CACHE_TTL_S")

    # ── LangGraph ──
    use_langgraph: bool = Field(default=False, validation_alias="USE_LANGGRAPH")

    # ── Event Intelligence Runtime ──
    event_intelligence_enabled: bool = Field(
        default=False, validation_alias="EVENT_INTELLIGENCE_ENABLED"
    )
    event_intelligence_postgres_dsn: str = Field(
        default="", validation_alias="EVENT_INTELLIGENCE_POSTGRES_DSN"
    )
    event_intelligence_qdrant_url: str = Field(
        default="", validation_alias="EVENT_INTELLIGENCE_QDRANT_URL"
    )
    event_intelligence_qdrant_api_key: str = Field(
        default="", validation_alias="EVENT_INTELLIGENCE_QDRANT_API_KEY"
    )
    event_intelligence_redis_url: str = Field(
        default="", validation_alias="EVENT_INTELLIGENCE_REDIS_URL"
    )
    event_intelligence_embedding_model: str = Field(
        default="bge-m3", validation_alias="EVENT_INTELLIGENCE_EMBEDDING_MODEL"
    )
    embedding_provider: str = Field(
        default="openai", validation_alias="EMBEDDING_PROVIDER"
    )
    local_embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5", validation_alias="LOCAL_EMBEDDING_MODEL"
    )
    gliner_model: str = Field(
        default="urchade/gliner_multi-v2.1", validation_alias="GLINER_MODEL"
    )
    event_intelligence_reranker_model: str = Field(
        default="bge-reranker-v2-m3",
        validation_alias="EVENT_INTELLIGENCE_RERANKER_MODEL",
    )
    event_intelligence_report_profile: str = Field(
        default="macro_daily", validation_alias="EVENT_INTELLIGENCE_REPORT_PROFILE"
    )
    event_intelligence_store_timeout_ms: int = Field(
        default=5000, validation_alias="EVENT_INTELLIGENCE_STORE_TIMEOUT_MS"
    )
    event_intelligence_store_max_retries: int = Field(
        default=1, validation_alias="EVENT_INTELLIGENCE_STORE_MAX_RETRIES"
    )

    # ── 标题去重 ──
    dedup_similarity_threshold: float = Field(
        default=0.55, validation_alias="DEDUP_SIMILARITY_THRESHOLD"
    )
    dedup_hours_back: int = Field(default=24, validation_alias="DEDUP_HOURS_BACK")

    # ── 研报 ──
    report_max_news: int = Field(default=500, validation_alias="REPORT_MAX_NEWS")
    report_auto_save_predictions: bool = Field(
        default=True, validation_alias="REPORT_AUTO_SAVE_PREDICTIONS"
    )
    data_retention_days: int = Field(default=30, validation_alias="DATA_RETENTION_DAYS")

    # ── 聚类 ──
    cluster_similarity_threshold: float = Field(
        default=0.3, validation_alias="CLUSTER_SIMILARITY_THRESHOLD"
    )

    # ── 趋势检测 ──
    trending_max_tracked_terms: int = Field(
        default=5000, validation_alias="TRENDING_MAX_TRACKED_TERMS"
    )
    trending_max_seen_headlines: int = Field(
        default=50000, validation_alias="TRENDING_MAX_SEEN_HEADLINES"
    )

    # ── 通知推送 ──
    notify_max_retries: int = Field(default=3, validation_alias="NOTIFY_MAX_RETRIES")
    notify_base_delay_ms: int = Field(
        default=1000, validation_alias="NOTIFY_BASE_DELAY_MS"
    )
    feishu_webhook: str = Field(default="", validation_alias="FEISHU_WEBHOOK")
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")

    # ── 翻译 API（事件速报英→中，二选一） ──
    deepl_api_key: str = Field(default="", validation_alias="DEEPL_API_KEY")
    libretranslate_url: str = Field(default="", validation_alias="LIBRETRANSLATE_URL")

    # ── 日志 ──
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_pretty: bool = Field(default=True, validation_alias="LOG_PRETTY")
    log_to_file: bool = Field(default=False, validation_alias="LOG_TO_FILE")
    log_file_path: str = Field(
        default="logs/deepcurrents.log", validation_alias="LOG_FILE_PATH"
    )
    log_to_stderr: bool = Field(default=True, validation_alias="LOG_TO_STDERR")

    # ── 网络 ──
    https_proxy: str = Field(default="", validation_alias="HTTPS_PROXY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    def get_event_intelligence_required_settings(self) -> Dict[str, str]:
        return {
            "EVENT_INTELLIGENCE_POSTGRES_DSN": self.event_intelligence_postgres_dsn,
            "EVENT_INTELLIGENCE_QDRANT_URL": self.event_intelligence_qdrant_url,
            "EVENT_INTELLIGENCE_REDIS_URL": self.event_intelligence_redis_url,
        }

    def validate_event_intelligence_settings(self) -> None:
        if not self.event_intelligence_enabled:
            return

        missing = [
            name
            for name, value in self.get_event_intelligence_required_settings().items()
            if not value.strip()
        ]
        if missing:
            raise ValueError(
                "Event Intelligence runtime enabled but missing required settings: "
                + ", ".join(missing)
            )


CONFIG = Settings()
