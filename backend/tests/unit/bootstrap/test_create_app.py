import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bootstrap import create_app as create_app_module
from app.config import Config
from app.config.auth import AuthSettings
from app.libraries.password_hasher import PasswordHashExecutor


class StubEngine:

    def __init__(self) -> None:
        self.dispose_calls = 0

    async def dispose(self) -> None:
        self.dispose_calls += 1


class StubPasswordHashExecutor:

    def __init__(self) -> None:
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class StubInjector:

    def __init__(self, engine: StubEngine, config=None) -> None:
        self._engine = engine
        self._password_hash_executor = StubPasswordHashExecutor()
        self._config = config or SimpleNamespace(
            ENVIRONMENT="local",
            LOG_LEVEL="INFO",
        )
        self._auth_settings = AuthSettings(_env_file=None)
        self.requested_interfaces = []

    def get(self, interface):
        self.requested_interfaces.append(interface)
        if interface is AsyncEngine:
            return self._engine
        if interface is PasswordHashExecutor:
            return self._password_hash_executor
        if interface is Config:
            return self._config
        if interface is AuthSettings:
            return self._auth_settings
        raise AssertionError(f"Unexpected interface: {interface}")


def _app_with_config(
        monkeypatch,
        config) -> tuple[StubEngine, StubPasswordHashExecutor, TestClient]:
    engine = StubEngine()
    injector = StubInjector(engine, config)
    monkeypatch.setattr(create_app_module, "build_container", lambda: injector)
    app = create_app_module.create_app()
    return engine, injector._password_hash_executor, TestClient(app)


@pytest.mark.parametrize("environment", ["production", "prod", "Production"])
def test_production_like_environments_disable_docs(monkeypatch, environment):
    engine, password_hash_executor, client = _app_with_config(
        monkeypatch,
        SimpleNamespace(ENVIRONMENT=environment, LOG_LEVEL="INFO"),
    )

    with client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404

    assert engine.dispose_calls == 1
    assert password_hash_executor.shutdown_calls == 1


def test_unset_environment_disables_docs_by_default(monkeypatch):
    engine, password_hash_executor, client = _app_with_config(
        monkeypatch,
        SimpleNamespace(ENVIRONMENT=Config(_env_file=None).ENVIRONMENT,
                        LOG_LEVEL="INFO"),
    )

    with client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404

    assert engine.dispose_calls == 1
    assert password_hash_executor.shutdown_calls == 1


def test_local_environment_enables_docs(monkeypatch):
    engine, password_hash_executor, client = _app_with_config(
        monkeypatch,
        SimpleNamespace(ENVIRONMENT="local", LOG_LEVEL="INFO"),
    )

    with client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200

    assert engine.dispose_calls == 1
    assert password_hash_executor.shutdown_calls == 1


def test_create_app_applies_log_level_from_config(monkeypatch):
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("app").setLevel(logging.NOTSET)
    engine, password_hash_executor, client = _app_with_config(
        monkeypatch,
        SimpleNamespace(ENVIRONMENT="local", LOG_LEVEL="DEBUG"),
    )

    with client:
        pass

    assert logging.getLogger().getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("app").getEffectiveLevel() == logging.DEBUG
    assert engine.dispose_calls == 1
    assert password_hash_executor.shutdown_calls == 1


def test_create_app_resolves_auth_settings_during_startup(monkeypatch):
    engine = StubEngine()
    injector = StubInjector(engine)
    monkeypatch.setattr(create_app_module, "build_container", lambda: injector)

    create_app_module.create_app()

    assert AuthSettings in injector.requested_interfaces


def test_create_app_fails_fast_when_auth_settings_are_invalid(monkeypatch):

    class InvalidAuthSettingsInjector(StubInjector):

        def get(self, interface):
            if interface is AuthSettings:
                raise ValueError("invalid auth settings")
            return super().get(interface)

    injector = InvalidAuthSettingsInjector(StubEngine())
    monkeypatch.setattr(create_app_module, "build_container", lambda: injector)

    with pytest.raises(ValueError, match="invalid auth settings"):
        create_app_module.create_app()


def test_create_app_falls_back_for_invalid_log_level(monkeypatch, caplog):
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger("app").setLevel(logging.NOTSET)
    engine, password_hash_executor, client = _app_with_config(
        monkeypatch,
        SimpleNamespace(ENVIRONMENT="local", LOG_LEVEL="NOPE"),
    )

    with caplog.at_level(logging.WARNING):
        with client:
            pass

    assert logging.getLogger().getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("app").getEffectiveLevel() == logging.INFO
    assert "Invalid LOG_LEVEL=NOPE; falling back to INFO" in caplog.text
    assert engine.dispose_calls == 1
    assert password_hash_executor.shutdown_calls == 1


def test_lifespan_disposes_async_engine_on_shutdown(monkeypatch):
    engine, password_hash_executor, client = _app_with_config(
        monkeypatch,
        SimpleNamespace(ENVIRONMENT="local", LOG_LEVEL="INFO"),
    )

    with client:
        pass

    assert engine.dispose_calls == 1
    assert password_hash_executor.shutdown_calls == 1


def test_stub_injector_returns_async_engine():
    engine = StubEngine()
    injector = StubInjector(engine)

    assert injector.get(AsyncEngine) is engine
