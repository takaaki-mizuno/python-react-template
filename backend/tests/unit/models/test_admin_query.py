import pytest

from app.models.admin_query import normalize_admin_search


def test_normalize_admin_search_trims_value() -> None:
    assert normalize_admin_search("  Admin@Example.com  ") == "Admin@Example.com"


def test_normalize_admin_search_converts_blank_to_none() -> None:
    assert normalize_admin_search("   ") is None
    assert normalize_admin_search(None) is None


def test_normalize_admin_search_rejects_values_over_max_length() -> None:
    with pytest.raises(ValueError):
        normalize_admin_search("x" * 6, max_length=5)
