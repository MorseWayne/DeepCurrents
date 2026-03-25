from fastapi import APIRouter

from app.services import bridge

router = APIRouter(tags=["sources"])


@router.get("/sources")
async def list_sources():
    return await bridge.get_source_statuses()
