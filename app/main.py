"""DeepCurrents Web API — FastAPI 入口。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="DeepCurrents API",
    version="1.0.0",
    description="AI-driven global intelligence aggregation engine",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


from app.routers import reports, events, sources, system
app.include_router(reports.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(system.router, prefix="/api")
