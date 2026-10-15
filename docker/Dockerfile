# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

FROM base AS development
RUN uv sync --locked --no-install-project
COPY . .
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS production
COPY . .
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]
