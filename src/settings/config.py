import sys

from loguru import logger
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    VK_TOKEN: str
    BARK_TOKEN: str
    BARK_URL: str = "https://api.day.app"

    model_config = SettingsConfigDict(
        env_file=".env",
    )


try:
    settings = Settings()
except ValidationError as error:
    logger.critical(
        "Некорректная конфигурация: заполните .env (см. sample.env) "
        f"или передайте переменные окружения.\n{error}",
    )
    sys.exit(1)
