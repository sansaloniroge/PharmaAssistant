# Observabilidad — PharmaAssistant

Guía práctica para **logs**, **métricas** y (opcional) **trazas**. Incluye comandos de verificación, consultas Prometheus y un compose de ejemplo con **Prometheus + Grafana** para local.

---

## 1) Logs

### Formato y emisión
- **JSON a stdout** mediante `service/logging_setup.py` y el middleware en `service/main.py`.
- Cada petición HTTP emite: método, ruta, **status**, **latencia ms** y **tenant** (`client_id` o `x-tenant-id`).

**Ejemplo (formato lógico):**
```json
{"ts": 1726640000, "level":"INFO","logger":"app",
 "msg":"GET /answer 200 35.71ms tenant=client_1"}
```

### Verificación
```bash
# Local (uvicorn)
poetry run uvicorn service.main:app --port 8080 --reload
curl -s "http://localhost:8080/greet?client_id=client_1" -H "x-api-key: secret_key_client_1" >/dev/null
# Observa la línea JSON en consola

# Docker Compose
docker compose logs -f pharmaassistant
```

### Buenas prácticas
- No registrar payloads con datos sensibles.
- Mantener `LOG_LEVEL` en `INFO` en prod; usar `DEBUG` sólo puntualmente.
- Alinear handlers de `uvicorn` con el mismo formatter JSON (se hace en `setup_logging`).

---

## 2) Métricas (Prometheus)

### Exposición
- Endpoint: `GET /metrics` (formato Prometheus exposition).
- Registro en `service/metrics.py` (llamado desde `service/main.py`: `register_metrics(app)`).

### Métricas clave (incluidas por defecto)
- **HTTP**:
  - `http_requests_total{method,path,status}`
  - `http_request_duration_seconds_bucket/sum/count{method,path}`
- **Negocio**:
  - `recommendations_total{client_id}` (se incrementa en `/answer`)

### Verificación
```bash
curl -s http://localhost:8080/metrics | head -n 20
```

### Consultas Prometheus útiles
- **QPS** por ruta:
  ```promql
  sum by (path) (rate(http_requests_total[5m]))
  ```
- **Error rate (5xx)** global:
  ```promql
  sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
  ```
- **p95 de latencia** por ruta:
  ```promql
  histogram_quantile(0.95, sum by (le, path) (rate(http_request_duration_seconds_bucket[5m])))
  ```
- **Recomendaciones por tenant** (negocio):
  ```promql
  sum by (client_id) (increase(recommendations_total[1h]))
  ```

### SLO/SLA (ideas)
- **Disponibilidad**: error rate < 1% en 30d.
- **Latencia**: p95 < 300ms para `/greet`; p95 < 800ms para `/answer`.
- **Cuotas**: alertar cuando `X-RateLimit-Remaining` se acerque a 0 (ver sección Alerting).

---

## 3) Alerting (reglas Prometheus de ejemplo)

> Requiere Prometheus + Alertmanager en tu entorno.

**Error rate alto (5m):**
```yaml
groups:
- name: pharmaassistant.rules
  rules:
  - alert: HighErrorRate
    expr: sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05
    for: 10m
    labels:
      severity: critical
    annotations:
      summary: "Error rate > 5%"
      description: "Más de 5% de respuestas 5xx en los últimos 10m."
```

**Latencia p95 alta en `/answer`:**
```yaml
  - alert: HighLatencyP95
    expr: histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{path="/answer"}[5m]))) > 0.8
    for: 10m
    labels:
      severity: warning
    annotations:
      summary: "p95 /answer > 800ms"
      description: "La latencia p95 de /answer supera 800ms por 10m."
```

**Caída de throughput (posible caída de servicio):**
```yaml
  - alert: NoTraffic
    expr: sum(rate(http_requests_total[5m])) < 0.01
    for: 15m
    labels:
      severity: warning
    annotations:
      summary: "Tráfico inapreciable"
      description: "Casi sin peticiones en 15m; revisar despliegue/ingress/cliente."
```

---

## 4) Trazas (Opcional, OpenTelemetry)

- **Inicialización**: `service/tracing.py` → `setup_tracing("pharmaassistant")`.
- **Exportador**: `ConsoleSpanExporter` (para empezar). Más tarde, usa OTLP → Jaeger/Tempo/OTel Collector.
- **Uso recomendado**: envolver llamadas a modelos, E/S de índice, y pasos clave del `PharmaAssistant` en spans.

### Verificación rápida
```bash
poetry run uvicorn service.main:app --port 8080
curl -s http://localhost:8080/healthz >/dev/null
# Verás spans en consola si activaste tracing
```

---

## 5) Dashboards (Grafana)

### Paneles útiles
- **Visión general** (por ruta):
  - Gráfico: QPS por `path`
  - Tabla: error rate por `path`
  - Gráfico: p95 por `path`
- **Negocio**:
  - `increase(recommendations_total[1h])` por `client_id`
- **Tenants**:
  - Panel de distribución de tráfico por `client_id` (si etiquetas las métricas HTTP con `client_id`; ojo a la cardinalidad).

### Variables
- `path` (regex sobre series)
- `client_id` (si las series tienen esa etiqueta)

---

## 6) Local: Prometheus + Grafana (docker-compose override)

Crea `docker-compose.override.yml` con servicios de observabilidad para **desarrollo local**:

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    container_name: prom
    ports: ["9090:9090"]
    volumes:
      - ./ops/observability/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
    depends_on:
      - pharmaassistant

  grafana:
    image: grafana/grafana:latest
    container_name: grafana
    ports: ["3000:3000"]
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - prometheus
```

Archivo `ops/observability/prometheus.yml` (scrape local):
```yaml
global:
  scrape_interval: 15s

scrape_configs:
- job_name: pharmaassistant
  static_configs:
  - targets: ["pharmaassistant:8080"]
```

### Puesta en marcha local
```bash
docker compose up -d           # levanta la API
docker compose -f docker-compose.yml -f docker-compose.override.yml up -d
# Abre Prometheus: http://localhost:9090  y Grafana: http://localhost:3000 (admin/admin)
```

---

## 7) Operación y troubleshooting

- **`/metrics` no responde** → verifica que `register_metrics(app)` se llama y que no hay middlewares bloqueando.
- **Latencias altas** → inspecciona p95/p99, CPU/RAM del pod/host, y evalúa cache o reducción de D en embeddings.
- **Error rate alto** → correlaciona con despliegues recientes; revisa `/readyz`, logs y estado de índices por tenant.
- **Cardinalidad de etiquetas** → evita incluir IDs de sesión o textos libres como `label` (puede degradar Prometheus).

---

## 8) Referencias rápidas

- **Logs**: `LOG_LEVEL`, JSON por stdout; middleware en `service/main.py`.
- **Métricas**: `/metrics` (Prometheus client), nombres anteriores.
- **Trazas**: `service/tracing.py` (opcional).
- **Compose observabilidad**: ver override y `ops/observability/prometheus.yml`.
- **Runbooks**: `ops/runbook-incident-500s.md`, `ops/runbook-reindex.md`, `ops/runbook-quotas.md`.
