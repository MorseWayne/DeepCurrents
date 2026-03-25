from fastapi import APIRouter, HTTPException, Query

from app.services import bridge

router = APIRouter(tags=["reports"])


@router.get("/reports")
async def list_reports(limit: int = Query(20, ge=1, le=100)):
    return await bridge.list_reports(limit=limit)


@router.get("/reports/{report_id}")
async def get_report(report_id: str):
    report = await bridge.get_report(report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report
