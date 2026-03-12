from __future__ import annotations

import importlib
from typing import Any, Dict, Mapping, Sequence

from ..utils.logger import get_logger

logger = get_logger("vector-store")


_DISTANCE_MAP = {
    "cosine": "COSINE",
    "dot": "DOT",
    "euclid": "EUCLID",
    "manhattan": "MANHATTAN",
}


class VectorStore:
    def __init__(
        self,
        url: str,
        *,
        api_key: str = "",
        timeout_ms: int = 5000,
        client: Any | None = None,
    ):
        self.url = url
        self.api_key = api_key
        self.timeout_ms = timeout_ms
        self._client = client
        self._owns_client = client is None
        self._models = None

    async def connect(self) -> None:
        if self._client is not None:
            if self._models is None:
                self._load_models()
            return

        try:
            qdrant_client = importlib.import_module("qdrant_client")
        except ImportError as exc:
            raise ImportError(
                "VectorStore requires `qdrant-client`. Install it via requirements.txt."
            ) from exc

        self._client = qdrant_client.AsyncQdrantClient(
            url=self.url,
            api_key=self.api_key or None,
            timeout=max(self.timeout_ms / 1000, 1),
        )
        self._load_models()
        logger.info("Qdrant vector store 已连接。")

    async def health_check(self) -> Dict[str, Any]:
        client = self._require_client()
        collections = await client.get_collections()
        items = getattr(collections, "collections", collections)
        count = len(items)
        return {
            "backend": "qdrant",
            "healthy": True,
            "collections": count,
        }

    async def ensure_collection(
        self,
        collection_name: str,
        *,
        vector_size: int,
        distance: str = "cosine",
    ) -> None:
        client = self._require_client()
        if vector_size <= 0:
            raise ValueError("vector_size must be positive")

        exists = await client.collection_exists(collection_name=collection_name)
        if exists:
            return

        models = self._require_models()
        distance_value = self._distance_value(distance)
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=distance_value,
            ),
        )

    async def upsert_point(
        self,
        collection_name: str,
        *,
        point_id: str | int,
        vector: Sequence[float],
        payload: Mapping[str, Any] | None = None,
        wait: bool = True,
    ) -> Dict[str, Any]:
        client = self._require_client()
        values = [float(item) for item in vector]
        if not values:
            raise ValueError("vector must not be empty")

        models = self._require_models()
        result = await client.upsert(
            collection_name=collection_name,
            wait=wait,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=values,
                    payload=dict(payload or {}),
                )
            ],
        )
        if hasattr(result, "model_dump"):
            return result.model_dump()
        if isinstance(result, dict):
            return result
        if hasattr(result, "dict"):
            return result.dict()
        return {"result": result}

    async def close(self) -> None:
        if self._client is None:
            return
        if self._owns_client:
            if hasattr(self._client, "close"):
                await self._client.close()
            elif hasattr(self._client, "aclose"):
                await self._client.aclose()
        self._client = None
        self._models = None

    def _load_models(self) -> None:
        if self._models is not None:
            return
        try:
            self._models = importlib.import_module("qdrant_client.models")
        except ImportError:
            qdrant_client = importlib.import_module("qdrant_client")
            self._models = qdrant_client.models

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Vector store not connected")
        if self._models is None:
            self._load_models()
        return self._client

    def _require_models(self) -> Any:
        if self._models is None:
            self._load_models()
        return self._models

    def _distance_value(self, distance: str) -> Any:
        normalized = distance.strip().lower()
        member = _DISTANCE_MAP.get(normalized)
        if member is None:
            raise ValueError(f"Unsupported Qdrant distance: {distance}")
        return getattr(self._require_models().Distance, member)
