def normalize_admin_search(value: str | None, *, max_length: int = 320) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if normalized == "":
        return None
    if len(normalized) > max_length:
        raise ValueError("Search query is too long.")
    return normalized


def escape_like_search(value: str, *, escape_char: str = "\\") -> str:
    return (value.replace(escape_char, escape_char + escape_char).replace(
        "%",
        escape_char + "%",
    ).replace("_", escape_char + "_"))
