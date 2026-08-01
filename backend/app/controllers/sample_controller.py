from fastapi import APIRouter, Request

from app.interfaces.usecases.get_sample_index_usecase_interface import \
    GetSampleIndexUsecaseInterface
from app.models.status import Status

router = APIRouter(
    prefix="/sample",
    tags=["sample"],
    responses={
        401: Status(success=False, message="Unauthorized").model_dump(),
        403: Status(success=False, message="Forbidden").model_dump(),
        404: Status(success=False, message="Not found").model_dump(),
    },
)


@router.get("/")
async def sample_index(request: Request) -> Status:
    usecase = request.app.state.injector.get(GetSampleIndexUsecaseInterface)
    return usecase.handle("Hello, World!")
