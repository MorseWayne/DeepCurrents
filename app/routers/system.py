import asyncio
import json
import time

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(tags=["system"])

_start_time = time.time()


@router.get("/system/status")
async def system_status():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _start_time, 1),
    }


@router.get("/system/stream")
async def stream_status(request: Request):
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            data = {
                "uptime": round(time.time() - _start_time, 1),
                "timestamp": time.time(),
            }
            yield {"event": "status", "data": json.dumps(data)}
            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())
