from fastapi import APIRouter

from app.models.error import problem_response_openapi
from app.models.status import Status

router = APIRouter(
    tags=["health"],
    responses={
        404: problem_response_openapi(),
    },
)


@router.get("/healthz")
async def healthz() -> Status:
    return Status(success=True, message="ok")
