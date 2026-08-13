import math
from datetime import datetime


def unix_timestamp_seconds(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return math.floor(value.timestamp())
