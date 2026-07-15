import sys

from loguru import logger

from src.core.bark import Bark
from src.core.vk import VKAuthError, VKListener
from src.settings.config import settings


def main() -> None:
    bark = Bark(token=settings.BARK_TOKEN, bark_url=settings.BARK_URL)
    listener = VKListener(token=settings.VK_TOKEN, bark=bark)
    try:
        listener.listen()
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем")
    except VKAuthError as error:
        logger.critical(f"{error}. Проверьте VK_TOKEN")
        sys.exit(1)


if __name__ == "__main__":
    main()
