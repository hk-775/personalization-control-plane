FROM python:3.12-alpine3.24@sha256:d09d15e60962ca365d1cd544a48773bac9d33f2fb1b00f2aa0deec78ade7dc31

COPY --from=ghcr.io/astral-sh/uv:0.10.7@sha256:edd1fd89f3e5b005814cc8f777610445d7b7e3ed05361f9ddfae67bebfe8456a /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PCP_HOST=0.0.0.0 \
    PCP_PORT=8102 \
    PCP_DB_PATH=/app/data/personalization-control-plane.db \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

RUN apk upgrade --no-cache \
    && addgroup -S -g 10001 pcp \
    && adduser -S -D -H -u 10001 -G pcp -h /app -s /sbin/nologin pcp

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable \
    && mkdir -p /app/data \
    && chown -R pcp:pcp /app

USER pcp

EXPOSE 8102

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8102/api/v1/health', timeout=2)"]

CMD ["uv", "run", "--locked", "--no-dev", "--no-sync", "pcp-demo", "--host", "0.0.0.0", "--port", "8102", "--db", "/app/data/personalization-control-plane.db"]
