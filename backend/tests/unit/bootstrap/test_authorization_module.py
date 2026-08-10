from pathlib import Path

from fastapi import FastAPI
from injector import Injector

from app.bootstrap.modules import AuthModule, CoreModule, DatabaseModule
from app.bootstrap.route import setup_routes
from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.usecases.authorization_usecase_interface import AuthorizationUsecaseInterface
from app.services.authorization_repository import AuthorizationRepository
from app.usecases.authorization_usecase import AuthorizationUsecase


class BinderStub:

    def __init__(self) -> None:
        self.bindings = {}

    def bind(self, interface, to, scope) -> None:
        self.bindings[interface] = (to, scope)


def test_auth_module_binds_authorization_repository_and_usecase() -> None:
    binder = BinderStub()

    AuthModule().configure(binder)

    assert binder.bindings[AuthorizationRepositoryInterface][0] is AuthorizationRepository
    assert binder.bindings[AuthorizationUsecaseInterface][0] is AuthorizationUsecase


def test_auth_module_resolves_authorization_usecase_from_container() -> None:
    injector = Injector([CoreModule(), DatabaseModule(), AuthModule()])

    assert isinstance(
        injector.get(AuthorizationRepositoryInterface),
        AuthorizationRepository,
    )
    assert isinstance(injector.get(AuthorizationUsecaseInterface), AuthorizationUsecase)


def test_setup_routes_includes_authorization_admin_routes(tmp_path: Path) -> None:
    app = setup_routes(FastAPI(), static_directory=tmp_path)

    paths = set(app.openapi()["paths"])
    assert "/api/admin/roles" in paths
    assert "/api/admin/users/{user_id}/roles" in paths
