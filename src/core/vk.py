import time

from requests import RequestException, session
from loguru import logger

from src.core.bark import Bark
from src.core.exceptions import VKAPIError, VKAuthError
from src.settings.config import settings
from src.settings.constants import (
    VK_ICON_PNG,
    VK_ME,
    NEW_MESSAGE_EVENT,
    OUTBOX_FLAG,
    AUTH_ERROR_CODES,
    REQUEST_TIMEOUT,
    LONG_POLL_WAIT,
    RECONNECT_DELAY,
    MAX_RECONNECT_DELAY,
    STABLE_CONNECTION_TIME,
)


class VKListener():
    _api_url: str = "https://api.vk.com/method"
    _api_version: str = "5.199"

    def __init__(self, token: str, bark: Bark) -> None:
        self._token = token
        self._bark = bark
        self._session = session()
        self._senders_cache: dict[int, tuple[str, str, str]] = {}

    def _method(self, method: str, **params) -> dict | list:
        params |= {"access_token": self._token, "v": self._api_version}
        try:
            response = self._session.get(
                f"{self._api_url}/{method}",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            response_json: dict = response.json()
        except (RequestException, ValueError) as error:
            raise VKAPIError(f"Не удалось выполнить запрос {method}: {error}") from error
        if "error" in response_json:
            error_data: dict = response_json["error"]
            error_code = error_data.get("error_code")
            message = f"VK API {method} [{error_code}]: {error_data.get('error_msg')}"
            if error_code in AUTH_ERROR_CODES:
                raise VKAuthError(message)
            raise VKAPIError(message)
        return response_json["response"]

    def _get_long_poll_server(self) -> dict:
        return self._method("messages.getLongPollServer", lp_version=3)

    def _get_sender(self, from_id: int) -> tuple[str, str, str]:
        if from_id in self._senders_cache:
            return self._senders_cache[from_id]
        name, icon = str(from_id), VK_ICON_PNG
        screen_name = f"id{from_id}" if from_id > 0 else f"club{-from_id}"
        try:
            if from_id > 0:
                users: list = self._method(
                    "users.get",
                    user_ids=from_id,
                    fields="photo_100,screen_name",
                )
                if users:
                    user: dict = users[0]
                    name = f"{user['first_name']} {user['last_name']}"
                    icon = user.get("photo_100") or VK_ICON_PNG
                    screen_name = user.get("screen_name") or screen_name
            else:
                response = self._method("groups.getById", group_id=-from_id)
                groups = response.get("groups", response) if isinstance(response, dict) else response
                if groups:
                    group: dict = groups[0]
                    name = group["name"]
                    icon = group.get("photo_100") or VK_ICON_PNG
                    screen_name = group.get("screen_name") or screen_name
        except VKAuthError:
            raise
        except VKAPIError as error:
            logger.warning(f"Не удалось получить данные отправителя {from_id}: {error}")
            return name, icon, f"{VK_ME}{screen_name}"
        sender = (name, icon, f"{VK_ME}{screen_name}")
        self._senders_cache[from_id] = sender
        return sender

    def _handle_update(self, update: list) -> None:
        if not update or update[0] != NEW_MESSAGE_EVENT:
            return
        message_id, flags = update[1], update[2]
        if flags & OUTBOX_FLAG:
            return
        response: dict = self._method("messages.getById", message_ids=message_id)
        items: list = response.get("items", [])
        if not items:
            return
        message: dict = items[0]
        name, icon, url = self._get_sender(message["from_id"])
        body = message.get("text") or "Вложение"
        self._bark.notification(title=name, body=body, icon=icon, url=url)
        logger.info(f"Новое сообщение от {name}: {body}")

    def _poll(self) -> None:
        server = self._get_long_poll_server()
        logger.info("Слушатель сообщений VK запущен")
        while True:
            response = self._session.get(
                f"https://{server['server']}",
                params={
                    "act": "a_check",
                    "key": server["key"],
                    "ts": server["ts"],
                    "wait": LONG_POLL_WAIT,
                    "mode": 2,
                    "version": 3,
                },
                timeout=LONG_POLL_WAIT + 10,
            )
            response_json: dict = response.json()
            failed = response_json.get("failed")
            if failed == 1:
                server["ts"] = response_json["ts"]
                continue
            if failed in (2, 3):
                logger.info("Ключ Long Poll устарел, получаю новый")
                server = self._get_long_poll_server()
                continue
            if failed:
                raise VKAPIError(f"Long Poll вернул ошибку: failed={failed}")
            server["ts"] = response_json["ts"]
            for update in response_json.get("updates", []):
                try:
                    self._handle_update(update)
                except VKAuthError:
                    raise
                except Exception:
                    logger.exception(f"Не удалось обработать событие: {update}")

    def listen(self) -> None:
        delay = RECONNECT_DELAY
        while True:
            started = time.monotonic()
            try:
                self._poll()
            except VKAuthError:
                raise
            except (VKAPIError, RequestException, ValueError) as error:
                if time.monotonic() - started > STABLE_CONNECTION_TIME:
                    delay = RECONNECT_DELAY
                logger.error(f"Соединение с VK потеряно: {error}")
                logger.info(f"Переподключение через {delay} с.")
                time.sleep(delay)
                delay = min(delay * 2, MAX_RECONNECT_DELAY)


if __name__ == "__main__":
    bark = Bark(token=settings.BARK_TOKEN)
    listener = VKListener(token=settings.VK_TOKEN, bark=bark)
    listener.listen()
