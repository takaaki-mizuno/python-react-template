from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.bootstrap.dependencies import inject
from app.bootstrap.error_handlers import api_error
from app.controllers.auth_dependencies import require_current_session
from app.interfaces.usecases.sample_item_usecase_interface import SampleItemUsecaseInterface
from app.models.auth_context import AuthenticatedSessionContext
from app.models.error import ErrorResponse
from app.models.sample_item import SampleItemUpdateChanges
from app.models.sample_item_errors import InvalidSampleItemCursorError, SampleItemNotFoundError
from app.models.sample_item_schemas import (SampleItemCreateRequest, SampleItemListResponse,
                                            SampleItemResponse, SampleItemUpdateRequest)

ErrorResponses = dict[int | str, dict[str, Any]]
ERROR_RESPONSE: dict[str, Any] = {"model": ErrorResponse}
LIST_ERROR_RESPONSES: ErrorResponses = {
    400: ERROR_RESPONSE,
    401: ERROR_RESPONSE,
    422: ERROR_RESPONSE
}
CREATE_ERROR_RESPONSES: ErrorResponses = {
    401: ERROR_RESPONSE,
    403: ERROR_RESPONSE,
    422: ERROR_RESPONSE,
}
GET_ITEM_ERROR_RESPONSES: ErrorResponses = {
    401: ERROR_RESPONSE,
    404: ERROR_RESPONSE,
    422: ERROR_RESPONSE,
}
UPDATE_ERROR_RESPONSES: ErrorResponses = {
    401: ERROR_RESPONSE,
    403: ERROR_RESPONSE,
    404: ERROR_RESPONSE,
    422: ERROR_RESPONSE,
}
DELETE_ERROR_RESPONSES: ErrorResponses = UPDATE_ERROR_RESPONSES

get_sample_item_usecase = inject(SampleItemUsecaseInterface)

router = APIRouter(prefix="/samples", tags=["samples"])


@router.get("", response_model=SampleItemListResponse, responses=LIST_ERROR_RESPONSES)
async def list_sample_items(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    auth_context: AuthenticatedSessionContext = Depends(require_current_session),
    usecase: SampleItemUsecaseInterface = Depends(get_sample_item_usecase),
) -> SampleItemListResponse:
    try:
        result = await usecase.list_items(auth_context.user.id, limit=limit, cursor=cursor)
    except InvalidSampleItemCursorError as error:
        raise api_error(
            400,
            "SAMPLE_ITEM_INVALID_CURSOR",
            "Invalid sample item cursor",
        ) from error
    return SampleItemListResponse(
        items=[SampleItemResponse.from_item(item) for item in result.items],
        next_cursor=result.next_cursor,
    )


@router.post(
    "",
    response_model=SampleItemResponse,
    status_code=201,
    responses=CREATE_ERROR_RESPONSES,
)
async def create_sample_item(
        payload: SampleItemCreateRequest,
        auth_context: AuthenticatedSessionContext = Depends(require_current_session),
        usecase: SampleItemUsecaseInterface = Depends(get_sample_item_usecase),
) -> SampleItemResponse:
    item = await usecase.create_item(
        auth_context.user.id,
        title=payload.title,
        description=payload.description,
    )
    return SampleItemResponse.from_item(item)


@router.get("/{item_id}", response_model=SampleItemResponse, responses=GET_ITEM_ERROR_RESPONSES)
async def get_sample_item(
        item_id: UUID,
        auth_context: AuthenticatedSessionContext = Depends(require_current_session),
        usecase: SampleItemUsecaseInterface = Depends(get_sample_item_usecase),
) -> SampleItemResponse:
    try:
        item = await usecase.get_item(auth_context.user.id, item_id)
    except SampleItemNotFoundError as error:
        raise _not_found_error() from error
    return SampleItemResponse.from_item(item)


@router.patch("/{item_id}", response_model=SampleItemResponse, responses=UPDATE_ERROR_RESPONSES)
async def update_sample_item(
        item_id: UUID,
        payload: SampleItemUpdateRequest,
        auth_context: AuthenticatedSessionContext = Depends(require_current_session),
        usecase: SampleItemUsecaseInterface = Depends(get_sample_item_usecase),
) -> SampleItemResponse:
    changes = SampleItemUpdateChanges(
        title=payload.title,
        description=payload.description,
        is_completed=payload.is_completed,
        fields_set=frozenset(payload.model_fields_set),
    )
    try:
        item = await usecase.update_item(auth_context.user.id, item_id, changes)
    except SampleItemNotFoundError as error:
        raise _not_found_error() from error
    return SampleItemResponse.from_item(item)


@router.delete("/{item_id}", status_code=204, responses=DELETE_ERROR_RESPONSES)
async def delete_sample_item(
        item_id: UUID,
        auth_context: AuthenticatedSessionContext = Depends(require_current_session),
        usecase: SampleItemUsecaseInterface = Depends(get_sample_item_usecase),
) -> Response:
    try:
        await usecase.delete_item(auth_context.user.id, item_id)
    except SampleItemNotFoundError as error:
        raise _not_found_error() from error
    return Response(status_code=204)


def _not_found_error() -> HTTPException:
    return api_error(
        404,
        "SAMPLE_ITEM_NOT_FOUND",
        "Sample item not found",
    )
