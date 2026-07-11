from urllib.parse import quote

from requests import RequestException, session
from loguru import logger

from src.settings.config import settings
from src.settings.constants import (
    VK_ICON_PNG,
    VK_ME,
    REQUEST_TIMEOUT,
)


class Bark():
    _url: str = "https://api.day.app"

    def __init__(self, token: str) -> None:
        self._token = token
        self._session = session()

    def notification(
        self,
        title: str,
        body: str,
        *,
        icon: str = VK_ICON_PNG,
        url: str = VK_ME,
    ) -> dict | None:
        request_url = f"{self._url}/{self._token}/{quote(title, safe='')}/{quote(body, safe='')}"
        try:
            response = self._session.get(
                request_url,
                params={"icon": icon, "url": url},
                timeout=REQUEST_TIMEOUT,
            )
        except RequestException as error:
            logger.error(f"Не удалось отправить уведомление в Bark: {error}")
            return
        if response.status_code == 200:
            try:
                response_json: dict = response.json()
            except ValueError:
                logger.warning(f"Bark вернул некорректный ответ: {response.text}")
                return
            if response_json.get("code") == 200:
                return response_json
        logger.warning(f"Bark вернул ошибку: {response.text}")
        return


if __name__ == "__main__":
    bark = Bark(token=settings.BARK_TOKEN)
    bark.notification("Test", "Message")
