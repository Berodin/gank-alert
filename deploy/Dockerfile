FROM python:3.12-slim AS base

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/shared/pyproject.toml packages/shared/pyproject.toml
COPY apps/ingester/pyproject.toml apps/ingester/pyproject.toml
COPY apps/bot/pyproject.toml apps/bot/pyproject.toml
COPY apps/api/pyproject.toml apps/api/pyproject.toml

COPY packages/shared packages/shared
COPY apps/ingester apps/ingester
COPY apps/bot apps/bot
COPY apps/api apps/api

# gank-client (PySide6/GUI) is deliberately excluded -- it's distributed
# to users as a standalone binary, not run server-side.
RUN uv sync --frozen --no-dev \
    --package gank-shared --package gank-ingester --package gank-bot --package gank-api

ARG APP
ENV APP=${APP}
ENTRYPOINT ["sh", "-c", "uv run --package ${APP} ${APP}"]
