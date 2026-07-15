import time

from requests import RequestException, session
from loguru import logger

from src.core.bark import Bark
from src.core.exceptions import VKAPIError, VKAuthError
from src.core.enums import (
    VKPoolFailedStatuses,
    VKPollEvents,
    VKPollFlags,
)
from src.settings.config import settings
from src.settings.constants import (
    VK_ICON_PNG,
    VK_ME,
    VK_IM,
    CHAT_ID_OFFSET,
    AUTH_ERROR_CODES,
    ATTACHMENT_NAMES,
    GEO_NAME,
    FORWARDED_NAME,
    REPLY_NAME,
    UNKNOWN_ATTACHMENT_NAME,
    READ_CHECK_DELAY,
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

    def _get_conversation(self, peer_id: int) -> dict:
        try:
            response: dict = self._method(
                "messages.getConversationsById",
                peer_ids=peer_id,
            )
        except VKAuthError:
            raise
        except VKAPIError as error:
            logger.warning(f"Не удалось получить данные диалога {peer_id}: {error}")
            return {}
        items: list[dict] = response.get("items", [])
        return items[0] if items else {}

    @staticmethod
    def _is_muted(conversation: dict) -> bool:
        push_settings: dict = conversation.get("push_settings") or {}
        if push_settings.get("disabled_forever"):
            return True
        disabled_until = push_settings.get("disabled_until") or 0
        return disabled_until == -1 or disabled_until > time.time()

    def _is_read(self, peer_id: int, message_id: int) -> bool:
        in_read = self._get_conversation(peer_id).get("in_read") or 0
        return in_read >= message_id

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

    def _describe_message(self, message: dict[dict, ...]) -> str:
        names: list[str] = []
        for attachment in message.get("attachments") or []:
            attachment_type = attachment.get("type") or ""
            name = ATTACHMENT_NAMES.get(attachment_type, UNKNOWN_ATTACHMENT_NAME)
            if name not in names:
                names.append(name)
        if message.get("fwd_messages"):
            names.append(FORWARDED_NAME)
        elif message.get("reply_message"):
            names.append(REPLY_NAME)
        if message.get("geo"):
            names.append(GEO_NAME)
        return ", ".join(names) or UNKNOWN_ATTACHMENT_NAME

    def _handle_update(self, update: list) -> None:
        if not update or update[0] != VKPollEvents.NEW_MESSAGE_EVENT:
            return
        message_id, flags = update[1], update[2]
        if flags & VKPollFlags.OUTBOX:
            return
        response: dict = self._method("messages.getById", message_ids=message_id)
        items: list = response.get("items", [])
        if not items:
            return
        message: dict = items[0]
        peer_id = message.get("peer_id") or 0
        conversation = self._get_conversation(peer_id) if peer_id else {}
        if self._is_muted(conversation):
            logger.info(f"Уведомления в диалоге {peer_id} отключены, пропускаю сообщение")
            return
        time.sleep(READ_CHECK_DELAY)
        if peer_id and self._is_read(peer_id, message_id):
            logger.info(f"Сообщение {message_id} уже прочитано, пропускаю")
            return
        name, icon, url = self._get_sender(message["from_id"])
        if peer_id >= CHAT_ID_OFFSET:
            chat_settings: dict = conversation.get("chat_settings") or {}
            chat_photo: dict = chat_settings.get("photo") or {}
            icon = chat_photo.get("photo_100") or icon
            url = f"{VK_IM}c{peer_id - CHAT_ID_OFFSET}"
        body = message.get("text") or self._describe_message(message)
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
            if failed == VKPoolFailedStatuses.EVENT_EXPIRED:
                server["ts"] = response_json["ts"]
                continue
            if failed in (VKPoolFailedStatuses.KEY_EXPIRED, VKPoolFailedStatuses.USER_DATA_EXPIRED):
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
    bark = Bark(token=settings.BARK_TOKEN, bark_url=settings.BARK_URL)
    listener = VKListener(token=settings.VK_TOKEN, bark=bark)
    listener.listen()
