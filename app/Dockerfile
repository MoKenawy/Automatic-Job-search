# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv, copied from the official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first for layer caching
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Application source, migrations and alembic config
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# No default command: docker-compose supplies one per service (web, scheduler,
# migrate). Running bare defaults to the CLI help.
ENTRYPOINT ["uv", "run", "--no-sync"]
CMD ["python", "-m", "app", "--help"]
