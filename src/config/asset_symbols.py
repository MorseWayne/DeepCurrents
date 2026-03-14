import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .settings import CONFIG

_rapidfuzz: Any = None


def _ensure_rapidfuzz() -> Any:
    global _rapidfuzz
    if _rapidfuzz is None:
        try:
            from rapidfuzz import fuzz as _rf

            _rapidfuzz = _rf
        except ImportError:
            _rapidfuzz = False
    return _rapidfuzz


# Fallback map to avoid total failure when file is missing/invalid.
DEFAULT_FALLBACK_MAP: Dict[str, str] = {
    "gold": "GC=F",
    "oil": "CL=F",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
    "s&p 500": "^GSPC",
    "dxy": "DX-Y.NYB",
}

_cache: Dict[str, str] = {}
_cache_file: Optional[str] = None
_cache_mtime: Optional[float] = None


def _normalize_map(data: object) -> Dict[str, str]:
    if not isinstance(data, dict):
        return {}

    normalized: Dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        key = k.strip().lower()
        val = v.strip()
        if key and val:
            normalized[key] = val
    return normalized


def _load_map_from_file(path: Path) -> Dict[str, str]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return _normalize_map(data)
    except Exception:
        return {}


def get_asset_symbol_map(extra_map: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    global _cache, _cache_file, _cache_mtime

    path = Path(CONFIG.asset_symbols_file)
    file_str = str(path.resolve())
    file_mtime = path.stat().st_mtime if path.exists() else None

    if _cache and _cache_file == file_str and _cache_mtime == file_mtime:
        merged = dict(_cache)
    else:
        from_file = _load_map_from_file(path)
        merged = from_file or dict(DEFAULT_FALLBACK_MAP)
        _cache = dict(merged)
        _cache_file = file_str
        _cache_mtime = file_mtime

    if extra_map:
        merged.update(_normalize_map(extra_map))
    return merged


def resolve_asset_symbol(
    asset_class: str, symbol_map: Optional[Dict[str, str]] = None
) -> Optional[str]:
    if not asset_class:
        return None

    normalized = asset_class.strip().lower()
    merged_map = get_asset_symbol_map(symbol_map)
    # Prefer longer keys first to avoid short-token collisions.
    for key in sorted(merged_map.keys(), key=len, reverse=True):
        if key in normalized:
            return merged_map[key]

    rf = _ensure_rapidfuzz()
    if rf:
        best_key = ""
        best_score = 0
        for key in merged_map:
            score: int = rf.partial_ratio(normalized, key)
            if score > best_score:
                best_score = score
                best_key = key
        if best_score >= 75 and best_key:
            return merged_map[best_key]

    return None


def get_default_market_symbols(
    limit: int = 6, symbol_map: Optional[Dict[str, str]] = None
) -> List[str]:
    merged_map = get_asset_symbol_map(symbol_map)
    safe_limit = max(limit, 1)
    symbols: List[str] = []
    seen = set()

    for symbol in merged_map.values():
        clean = symbol.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        symbols.append(clean)
        if len(symbols) >= safe_limit:
            break

    if symbols:
        return symbols

    fallback = []
    seen_fallback = set()
    for symbol in DEFAULT_FALLBACK_MAP.values():
        if symbol not in seen_fallback:
            seen_fallback.add(symbol)
            fallback.append(symbol)
        if len(fallback) >= safe_limit:
            break
    return fallback
