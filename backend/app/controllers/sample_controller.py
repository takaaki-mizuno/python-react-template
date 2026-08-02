from fastapi import APIRouter, Depends

from app.bootstrap.dependencies import inject
from app.interfaces.usecases.get_sample_index_usecase_interface import \
    GetSampleIndexUsecaseInterface
from app.models.error import ErrorResponse
from app.models.status import Status

get_sample_index_usecase = inject(GetSampleIndexUsecaseInterface)

router = APIRouter(
    prefix="/sample",
    tags=["sample"],
    responses={
        401: {
            "model": ErrorResponse
        },
        403: {
            "model": ErrorResponse
        },
        404: {
            "model": ErrorResponse
        },
    },
)


@router.get("/")
async def sample_index(
    usecase: GetSampleIndexUsecaseInterface = Depends(
        get_sample_index_usecase),
) -> Status:
    return usecase.handle("Hello, World!")
