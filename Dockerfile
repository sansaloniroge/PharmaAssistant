# Dockerfile
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Dependencias del sistema mínimas
RUN apt-get update && apt-get install -y build-essential curl && rm -rf /var/lib/apt/lists/*

# Instala Poetry
RUN pip install poetry==1.8.3

# Copia definición del proyecto y resuelve dependencias
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --only main

# Copia código
COPY app/ ./app/
COPY service/ ./service/
COPY data/ ./data/
COPY profiles/ ./profiles/
COPY storage/ ./storage/

# Exponer puerto
EXPOSE 8080

# Gunicorn con workers Uvicorn
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "service.main:app", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "120"]
