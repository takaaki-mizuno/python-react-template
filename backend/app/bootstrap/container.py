from injector import Injector

from app.bootstrap.modules import AuthModule, CoreModule, DatabaseModule, SampleModule


def build_container() -> Injector:
    return Injector(modules=[
        CoreModule(),
        DatabaseModule(),
        AuthModule(),
        SampleModule(),
    ])
