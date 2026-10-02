FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY prompts ./prompts
COPY services ./services
COPY data ./data

RUN uv sync --frozen --no-editable

EXPOSE 8000 8001

CMD ["python", "-m", "emporium.ingest"]
