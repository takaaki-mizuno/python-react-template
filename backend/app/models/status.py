from sqlmodel import SQLModel


class Status(SQLModel, table=False):
    success: bool
    message: str
