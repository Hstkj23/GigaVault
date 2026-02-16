FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY pyproject.toml .
COPY spawn_agent/ spawn_agent/
COPY README.md .
COPY LICENSE .

RUN pip install --no-cache-dir --prefix=/install .

# --- Runtime ---
FROM python:3.12-slim

LABEL maintainer="SpawnAgent Contributors"
LABEL description="Real-time on-chain intelligence agent"
LABEL org.opencontainers.image.source="https://github.com/Hstkj23/GigaVault"

RUN groupadd -r spawn && useradd -r -g spawn -d /app spawn

WORKDIR /app

COPY --from=builder /install /usr/local

COPY config/spawn_agent.example.yml /app/config/spawn_agent.yml

USER spawn

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import spawn_agent; print('ok')" || exit 1

ENTRYPOINT ["spawn-agent"]
CMD ["serve", "--config", "/app/config/spawn_agent.yml"]
