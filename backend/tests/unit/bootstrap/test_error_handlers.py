from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.bootstrap.error_handlers import register_error_handlers


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
                "code": "EMAIL_ALREADY_REGISTERED",
                "message": "Email already registered",
            },
        )

    @app.post("/payload")
    async def payload(_payload: Payload):
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("boom")

    return app


def test_http_exception_string_detail_uses_error_envelope():
    client = TestClient(_app())

    response = client.get("/unauthorized")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Unauthorized",
            "details": [],
        }
    }


def test_http_exception_dict_detail_preserves_code_and_message():
    client = TestClient(_app())

    response = client.get("/duplicate")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "EMAIL_ALREADY_REGISTERED",
            "message": "Email already registered",
            "details": [],
        }
    }


def test_validation_error_uses_error_envelope_with_field_details():
    client = TestClient(_app())

    response = client.post("/payload", json={"name": "x"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Validation failed"
    assert body["error"]["details"][0]["loc"] == ["body", "name"]
    assert body["error"]["details"][0]["message"]
    assert body["error"]["details"][0]["type"]


def test_unhandled_exception_hides_internal_message():
    client = TestClient(_app(), raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "INTERNAL_SERVER_ERROR",
            "message": "Internal server error",
            "details": [],
        }
    }
