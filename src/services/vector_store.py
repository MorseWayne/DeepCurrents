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

    async def query_similar_points(
        self,
        collection_name: str,
        *,
        query_vector: Sequence[float],
        limit: int = 10,
        score_threshold: float | None = None,
        with_payload: bool | Sequence[str] = True,
    ) -> list[dict[str, Any]]:
        client = self._require_client()
        values = [float(item) for item in query_vector]
        if not values:
            raise ValueError("query_vector must not be empty")

        points: Any
        if hasattr(client, "query_points"):
            response = await client.query_points(
                collection_name=collection_name,
                query=values,
                limit=limit,
                with_payload=with_payload,
                with_vectors=False,
                score_threshold=score_threshold,
            )
            points = getattr(response, "points", response)
        elif hasattr(client, "search"):
            points = await client.search(
                collection_name=collection_name,
                query_vector=values,
                limit=limit,
                with_payload=with_payload,
                score_threshold=score_threshold,
            )
        elif hasattr(client, "search_points"):
            models = self._require_models()
            request = models.SearchRequest(
                vector=values,
                limit=limit,
                with_payload=with_payload,
                with_vector=False,
                score_threshold=score_threshold,
            )
            response = await client.search_points(
                collection_name=collection_name,
                search_request=request,
            )
            points = getattr(response, "result", None) or getattr(
                response, "points", response
            )
        else:
            raise RuntimeError(
                "Vector store client does not support similarity queries"
            )

        return [self._serialize_scored_point(point) for point in points]

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

    @staticmethod
    def _serialize_scored_point(point: Any) -> dict[str, Any]:
        if isinstance(point, Mapping):
            return dict(point)
        if hasattr(point, "model_dump"):
            return point.model_dump()
        if hasattr(point, "dict"):
            return point.dict()
        serialized = {
            "id": getattr(point, "id", None),
            "score": getattr(point, "score", None),
            "payload": getattr(point, "payload", None),
        }
        vector = getattr(point, "vector", None)
        if vector is not None:
            serialized["vector"] = vector
        return serialized
