from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app import schemas as s
from app.service import WindService

router = APIRouter(prefix="/api")


def get_service(request: Request) -> WindService:
    service: WindService = request.app.state.service
    return service


Service = Annotated[WindService, Depends(get_service)]
Cutoff = Annotated[time | None, Query(description="Decision cutoff, UK local time (HH:MM)")]


def _cutoff(service: WindService, cutoff: time | None) -> time:
    # Seconds don't mean anything here and would fragment the cache.
    return (cutoff or service.settings.default_cutoff).replace(second=0, microsecond=0)


@router.get("/health")
def health(service: Service) -> s.Health:
    return s.Health(status="ok", fetched_at=service.fetched_at)


@router.get("/meta")
def meta(service: Service) -> s.Meta:
    return service.meta()


@router.get("/decision")
def decision(service: Service, day: date, cutoff: Cutoff = None) -> s.Decision:
    settings = service.settings
    if not settings.decision_start <= day <= settings.decision_end:
        raise HTTPException(
            422,
            f"day must be between {settings.decision_start} and {settings.decision_end}",
        )
    return service.decision(day, _cutoff(service, cutoff))


@router.get("/accuracy")
def accuracy(service: Service, cutoff: Cutoff = None) -> s.Accuracy:
    return service.accuracy(_cutoff(service, cutoff))


@router.get("/lead-time")
def lead_time(service: Service) -> s.LeadTime:
    return service.lead_time()


@router.get("/horizon")
def horizon(service: Service, hours: Annotated[float, Query(ge=0, le=48)] = 24) -> s.Horizon:
    return service.horizon(hours)


@router.get("/export/decisions.csv", response_class=PlainTextResponse)
def export_decisions(service: Service, cutoff: Cutoff = None) -> PlainTextResponse:
    c = _cutoff(service, cutoff)
    return PlainTextResponse(
        service.export_csv(c),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="windsight-decisions-{c:%H%M}.csv"'},
    )
