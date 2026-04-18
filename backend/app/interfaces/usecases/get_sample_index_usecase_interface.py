from abc import ABCMeta, abstractmethod
from typing import Optional, Tuple

from app.models.status import Status


class GetSampleIndexUsecaseInterface(metaclass=ABCMeta):

    @abstractmethod
    def handle(self, message: str) -> Optional[Status]:
        raise NotImplementedError
