from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import UnixTimestampMillis
from app.models.sample_item import SampleItem
from app.models.sample_item_schemas import (SampleItemCreateRequest, SampleItemResponse,
                                            SampleItemUpdateRequest)


def test_sample_item_table_metadata() -> None:
    assert SampleItem.__tablename__ == "sample_items"
    table = SQLModel.metadata.tables["sample_items"]

    assert set(table.columns.keys()) == {
        "id",
        "owner_user_id",
        "title",
        "description",
        "is_completed",
        "registered_at",
        "modified_at",
        "created_at",
        "updated_at",
    }
    foreign_key = next(iter(table.c.owner_user_id.foreign_keys))
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "CASCADE"
    assert table.c.updated_at.onupdate is not None
    assert table.c.updated_at.onupdate.arg.__name__ == utcnow.__name__
    assert table.c.updated_at.onupdate.arg.__module__ == utcnow.__module__
    assert isinstance(table.c.registered_at.type, UnixTimestampMillis)


def test_sample_item_request_validation_and_snake_case() -> None:
    create_request = SampleItemCreateRequest(title="Write tests", description=None)
    assert create_request.model_dump(by_alias=True) == {
        "title": "Write tests",
        "description": None,
    }

    update_request = SampleItemUpdateRequest(is_completed=True)
    assert update_request.is_completed is True
    assert update_request.model_dump(exclude_unset=True) == {
        "is_completed": True,
    }


def test_sample_item_update_distinguishes_omitted_field_from_null() -> None:
    omitted = SampleItemUpdateRequest()
    explicit_null = SampleItemUpdateRequest(description=None)

    assert omitted.model_dump(exclude_unset=True) == {}
    assert explicit_null.model_dump(exclude_unset=True) == {"description": None}
    assert explicit_null.model_fields_set == {"description"}


@pytest.mark.parametrize("payload", [{"title": None}, {"is_completed": None}])
def test_sample_item_update_rejects_null_for_non_nullable_fields(payload) -> None:
    with pytest.raises(ValidationError):
        SampleItemUpdateRequest.model_validate(payload)


def test_sample_item_requests_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        SampleItemUpdateRequest.model_validate({"tittle": "typo"})


def test_sample_item_response_serializes_snake_case_unix_timestamp_seconds() -> None:
    item_id = uuid4()
    owner_user_id = uuid4()
    registered_at = datetime(2026, 8, 2, 1, 2, 3, tzinfo=UTC)
    modified_at = datetime(2026, 8, 2, 4, 5, 6, tzinfo=UTC)
    created_at = datetime(2026, 8, 3, 1, 2, 3, tzinfo=UTC)
    updated_at = datetime(2026, 8, 3, 4, 5, 6, tzinfo=UTC)
    item = SampleItem(
        id=item_id,
        owner_user_id=owner_user_id,
        title="Write docs",
        description="Use this sample as the template.",
        is_completed=True,
        registered_at=registered_at,
        modified_at=modified_at,
        created_at=created_at,
        updated_at=updated_at,
    )

    response = SampleItemResponse.from_item(item)

    assert response.model_dump(mode="json") == {
        "id": str(item_id),
        "title": "Write docs",
        "description": "Use this sample as the template.",
        "is_completed": True,
        "created_at": 1785632523,
        "updated_at": 1785643506,
    }
