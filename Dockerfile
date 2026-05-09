FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DB_PATH=/data/privy_manager.db

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "requests[socks]"

COPY . .

RUN mkdir -p /data

EXPOSE 7894 7895

ENTRYPOINT ["/usr/bin/tini", "--"]

COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]