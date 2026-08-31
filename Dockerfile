# syntax=docker/dockerfile:1

########################
# Stage 1: builder
########################
FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Herramientas mínimas para compilar wheels binarios (numpy/pandas) si hiciera falta
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# Archivos de proyecto para Poetry
COPY pyproject.toml ./
COPY poetry.lock ./
COPY README.md ./

# Código (layout src/)
COPY src ./src

# --- Exportar dependencias desde Poetry a requirements.txt ---
# Sin instalar Poetry globalmente: usamos el backend para exportar (más portable),
# pero la forma más simple es instalar poetry solo en build:
RUN pip install --no-cache-dir "poetry>=1.6,<2"
RUN poetry export -f requirements.txt --without-hashes -o /tmp/requirements.txt

# --- Construir wheel del proyecto (como ya hacías) ---
RUN python -m pip install --upgrade pip wheel setuptools \
 && pip wheel --no-deps --no-cache-dir -w /dist .

########################
# Stage 2: runtime
########################
FROM python:3.11-slim AS runtime

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Dependencias runtime necesarias para numpy/pandas + certificados
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Instalar dependencias de Poetry (exportadas)
COPY --from=builder /tmp/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 2) Instalar el wheel de tu paquete (sin deps)
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl /tmp/requirements.txt

# 3) Copiar archivos que NO van en el wheel pero tu app necesita en runtime
#    - config.py en la raíz del proyecto
#    - data/ con prompts y patrones
COPY config.py /app/config.py
COPY data /app/data
COPY profiles /app/profiles

# (Opcional) Si en local quieres imagen "all in one”, podrías copiar índices:
# COPY storage/indexes /app/storage/indexes
# En producción mejor usa PVC o el CronJob de tu chart para generarlos.

# Usuario no-root por seguridad
RUN useradd -m appuser
USER appuser

# Exponemos el puerto que usa Helm (8080)
EXPOSE 8080

# Asegura que el import "service.main:app" funciona porque el paquete está instalado
# Lanza uvicorn en 0.0.0.0:8080 para que el Service haga targetPort:8080
CMD ["python", "-m", "uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8080"]
