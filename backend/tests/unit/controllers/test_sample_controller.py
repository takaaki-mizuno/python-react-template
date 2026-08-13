from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers.sample_controller import router


def test_sample_router_documents_rest_crud_contract() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    paths = client.get("/openapi.json").json()["paths"]

    assert "/api/sample/" not in paths
    assert set(paths["/api/samples"].keys()) == {"get", "post"}
    assert set(paths["/api/samples/{item_id}"].keys()) == {"get", "patch", "delete"}


def test_sample_router_documents_problem_details_error_response() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    client = TestClient(app)

    paths = client.get("/openapi.json").json()["paths"]

    list_responses = paths["/api/samples"]["get"]["responses"]
    assert set(list_responses) == {"200", "400", "401", "422"}
    assert list_responses["400"]["content"]["application/problem+json"]["schema"][
        "$ref"] == "#/components/schemas/ProblemDetails"
    assert "application/json" not in list_responses["400"].get("content", {})
    assert list_responses["401"]["content"]["application/problem+json"]["schema"][
        "$ref"] == "#/components/schemas/ProblemDetails"

    post_responses = paths["/api/samples"]["post"]["responses"]
    assert set(post_responses) == {"201", "401", "403", "422"}

    get_item_responses = paths["/api/samples/{item_id}"]["get"]["responses"]
    assert set(get_item_responses) == {"200", "401", "404", "422"}
    assert get_item_responses["404"]["content"]["application/problem+json"]["schema"][
        "$ref"] == "#/components/schemas/ProblemDetails"

    patch_responses = paths["/api/samples/{item_id}"]["patch"]["responses"]
    assert set(patch_responses) == {"200", "401", "403", "404", "422"}

    delete_responses = paths["/api/samples/{item_id}"]["delete"]["responses"]
    assert set(delete_responses) == {"204", "401", "403", "404", "422"}
