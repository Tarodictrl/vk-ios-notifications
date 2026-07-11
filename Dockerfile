FROM python:3.13-slim

ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir poetry==1.8.2

WORKDIR /code

COPY poetry.lock pyproject.toml ./
RUN poetry install --only main --no-root --no-interaction --no-ansi \
    && rm -rf $POETRY_CACHE_DIR

COPY src ./src

CMD ["python", "-m", "src.main"]
