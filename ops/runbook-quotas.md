# Runbook — Cuotas / Rate Limits por Tenant

Guía operativa para **diagnosticar, ajustar y recuperar** problemas relacionados con el **rate limit diario** por cliente (tenant).

---

## 1) Contexto rápido

- Cada tenant posee:
  - **API key** (`x-api-key`) y **client_id** (query param).
  - **Cuota diaria** `max_requests_per_day` configurada en `service/tenants.yaml`.
- La API devuelve **cabeceras**:
  - `X-RateLimit-Limit` — límite diario configurado.
  - `X-RateLimit-Remaining` — número de peticiones restantes.
- Al superar la cuota: **HTTP 429** `{"detail": "Daily quota exceeded"}`.

> La ventana de cuota es **diaria** (reset por fecha/estrategia de tu implementación).

---

## 2) Diagnóstico rápido

### 2.1 Verificar salud básica
```bash
curl -s http://HOST:8080/healthz | jq .
```

### 2.2 Comprobar estado para un tenant (requiere auth)
```bash
CID=client_1
KEY=secret_key_client_1
curl -i "http://HOST:8080/greet?client_id=$CID" -H "x-api-key: $KEY"
# Observa X-RateLimit-Limit y X-RateLimit-Remaining en la respuesta
```

### 2.3 Confirmar excedente de cuota
Si recibes `429`, valida cabeceras:
```bash
curl -i "http://HOST:8080/answer?client_id=$CID" \
  -H "x-api-key: $KEY" -H "content-type: application/json" \
  -d '{"message":"hola"}'
```

Resultados esperados:
- `HTTP/1.1 429 Too Many Requests`
- `X-RateLimit-Limit: <N>`
- `X-RateLimit-Remaining: 0`

---

## 3) Acciones de mitigación

### 3.1 Aumentar cuota temporalmente
Edita `service/tenants.yaml` para el tenant afectado:
```yaml
tenants:
  client_1:
    api_key: "secret_key_client_1"
    max_requests_per_day: 5000    # <= nuevo límite temporal
```

Reinicia el servicio (según tu plataforma) para recargar el archivo, o si tu implementación lo soporta, fuerza recarga.

> **Buenas prácticas**: documenta el cambio en un ticket y establece una **fecha de expiración** para volver al valor normal.

### 3.2 Comunicar ventana de reset
Si no puedes aumentar la cuota, comunica a cliente **cuándo resetea** la ventana (e.g. UTC 00:00) y su `remaining` actual.

---

## 4) Simular y reproducir (útil para QA)

### 4.1 Disparar X peticiones rápidas hasta agotar
```bash
CID=client_1
KEY=secret_key_client_1
API=http://HOST:8080

for i in $(seq 1 10); do
  curl -s "$API/greet?client_id=$CID" -H "x-api-key: $KEY" >/dev/null
done

# Ver el remaining
curl -i "$API/greet?client_id=$CID" -H "x-api-key: $KEY" | grep -i rate
```

### 4.2 Script de carga mínima
```bash
#!/usr/bin/env bash
API=${1:-http://HOST:8080}
CID=${2:-client_1}
KEY=${3:-secret_key_client_1}
N=${4:-20}

for i in $(seq 1 $N); do
  curl -s "$API/greet?client_id=$CID" -H "x-api-key: $KEY" >/dev/null
done

curl -i "$API/greet?client_id=$CID" -H "x-api-key: $KEY" | grep -i rate
```

---

## 5) Observabilidad y alertas

### 5.1 Métricas relevantes
- **HTTP**: `http_requests_total{status}` (tasa de `429` por tenant/ruta si etiquetas).
- **Negocio**: `recommendations_total{client_id}` (caudal por tenant).
- **Latencia**: `http_request_duration_seconds_*` (p95/p99).

### 5.2 Reglas de alerta (ideas)
- **429 anómalo**:
  ```promql
  sum(rate(http_requests_total{status="429"}[10m])) by (path) > 1
  ```
- **Consumo alto por tenant** (si expones etiqueta `client_id` en HTTP):
  ```promql
  sum(rate(http_requests_total{path="/answer", client_id="client_1"}[5m])) > 5
  ```

> Ajusta cardinalidad: evita poner `client_id` en todas las series si el número es grande; usa sólo en métricas de negocio o sampleadas.

---

## 6) Política de reset y almacenamiento

La lógica de **reset diario** y almacenamiento del consumo se implementa en `service/quota.py` (o equivalente). Modalidades comunes:

- **In-memory** (simple): reinicia con el proceso; **no** compartido entre réplicas.
- **Persistente** (Redis/DB): compartido entre réplicas; recomendado para producción.

**Recomendación**: en entornos con múltiples réplicas, usa un **backend compartido** (p. ej., Redis) o enruta por **sticky sessions** si mantienes el contador en memoria.

---

## 7) Contención y prevención

- **Throttling en clientes**: pide a integradores aplicar backoff exponencial y límites locales.
- **Cuotas por endpoint**: si un tenant satura `/answer`, considera límites diferenciados por ruta.
- **Planes y SLAs**: documenta `max_requests_per_day` por plan (básico/pro/enterprise).

---

## 8) Checklist de soporte

- [ ] Confirmar `client_id` y `x-api-key`.  
- [ ] Verificar `X-RateLimit-*` en respuestas.  
- [ ] Consultar métricas de `429` y caudal del tenant.  
- [ ] Aumentar cuota temporalmente si aplica (documentar).  
- [ ] Comunicar ventana de reset.  
- [ ] Registrar ticket con causa + acciones (y fecha para revertir cambios).

---

## 9) Troubleshooting

**Cabeceras ausentes**  
- Verifica que el **guard** de cuota (`quota_guard`) se ejecute antes del handler.
- Revisa middlewares que puedan sobrescribir headers.

**Reinicios no sincronizados**  
- Si usas almacenamiento **in-memory**, cada réplica cuenta por separado; migra a Redis/DB.

**Picos de tráfico inesperados**  
- Revisa logs JSON por `tenant`; investiga integraciones recientes o scraping.

**429 pese a cuota alta**  
- Confirmar zona horaria del reset; revisar reloj del sistema y la granularidad de la ventana.

---

## 10) Referencias

- `service/tenants.yaml` (cuotas/keys)  
- `service/quota.py` (lógica de consumo y reset)  
- `docs/observability.md` (métricas y alertas)  
- `ops/runbook-incident-500s.md` (si 429 se combinan con 5xx)  
- `docs/api.md` (cabeceras de respuesta y endpoints)
