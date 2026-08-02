from fastapi import APIRouter

from app.models.error import ErrorResponse
from app.models.status import Status

router = APIRouter(
    tags=["health"],
    responses={
        404: {
            "model": ErrorResponse
        },
    },
)


@router.get("/healthz")
async def healthz() -> Status:
    return Status(success=True, message="ok")
