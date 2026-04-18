from fastapi import APIRouter, HTTPException, Query, Request

from app.models.status import Status

router = APIRouter(
    tags=["health"],
    responses={
        404: Status(success=False, message="Not found").model_dump(),
    },
)


@router.get("/healthz")
async def healthz(request: Request) -> Status:
    return Status(success=True, message="ok")
