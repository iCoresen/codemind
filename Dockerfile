FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copy dependency manifests first to maximize Docker build cache reuse.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source.
COPY app ./app
COPY main.py ./main.py
COPY README.md ./README.md

RUN mkdir -p /app/logs /app/data/chroma

ENV PATH="/app/.venv/bin:${PATH}" \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8080

EXPOSE 8080

CMD ["python", "-m", "app.main"]
