# VK iOS Notifications

Пересылает новые сообщения ВКонтакте в push-уведомления на iOS через [Bark](https://github.com/Finb/Bark).
В уведомлении: имя отправителя (заголовок), текст сообщения и его аватарка.

## Как это работает

Сервис слушает события через [VK Long Poll API](https://dev.vk.com/ru/api/user-long-poll/getting-started).
При новом входящем сообщении он запрашивает данные отправителя (имя и фото — для бесед
определяется настоящий автор, а не чат) и отправляет уведомление на устройство через Bark.

- Исходящие сообщения игнорируются.
- Диалоги с отключёнными уведомлениями пропускаются.
- Данные отправителей кэшируются, чтобы не дёргать VK API на каждое сообщение.
- При сетевых сбоях и ошибках VK API сервис автоматически переподключается
  с экспоненциальной задержкой (5 с → 10 с → … → максимум 5 минут).
- При невалидном токене (`VK_TOKEN`) сервис завершается с понятной ошибкой —
  бесконечных попыток с мёртвым токеном не будет.

## Требования

- Токен VK (`vk1.a.…`) с доступом к сообщениям (`messages`).
- Ключ устройства Bark: установите [приложение Bark](https://apps.apple.com/app/bark-custom-notifications/id1403753865)
  на iPhone — ключ показан на главном экране приложения.

## Конфигурация

Создайте файл `.env` в корне проекта (пример — в [sample.env](sample.env)):

```env
VK_TOKEN=vk1.a.xxxxxxxx
BARK_TOKEN=xxxxxxxx
```

Вместо `.env` можно передать те же переменные окружения напрямую.

## Запуск локально

Требуется Python 3.13+ и [Poetry](https://python-poetry.org/):

```bash
poetry install --no-root
poetry run python -m src.main
```

## Запуск в Docker

```bash
docker build -t vk-ios-notifications .
docker run -d --name vk-ios-notifications --restart unless-stopped --env-file .env vk-ios-notifications
```

Файл `.env` не копируется в образ (см. [.dockerignore](.dockerignore)) —
токены передаются только через `--env-file` или `-e`.

Готовый образ собирается автоматически при пуше в `main`/`develop`
(см. [build_app.yml](.github/workflows/build_app.yml)) и публикуется в GitHub Container Registry:

```bash
docker run -d --restart unless-stopped --env-file .env ghcr.io/tarodictrl/vk-ios-notifications:main
```

## Структура проекта

```
src/
├── main.py              # точка входа
├── core/
│   ├── vk.py            # слушатель Long Poll VK, реконнект
│   ├── exceptions.py    # ошибки
│   └── bark.py          # отправка push-уведомлений через Bark
└── settings/
    ├── config.py        # настройки из .env (pydantic-settings)
    └── constants.py     # константы (иконка VK по умолчанию)
```
