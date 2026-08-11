from datetime import datetime

from app.libraries.sqlalchemy_types import UnixTimestampMillis


def unix_timestamp_millis(value: datetime) -> int:
    bound_value = UnixTimestampMillis().process_bind_param(value, None)
    if bound_value is None:
        raise ValueError("timestamp helper requires a datetime value")
    return bound_value
