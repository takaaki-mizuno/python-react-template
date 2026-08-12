from typing import Literal, TypeGuard

LanguageCode = Literal["en", "ja"]
SUPPORTED_LANGUAGE_CODES: tuple[LanguageCode, ...] = ("en", "ja")
DEFAULT_LANGUAGE_CODE: LanguageCode = "ja"


def is_supported_language_code(value: str) -> TypeGuard[LanguageCode]:
    return value in SUPPORTED_LANGUAGE_CODES
