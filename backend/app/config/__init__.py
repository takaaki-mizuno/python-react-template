from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "production"
    LOG_LEVEL: str = "INFO"


def get_config() -> Config:
    return Config()
