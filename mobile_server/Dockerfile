# Build from the repository root:
# docker build -f mobile_server/Dockerfile -t format-factory-service .
ARG BASE_IMAGE=python:3.13-slim
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer fonts-noto-cjk fonts-liberation libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY mobile_server/requirements.txt /app/mobile_server/requirements.txt
RUN pip install --no-cache-dir -r mobile_server/requirements.txt
COPY factory /app/factory
COPY vendor /app/vendor
COPY resources/formula /app/resources/formula
COPY mobile_server /app/mobile_server
RUN useradd --create-home --uid 10001 converter && mkdir /jobs && chown converter:converter /jobs \
    && find /app -type d -name __pycache__ -prune -exec rm -rf {} +
USER converter
ENV FACTORY_STORAGE=/jobs PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
# Loopback only by default. Override only for an explicitly configured LAN test
# or reverse proxy; use a single ASGI worker (job ownership is process-local).
CMD ["python", "-m", "uvicorn", "mobile_server.app:app", "--host", "127.0.0.1", "--port", "8765", "--workers", "1", "--no-access-log"]
