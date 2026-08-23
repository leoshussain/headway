FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Keep Python output visible in Docker logs and put the virtual environment
# outside /app so the development bind mount cannot hide it.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src

WORKDIR /app

# Dependency files are copied first so Docker can reuse this slow layer until
# either file changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY src ./src

# Install the project after copying its source. Keeping this separate from the
# dependency layer means source edits do not force every dependency to reinstall.
RUN uv sync --frozen

CMD ["headway-collect"]
