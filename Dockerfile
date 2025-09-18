# ---------- Stage 1: builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Paquetes base (libgomp1 ayuda con numpy/numba; build tools mínimos)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Instala Poetry sólo en el builder
RUN pip install --no-cache-dir "poetry==1.8.3"

WORKDIR /src

# Copiamos manifest para aprovechar cache de deps
COPY pyproject.toml poetry.lock* ./

# Exportamos requirements sin hashes y los instalamos en un venv
ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

RUN poetry export -f requirements.txt --without-hashes -o /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt

# Ahora instalamos el propio paquete (sin deps)
# Necesitamos las fuentes para que pip empaquete 'app' y 'service'
COPY app ./app
COPY service ./service
COPY scripts ./scripts
RUN pip install --no-cache-dir --no-deps .

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

# Sólo runtime libs necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Usuario no-root
RUN useradd -u 10001 -ms /bin/bash appuser

WORKDIR /app

# Copiamos el venv del builder
COPY --from=builder /opt/venv /opt/venv

# Copiamos lo mínimo necesario en runtime (datos/profiles opcionales; en dev puedes montarlos por volumen)
COPY --chown=10001:10001 data ./data
COPY --chown=10001:10001 profiles ./profiles
# Creamos la carpeta storage (si no se monta volumen)
RUN mkdir -p /app/storage && chown -R 10001:10001 /app

USER appuser

EXPOSE 8080

# Variables recomendadas (ajústalas en compose/entorno)
ENV LOG_LEVEL=INFO \
    ALLOWED_ORIGINS="" \
    PRELOAD_TENANTS=""

# Comando por defecto
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8080"]
