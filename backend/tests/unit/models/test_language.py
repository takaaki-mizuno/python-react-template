from typing import assert_type

from app.models.language import (DEFAULT_LANGUAGE_CODE, SUPPORTED_LANGUAGE_CODES, LanguageCode,
                                 is_supported_language_code)


def test_supported_language_codes_are_en_and_ja() -> None:
    assert SUPPORTED_LANGUAGE_CODES == ("en", "ja")
    assert DEFAULT_LANGUAGE_CODE == "ja"


def test_is_supported_language_code_accepts_only_lowercase_supported_values() -> None:
    assert is_supported_language_code("en") is True
    assert is_supported_language_code("ja") is True
    assert is_supported_language_code("fr") is False
    assert is_supported_language_code("") is False
    assert is_supported_language_code("EN") is False


def test_language_code_type_is_exported() -> None:
    value: LanguageCode = "ja"

    assert_type(value, LanguageCode)
