from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.bootstrap.error_handlers import api_error, register_error_handlers


class Payload(BaseModel):
    name: str = Field(min_length=3)


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/unauthorized")
    async def unauthorized():
        raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/duplicate")
    async def duplicate():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "email_already_registered",
                "detail": "Email already registered",
            },
        )

    @app.get("/with-details")
    async def with_details():
        raise api_error(
            400,
            "bad_request",
            "Has details",
            extensions={
                "provider_id": "google",
            },
        )

    @app.get("/unknown-code")
    async def unknown_code():
        raise api_error(409, "totally_unknown_typo", "Unknown code")

    @app.get("/reserved-extension")
    async def reserved_extension():
        raise api_error(
            400,
            "bad_request",
            "Reserved extension",
            extensions={
                "type": "evil",
                "providers": [{
                    "provider_id": "google",
                    "display_name": "Google",
                }],
            },
        )

    @app.get("/custom-cache")
    async def custom_cache():
        raise HTTPException(
            status_code=401,
            detail="Unauthorized",
            headers={"Cache-Control": "private"},
        )

    @app.post("/payload")
    async def payload(_payload: Payload):
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    return app


def test_http_exception_string_detail_uses_problem_details():
    client = TestClient(_app())

    response = client.get("/unauthorized")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "type": "/problems/unauthorized",
        "title": "Unauthorized",
        "status": 401,
        "detail": "Unauthorized",
        "instance": "/unauthorized",
        "code": "unauthorized",
    }


def test_http_exception_preserves_explicit_cache_control_header():
    client = TestClient(_app())

    response = client.get("/custom-cache")

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "private"


def test_http_exception_dict_detail_preserves_code_and_message():
    client = TestClient(_app())

    response = client.get("/duplicate")

    assert response.status_code == 409
    assert response.json() == {
        "type": "/problems/email_already_registered",
        "title": "Email already registered",
        "status": 409,
        "detail": "Email already registered",
        "instance": "/duplicate",
        "code": "email_already_registered",
    }


def test_api_error_accepts_optional_extensions_without_breaking_problem_details():
    client = TestClient(_app())

    response = client.get("/with-details")

    assert response.status_code == 400
    assert response.json() == {
        "type": "/problems/bad_request",
        "title": "Bad request",
        "status": 400,
        "detail": "Has details",
        "instance": "/with-details",
        "code": "bad_request",
        "provider_id": "google",
    }


def test_unknown_problem_code_logs_warning(caplog):
    client = TestClient(_app())

    with caplog.at_level("WARNING", logger="app.bootstrap.error_handlers"):
        response = client.get("/unknown-code")

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"
    assert "Unknown problem code" in caplog.text
    assert "totally_unknown_typo" in caplog.text


def test_reserved_problem_extension_member_is_dropped_and_logged(caplog):
    client = TestClient(_app())

    with caplog.at_level("WARNING", logger="app.bootstrap.error_handlers"):
        response = client.get("/reserved-extension")

    assert response.status_code == 400
    assert response.json()["type"] == "/problems/bad_request"
    assert response.json()["providers"] == [{
        "provider_id": "google",
        "display_name": "Google",
    }]
    assert "evil" not in response.text
    assert "Reserved Problem Details extension member" in caplog.text
    assert "type" in caplog.text


def test_validation_error_uses_problem_details_with_field_errors():
    client = TestClient(_app())

    response = client.post("/payload", json={"name": "x"})

    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/problems/validation_error"
    assert body["title"] == "Validation error"
    assert body["status"] == 422
    assert body["detail"] == "Request validation failed."
    assert body["instance"] == "/payload"
    assert body["code"] == "validation_error"
    assert body["errors"][0]["location"] == "body"
    assert body["errors"][0]["pointer"] == "#/name"
    assert body["errors"][0]["detail"]
    assert body["errors"][0]["code"]


def test_unhandled_exception_hides_internal_message():
    client = TestClient(_app(), raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "type": "/problems/internal_server_error",
        "title": "Internal server error",
        "status": 500,
        "detail": "Internal server error",
        "instance": "/boom",
        "code": "internal_server_error",
    }
