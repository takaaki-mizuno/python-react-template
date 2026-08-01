from logging import Logger
from typing import Optional

from app.config import Config
from app.interfaces.usecases.get_sample_index_usecase_interface import \
    GetSampleIndexUsecaseInterface
from app.models.status import Status


class GetSampleIndexUsecase(GetSampleIndexUsecaseInterface):

    def __init__(self, config: Config, logger: Logger):
        self._config = config
        self._logger = logger

    def handle(self, message: str) -> Optional[Status]:
        return Status(success=True, message=message)
