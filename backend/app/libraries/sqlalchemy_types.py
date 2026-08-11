from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import BigInteger, TypeDecorator

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class InetString(TypeDecorator[str | None]):
    impl = postgresql.INET
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        normalized_value = value.split("%", maxsplit=1)[0]
        return str(ip_address(normalized_value))

    def process_result_value(self, value: Any, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return str(value)


class UnixTimestampMillis(TypeDecorator[datetime | None]):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> int | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UnixTimestampMillis requires timezone-aware datetime")
        delta = value.astimezone(UTC) - EPOCH
        return delta // timedelta(milliseconds=1)

    def process_result_value(self, value: Any, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return EPOCH + timedelta(milliseconds=value)
