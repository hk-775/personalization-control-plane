FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PCP_HOST=0.0.0.0 \
    PCP_PORT=8102 \
    PCP_DB_PATH=/app/data/personalization-control-plane.db

WORKDIR /app

RUN groupadd --system pcp \
    && useradd --system --gid pcp --home-dir /app --shell /usr/sbin/nologin pcp

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN python -m pip install --no-cache-dir . \
    && mkdir -p /app/data \
    && chown -R pcp:pcp /app

USER pcp

EXPOSE 8102

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8102/api/v1/health', timeout=2)"]

CMD ["pcp-demo", "--host", "0.0.0.0", "--port", "8102", "--db", "/app/data/personalization-control-plane.db"]
