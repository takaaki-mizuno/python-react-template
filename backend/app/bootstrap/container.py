from logging import Logger, getLogger

from injector import Binder, Injector, InstanceProvider, singleton

from app.config import Config, config
from app.interfaces.usecases.get_sample_index_usecase_interface import \
    GetSampleIndexUsecaseInterface
from app.usecases.get_sample_index_usecase import GetSampleIndexUsecase


def build_container() -> Injector:
    return Injector(modules=[configure])


def configure(binder: Binder):
    binder.bind(Config, to=config, scope=singleton)

    logger = getLogger(__name__)
    binder.bind(Logger, to=logger, scope=singleton)

    # Usecases
    get_sample_index_usecase = GetSampleIndexUsecase(
        config=config,
        logger=logger,
    )
    binder.bind(GetSampleIndexUsecaseInterface, to=get_sample_index_usecase)
