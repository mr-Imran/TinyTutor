from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from services import daily_plan

router = APIRouter(prefix="/api/plan", tags=["plan"])

USER_ID = 1


@router.get("/today")
def today():
    return daily_plan.get_plan(USER_ID)


@router.post("/today/regenerate")
def regenerate():
    return daily_plan.regenerate(USER_ID)


@router.post("/tasks/{task_id:path}/toggle")
def toggle(task_id: str):
    plan = daily_plan.toggle_task(USER_ID, task_id)
    if plan is None:
        raise HTTPException(404, "Task not found in today's plan")
    return plan


@router.get("/calendar.ics")
def calendar(
    days: int = Query(7, ge=1, le=90),
    hour: int = Query(18, ge=0, le=23),
    minute: int = Query(0, ge=0, le=59),
):
    return Response(
        daily_plan.calendar_ics(USER_ID, days, hour, minute),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tinytutor-study-plan.ics"'},
    )
