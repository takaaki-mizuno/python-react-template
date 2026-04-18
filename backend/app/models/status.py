from sqlmodel import Field, SQLModel


class Status(SQLModel, table=False):
    success: bool
    message: str
