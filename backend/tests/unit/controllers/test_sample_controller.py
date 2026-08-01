from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.sample_controller import router


def test_sample_router_does_not_document_forbidden_as_402():
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    responses = client.get(
        "/openapi.json").json()["paths"]["/api/sample/"]["get"]["responses"]

    assert "402" not in responses
    assert "403" in responses
