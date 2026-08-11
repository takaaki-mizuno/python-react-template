from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, field_validator
from pydantic.alias_generators import to_camel
from sqlmodel import SQLModel
from sqlmodel.main import SQLModelConfig

from app.models.admin_user import AdminUserDetail, AdminUserRecord


class AdminUserSchema(SQLModel):
    model_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class AdminUserCreateRequest(AdminUserSchema):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    is_active: bool = True
    roles: list[str] = Field(default_factory=list, max_length=100)


class AdminUserUpdateRequest(AdminUserSchema):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)
    is_active: bool | None = None
    roles: list[str] | None = Field(default=None, max_length=100)

    @field_validator("email", "password", "is_active", "roles", mode="before")
    @classmethod
    def reject_null_for_non_nullable_patch_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null.")
        return value


class AdminUserListItemResponse(AdminUserSchema):
    id: UUID
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
    roles: list[str]

    @classmethod
    def from_record(cls, record: AdminUserRecord) -> "AdminUserListItemResponse":
        return cls(
            id=record.user.id,
            email=record.user.email,
            is_active=record.user.is_active,
            created_at=record.user.created_at,
            updated_at=record.user.updated_at,
            last_login_at=record.user.last_login_at,
            roles=list(record.roles),
        )


class AdminUserResponse(AdminUserListItemResponse):
    permissions: list[str]

    @classmethod
    def from_detail(cls, detail: AdminUserDetail) -> "AdminUserResponse":
        return cls(
            id=detail.user.id,
            email=detail.user.email,
            is_active=detail.user.is_active,
            created_at=detail.user.created_at,
            updated_at=detail.user.updated_at,
            last_login_at=detail.user.last_login_at,
            roles=list(detail.roles),
            permissions=list(detail.permissions),
        )


class AdminUserListResponse(AdminUserSchema):
    items: list[AdminUserListItemResponse]
    total: int
    offset: int
    limit: int
