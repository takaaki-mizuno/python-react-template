from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.controllers import sample_controller
from app.models.status import Status


class StubGetSampleIndexUsecase:

    def handle(self, message: str) -> Status:
        assert message == "Hello, World!"
        return Status(success=True, message="stubbed")


def test_sample_controller_usecase_can_be_overridden_without_injector():
    app = FastAPI()
    app.include_router(sample_controller.router, prefix="/api")
    app.dependency_overrides[
        sample_controller.
        get_sample_index_usecase] = lambda: StubGetSampleIndexUsecase()
    client = TestClient(app)

    response = client.get("/api/sample/")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "stubbed",
    }
