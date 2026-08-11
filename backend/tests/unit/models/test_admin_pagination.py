from app.models.admin_pagination import AdminOffsetPageRequest, AdminOffsetPageResult


def test_admin_offset_page_request_keeps_validated_values() -> None:
    page = AdminOffsetPageRequest(offset=20, limit=10)

    assert page.offset == 20
    assert page.limit == 10


def test_admin_offset_page_result_keeps_items_and_pagination_values() -> None:
    result = AdminOffsetPageResult[str](items=["a", "b"], total=7, offset=2, limit=2)

    assert result.items == ["a", "b"]
    assert result.total == 7
    assert result.offset == 2
    assert result.limit == 2
