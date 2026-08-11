from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.route import setup_routes


def _client_with_static(static_directory: Path) -> TestClient:
    app = FastAPI()
    setup_routes(app, static_directory=static_directory)
    return TestClient(app)


def test_setup_routes_starts_without_static_directory(tmp_path):
    client = _client_with_static(tmp_path / "missing-static")

    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "ok"}


def test_healthz_documents_error_envelope_for_not_found(tmp_path):
    client = _client_with_static(tmp_path / "missing-static")

    responses = client.get("/openapi.json").json()["paths"]["/api/healthz"]["get"]["responses"]

    assert responses["404"]["content"]["application/json"]["schema"][
        "$ref"] == "#/components/schemas/ErrorResponse"


def test_admin_users_route_is_included_in_openapi(tmp_path):
    client = _client_with_static(tmp_path / "missing-static")

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/admin/users" in paths
    assert "/api/admin/users/{user_id}" in paths


def test_setup_routes_skips_static_mount_when_index_html_is_missing(
    tmp_path,
    caplog,
):
    (tmp_path / "placeholder.txt").write_text("", encoding="utf-8")

    with caplog.at_level("WARNING", logger="app.bootstrap.route"):
        client = _client_with_static(tmp_path)

    assert client.get("/api/healthz").status_code == 200
    assert client.get("/login").status_code == 404
    assert "index.html" in caplog.text


def test_spa_deep_link_falls_back_to_index_html(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/login", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert response.text == "<main>spa shell</main>"


def test_spa_deep_link_accepts_wildcard_accept_header(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/login", headers={"accept": "*/*"})

    assert response.status_code == 200
    assert response.text == "<main>spa shell</main>"


def test_spa_deep_link_allows_dotted_slug(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/users/john.doe", headers={"accept": "text/html"})

    assert response.status_code == 200
    assert response.text == "<main>spa shell</main>"


def test_static_assets_are_served_without_spa_fallback(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.css").write_text("body { color: black; }", encoding="utf-8")
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/assets/app.css")

    assert response.status_code == 200
    assert response.text == "body { color: black; }"


def test_missing_static_asset_does_not_fall_back_to_spa_index(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/assets/missing.js", headers={"accept": "text/html"})

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"


def test_missing_known_static_extension_does_not_fall_back_to_spa_index(tmp_path, ):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/favicon.ico", headers={"accept": "*/*"})

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"


def test_missing_otf_font_does_not_fall_back_to_spa_index(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/fonts/x.otf", headers={"accept": "*/*"})

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"


def test_non_html_request_does_not_fall_back_to_spa_index(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/login", headers={"accept": "application/json"})

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"


def test_unknown_api_path_does_not_fall_back_to_spa_index(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/api/unknown")

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"


def test_unknown_api_post_returns_404_when_spa_static_is_mounted(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.post("/api/unknown")

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"


def test_uppercase_api_path_does_not_fall_back_to_spa_index(tmp_path):
    (tmp_path / "index.html").write_text("<main>spa shell</main>", encoding="utf-8")
    client = _client_with_static(tmp_path)

    response = client.get("/API/unknown")

    assert response.status_code == 404
    assert response.text != "<main>spa shell</main>"
