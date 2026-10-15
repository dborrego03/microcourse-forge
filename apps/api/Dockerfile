FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    FORGE_MEDIA_DIR=/data/media \
    FORGE_LLM_PROVIDER=anthropic

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY forge ./forge
COPY migrations ./migrations
COPY alembic.ini ./

# Bake the embedding and re-ranking models in, so a cold start doesn't download ~250 MB.
RUN python -c "from forge import embeddings as e; e.model(); e.reranker(); e.tokenizer()"

RUN useradd --create-home app && mkdir -p /data/media && chown -R app /app /data
USER app

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA
EXPOSE 8000
CMD ["uvicorn", "forge.api:app", "--host", "0.0.0.0", "--port", "8000"]
