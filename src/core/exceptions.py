class VKAPIError(Exception):
    """Ошибка при обращении к VK API."""


class VKAuthError(VKAPIError):
    """Токен VK недействителен: переподключение бессмысленно."""
