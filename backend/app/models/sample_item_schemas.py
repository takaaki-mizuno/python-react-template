from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator
from pydantic.alias_generators import to_camel
from sqlmodel import SQLModel
from sqlmodel.main import SQLModelConfig

from app.models.sample_item import SampleItem


class SampleItemSchema(SQLModel):
    model_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class SampleItemCreateRequest(SampleItemSchema):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class SampleItemUpdateRequest(SampleItemSchema):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    is_completed: bool | None = None

    @field_validator("title", "is_completed", mode="before")
    @classmethod
    def reject_null_for_non_nullable_patch_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null.")
        return value


class SampleItemResponse(SampleItemSchema):
    id: UUID
    title: str
    description: str | None
    is_completed: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_item(cls, item: SampleItem) -> "SampleItemResponse":
        return cls(
            id=item.id,
            title=item.title,
            description=item.description,
            is_completed=item.is_completed,
            created_at=item.registered_at,
            updated_at=item.modified_at,
        )


class SampleItemListResponse(SampleItemSchema):
    items: list[SampleItemResponse]
    next_cursor: str | None
