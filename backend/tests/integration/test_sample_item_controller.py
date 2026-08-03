from uuid import UUID

import pytest

pytestmark = pytest.mark.integration


def _assert_error_code(response, code: str) -> None:
    assert response.json()["error"]["code"] == code


def _register(client, email: str) -> None:
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201


def _csrf(client) -> str:
    return client.cookies.get("csrf_token") or client.get("/api/auth/csrf").json()["csrfToken"]


def _create_item(client, title: str, description: str | None = None):
    response = client.post(
        "/api/samples",
        json={
            "title": title,
            "description": description,
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 201
    return response.json()


def test_sample_items_require_authentication(client) -> None:
    response = client.get("/api/samples")

    assert response.status_code == 401
    _assert_error_code(response, "UNAUTHORIZED")


def test_sample_item_create_list_pagination_and_get_use_camel_case(client) -> None:
    _register(client, "sample-a@example.com")
    first = _create_item(client, "First", "First description")
    _create_item(client, "Second", "Second description")

    assert UUID(first["id"])
    assert first["isCompleted"] is False
    assert "createdAt" in first
    assert "updatedAt" in first
    assert "is_completed" not in first

    list_response = client.get("/api/samples")
    assert list_response.status_code == 200
    assert [item["title"] for item in list_response.json()["items"]] == ["Second", "First"]

    first_page = client.get("/api/samples?limit=1")
    assert first_page.status_code == 200
    assert first_page.json()["items"][0]["title"] == "Second"
    assert first_page.json()["nextCursor"]

    second_page = client.get(f"/api/samples?limit=1&cursor={first_page.json()['nextCursor']}")
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["title"] == "First"

    get_response = client.get(f"/api/samples/{first['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "First"


def test_sample_item_patch_semantics_and_validation(client) -> None:
    _register(client, "sample-patch@example.com")
    first = _create_item(client, "First", "First description")

    patch_response = client.patch(
        f"/api/samples/{first['id']}",
        json={
            "title": "Updated",
            "isCompleted": True,
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Updated"
    assert patch_response.json()["description"] == "First description"
    assert patch_response.json()["isCompleted"] is True

    noop_response = client.patch(
        f"/api/samples/{first['id']}",
        json={},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert noop_response.status_code == 200
    assert noop_response.json()["title"] == "Updated"

    clear_response = client.patch(
        f"/api/samples/{first['id']}",
        json={"description": None},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["description"] is None

    validation_response = client.patch(
        f"/api/samples/{first['id']}",
        json={"title": "x" * 121},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert validation_response.status_code == 422

    null_title_response = client.patch(
        f"/api/samples/{first['id']}",
        json={"title": None},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert null_title_response.status_code == 422

    null_completed_response = client.patch(
        f"/api/samples/{first['id']}",
        json={"isCompleted": None},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert null_completed_response.status_code == 422

    typo_response = client.patch(
        f"/api/samples/{first['id']}",
        json={"tittle": "Typo"},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert typo_response.status_code == 422


def test_sample_item_delete_returns_204_and_then_404(client) -> None:
    _register(client, "sample-delete@example.com")
    first = _create_item(client, "First", "First description")

    delete_response = client.delete(
        f"/api/samples/{first['id']}",
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert delete_response.status_code == 204
    missing_response = client.get(f"/api/samples/{first['id']}")
    assert missing_response.status_code == 404
    _assert_error_code(missing_response, "SAMPLE_ITEM_NOT_FOUND")


def test_sample_item_owner_scope_returns_404_for_other_users_items(client) -> None:
    _register(client, "sample-owner-a@example.com")
    second = _create_item(client, "Second", "Second description")

    _register(client, "sample-b@example.com")
    assert client.get(f"/api/samples/{second['id']}").status_code == 404
    assert client.patch(
        f"/api/samples/{second['id']}",
        json={
            "title": "Nope"
        },
        headers={
            "X-CSRF-Token": _csrf(client)
        },
    ).status_code == 404
    assert client.delete(
        f"/api/samples/{second['id']}",
        headers={
            "X-CSRF-Token": _csrf(client)
        },
    ).status_code == 404

    owner_b_list = client.get("/api/samples")
    assert owner_b_list.status_code == 200
    assert owner_b_list.json()["items"] == []


def test_sample_item_post_requires_csrf_header(client) -> None:
    _register(client, "sample-csrf@example.com")

    response = client.post(
        "/api/samples",
        json={
            "title": "No CSRF",
            "description": None,
        },
    )

    assert response.status_code == 403
    _assert_error_code(response, "CSRF_VALIDATION_FAILED")
