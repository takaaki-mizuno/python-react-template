from fastapi import APIRouter

from app.models.status import Status

router = APIRouter(
    tags=["health"],
    responses={
        404: Status(success=False, message="Not found").model_dump(),
    },
)


@router.get("/healthz")
async def healthz() -> Status:
    return Status(success=True, message="ok")
