import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface


class AsyncEngineStub:

    def __init__(self, dispose_error: Exception | None = None) -> None:
        self.dispose_calls = 0
        self._dispose_error = dispose_error

    async def dispose(self) -> None:
        self.dispose_calls += 1
        if self._dispose_error is not None:
            raise self._dispose_error


class InjectorStub:

    def __init__(self) -> None:
        self.engine = AsyncEngineStub()

    def get(self, interface):
        if interface is AsyncEngine:
            return self.engine
        if interface is AuthRepositoryInterface:
            return object()
        raise KeyError(interface)


@pytest.mark.asyncio
async def test_run_with_container_returns_operation_result_and_disposes_engine(monkeypatch):
    from app.bootstrap import cli

    injector = InjectorStub()
    monkeypatch.setattr(cli, "build_container", lambda: injector)

    async def operation(container):
        assert container.get(AuthRepositoryInterface) is not None
        return "ok"

    assert await cli.run_with_container(operation) == "ok"
    assert injector.engine.dispose_calls == 1


@pytest.mark.asyncio
async def test_run_with_container_logs_dispose_failure_without_masking_result(
    monkeypatch,
    caplog,
):
    from app.bootstrap import cli

    injector = InjectorStub()
    injector.engine = AsyncEngineStub(dispose_error=RuntimeError("dispose failed"))
    monkeypatch.setattr(cli, "build_container", lambda: injector)

    async def operation(_container):
        return "ok"

    assert await cli.run_with_container(operation) == "ok"
    assert injector.engine.dispose_calls == 1
    assert "Failed to dispose CLI database engine" in caplog.text


@pytest.mark.asyncio
async def test_run_with_container_disposes_engine_when_operation_raises(monkeypatch):
    from app.bootstrap import cli

    injector = InjectorStub()
    monkeypatch.setattr(cli, "build_container", lambda: injector)

    async def operation(_container):
        raise RuntimeError("operation failed")

    with pytest.raises(RuntimeError, match="operation failed"):
        await cli.run_with_container(operation)

    assert injector.engine.dispose_calls == 1
