from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.error_handlers import register_error_handlers
from app.controllers import sample_controller
from app.models.sample_item import SampleItem, SampleItemListResult
from app.models.sample_item_errors import InvalidSampleItemCursorError, SampleItemNotFoundError


class StubSampleItemUsecase:

    def __init__(self) -> None:
        self.owner_user_id = None

    async def list_items(self, owner_user_id, limit, cursor):
        self.owner_user_id = owner_user_id
        return SampleItemListResult(
            items=[
                SampleItem(
                    id=uuid4(),
                    owner_user_id=owner_user_id,
                    title="Stubbed",
                    description=None,
                    registered_at=datetime(2026, 8, 2, tzinfo=UTC),
                    modified_at=datetime(2026, 8, 2, tzinfo=UTC),
                    created_at=datetime(2026, 8, 2, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 2, tzinfo=UTC),
                )
            ],
            next_cursor=None,
        )

    async def get_item(self, owner_user_id, item_id):
        raise SampleItemNotFoundError


class InvalidCursorUsecase(StubSampleItemUsecase):

    async def list_items(self, owner_user_id, limit, cursor):
        raise InvalidSampleItemCursorError


def _auth_context(user_id):
    return SimpleNamespace(user=SimpleNamespace(id=user_id))


def test_sample_controller_usecase_and_auth_can_be_overridden_without_db() -> None:
    app = FastAPI()
    register_error_handlers(app)
    usecase = StubSampleItemUsecase()
    user_id = uuid4()
    app.include_router(sample_controller.router, prefix="/api")
    app.dependency_overrides[sample_controller.get_sample_item_usecase] = lambda: usecase
    app.dependency_overrides[
        sample_controller.require_current_session] = lambda: _auth_context(user_id)
    client = TestClient(app)

    response = client.get("/api/samples")

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Stubbed"
    assert usecase.owner_user_id == user_id


def test_sample_controller_maps_not_found_to_error_envelope() -> None:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sample_controller.router, prefix="/api")
    app.dependency_overrides[
        sample_controller.get_sample_item_usecase] = lambda: StubSampleItemUsecase()
    app.dependency_overrides[
        sample_controller.require_current_session] = lambda: _auth_context(uuid4())
    client = TestClient(app)

    response = client.get(f"/api/samples/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SAMPLE_ITEM_NOT_FOUND"


def test_sample_controller_maps_invalid_cursor_to_error_envelope() -> None:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(sample_controller.router, prefix="/api")
    app.dependency_overrides[
        sample_controller.get_sample_item_usecase] = lambda: InvalidCursorUsecase()
    app.dependency_overrides[
        sample_controller.require_current_session] = lambda: _auth_context(uuid4())
    client = TestClient(app)

    response = client.get("/api/samples?cursor=bad")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SAMPLE_ITEM_INVALID_CURSOR"
