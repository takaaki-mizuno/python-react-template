from ipaddress import ip_address
from typing import Any

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


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
