from fastapi import APIRouter, Query

from app.services import bridge

router = APIRouter(tags=["events"])


@router.get("/events")
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
):
    return await bridge.list_events(limit=limit, status=status)
