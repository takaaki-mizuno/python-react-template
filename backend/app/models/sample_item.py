from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, text
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow


@dataclass(frozen=True, slots=True)
class SampleItemCursor:
    created_at: datetime
    id: UUID


@dataclass(frozen=True, slots=True)
class SampleItemListResult:
    items: list["SampleItem"]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class SampleItemUpdateChanges:
    title: str | None = None
    description: str | None = None
    is_completed: bool | None = None
    fields_set: frozenset[str] = field(default_factory=frozenset)


class SampleItem(SQLModel, table=True):
    __tablename__ = "sample_items"
    __table_args__ = (Index("ix_sample_items_owner_user_id_created_at_id", "owner_user_id",
                            "created_at", "id"), )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_user_id: UUID = Field(sa_column=Column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ), )
    title: str = Field(sa_column=Column(String(length=120), nullable=False), )
    description: str | None = Field(
        default=None,
        sa_column=Column(String(length=1000), nullable=True),
    )
    is_completed: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )
