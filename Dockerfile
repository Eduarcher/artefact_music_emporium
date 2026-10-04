FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first so source changes do not invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

COPY src ./src
COPY tests ./tests
COPY prompts ./prompts
COPY services ./services
COPY data ./data
COPY .chainlit ./.chainlit
COPY public ./public
COPY chainlit.md ./chainlit.md

# Install the project itself against the already-populated environment.
RUN uv sync --frozen --no-editable

EXPOSE 8000 8001

CMD ["python", "-m", "emporium.ingest"]
