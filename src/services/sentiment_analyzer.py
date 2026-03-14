from __future__ import annotations

from typing import Any

from loguru import logger

# ── transformers lazy import ──

_transformers: Any = None


def _ensure_transformers() -> Any:
    global _transformers
    if _transformers is None:
        try:
            import transformers as _tf

            _transformers = _tf
        except ImportError:
            _transformers = False
            logger.debug("transformers not installed; FinBERT sentiment disabled")
    return _transformers


_NEUTRAL_RESULT: dict[str, Any] = {
    "label": "neutral",
    "score": 0.0,
    "scores": {},
}


# ── FinBERT Sentiment Analyzer ──


class SentimentAnalyzer:
    def __init__(self, *, model_name: str | None = None):
        self._model_name = model_name or "ProsusAI/finbert"
        self._pipeline: Any = None

    def _ensure_pipeline(self) -> bool:
        if self._pipeline is not None:
            return True
        tf = _ensure_transformers()
        if not tf:
            return False
        try:
            self._pipeline = tf.pipeline(
                "sentiment-analysis",
                model=self._model_name,
                return_all_scores=True,
            )
            return True
        except Exception as exc:
            logger.warning(f"Failed to load FinBERT pipeline {self._model_name}: {exc}")
            return False

    async def analyze(self, text: str) -> dict[str, Any]:
        if not text or not self._ensure_pipeline():
            return dict(_NEUTRAL_RESULT)

        import asyncio

        loop = asyncio.get_event_loop()
        try:
            raw = await loop.run_in_executor(None, self._predict, text[:512])
            return self._parse_result(raw)
        except Exception as exc:
            logger.warning(f"FinBERT prediction failed: {exc}")
            return dict(_NEUTRAL_RESULT)

    async def analyze_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        if not texts or not self._ensure_pipeline():
            return [dict(_NEUTRAL_RESULT) for _ in texts]

        import asyncio

        loop = asyncio.get_event_loop()
        try:
            truncated = [t[:512] for t in texts]
            raw_list = await loop.run_in_executor(None, self._predict_batch, truncated)
            return [self._parse_result(r) for r in raw_list]
        except Exception as exc:
            logger.warning(f"FinBERT batch prediction failed: {exc}")
            return [dict(_NEUTRAL_RESULT) for _ in texts]

    def _predict(self, text: str) -> list[dict[str, Any]]:
        return self._pipeline(text)

    def _predict_batch(self, texts: list[str]) -> list[list[dict[str, Any]]]:
        return self._pipeline(texts)

    @staticmethod
    def _parse_result(raw: Any) -> dict[str, Any]:
        if not raw:
            return dict(_NEUTRAL_RESULT)
        # raw is list of dicts with 'label' and 'score' when return_all_scores=True
        scores_list = raw[0] if raw and isinstance(raw[0], list) else raw
        scores: dict[str, float] = {}
        best_label = "neutral"
        best_score = 0.0
        for entry in scores_list:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label", "")).lower()
            score = float(entry.get("score", 0.0))
            scores[label] = round(score, 4)
            if score > best_score:
                best_score = score
                best_label = label
        return {
            "label": best_label,
            "score": round(best_score, 4),
            "scores": scores,
        }


__all__ = ["SentimentAnalyzer"]
