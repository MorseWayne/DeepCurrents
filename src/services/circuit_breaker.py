import time
from typing import Dict, Any, Optional
from ..utils.logger import get_logger

logger = get_logger("circuit-breaker")

class CircuitBreakerState:
    def __init__(self):
        self.failure_count = 0
        self.cooldown_until = 0
        self.last_success = 0

class CacheEntry:
    def __init__(self, data: Any):
        self.data = data
        self.timestamp = time.time()

class RSSCircuitBreaker:
    def __init__(self, max_failures: int = 3, cooldown_ms: int = 300000, cache_ttl_ms: int = 1800000, max_cache_entries: int = 100):
        self.max_failures = max_failures
        self.cooldown_ms = cooldown_ms
        self.cache_ttl_ms = cache_ttl_ms
        self.max_cache_entries = max_cache_entries
        self._states: Dict[str, CircuitBreakerState] = {}
        self._cache: Dict[str, CacheEntry] = {}

    def is_on_cooldown(self, source_key: str) -> bool:
        state = self._states.get(source_key)
        if not state: return False
        now = time.time() * 1000
        if now < state.cooldown_until: return True
        
        # 冷却期结束，重置
        if state.cooldown_until > 0:
            del self._states[source_key]
        return False

    def record_failure(self, source_key: str):
        state = self._states.get(source_key)
        if not state:
            state = CircuitBreakerState()
            self._states[source_key] = state
        
        state.failure_count += 1
        if state.failure_count >= self.max_failures:
            state.cooldown_until = (time.time() * 1000) + self.cooldown_ms
            logger.warning(f"[熔断] {source_key} 连续失败 {state.failure_count} 次，进入 {self.cooldown_ms / 1000}s 冷却期")

    def record_success(self, source_key: str):
        if source_key in self._states:
            del self._states[source_key]

    def set_cache(self, key: str, data: Any):
        self._cache[key] = CacheEntry(data)
        self._prune_cache()

    def get_cache(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if not entry: return None
        if (time.time() - entry.timestamp) * 1000 > self.cache_ttl_ms:
            del self._cache[key]
            return None
        return entry.data

    def get_stale_cache(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        return entry.data if entry else None

    def _prune_cache(self):
        if len(self._cache) <= self.max_cache_entries: return
        # 按时间戳排序，移除最旧的
        sorted_keys = sorted(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
        for k in sorted_keys[:len(self._cache) - self.max_cache_entries]:
            del self._cache[k]

    def get_summary(self) -> Dict[str, int]:
        now = time.time() * 1000
        on_cooldown = sum(1 for s in self._states.values() if now < s.cooldown_until)
        return {
            "total_sources": len(self._states),
            "on_cooldown": on_cooldown,
            "cached": len(self._cache)
        }
