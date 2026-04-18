import os
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Config(BaseSettings):
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    def __init__(self, environment: Optional[str] = None, **kwargs):
        if environment is not None:
            _env = environment
        else:
            _env = os.getenv("ENVIRONMENT", "local")

        super().__init__(**kwargs)


config = Config()
