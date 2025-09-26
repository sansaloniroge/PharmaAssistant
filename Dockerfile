# syntax=docker/dockerfile:1

########################
# Stage 1: builder
########################
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Metadatos que Poetry usa
COPY pyproject.toml ./
COPY README.md ./

# Mantener la estructura src/ (poetry: from="src")
COPY src ./src

# Construir wheel del proyecto
RUN python -m pip install --upgrade pip wheel setuptools \
 && pip wheel --no-deps --no-cache-dir -w /dist .

########################
# Stage 2: runtime
########################
FROM python:3.11-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar el wheel construido
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

# (Opcional) si necesitas ficheros no empaquetados:
# COPY service/tenants.yaml /app/service/tenants.yaml

EXPOSE 8000
# CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8000"]
