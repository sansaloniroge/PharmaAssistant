# Runbook — Incidente 500s (Errores Internos)

Guía operativa para investigar y resolver **picos de 5xx** en la API de PharmaAssistant. Aplica a `/greet`, `/answer` y endpoints de salud si se ven afectados.

---

## 0) Alcance y disparadores

**Cuándo se aplica**: incremento anómalo de `HTTP 5xx` (>3% en 5–10 min), alertas de disponibilidad, o reportes de usuarios.  
**SLO sugerido**: error rate < 1% mensual; p95 de `/answer` < 800ms.  
**Alertas ejemplo** (Prometheus):
```promql
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.03
```
```promql
histogram_quantile(0.95, sum by (le, path) (rate(http_request_duration_seconds_bucket{path="/answer"}[5m]))) > 0.8
```

---

## 1) Triaging rápido (≤ 5 min)

1. **Confirma alcance**  
   - ¿Afecta a todos los endpoints o solo a `/answer`?
   - ¿Todos los tenants o específico?

2. **Checks de salud**
   ```bash
   API=${API:-http://localhost:8080}
   curl -s $API/healthz | jq . || true
   curl -i $API/readyz || true
   ```

3. **Logs** (JSON a stdout)
   ```bash
   # Docker Compose
   docker compose logs -f pharmaassistant | sed -n '1,200p'

   # Local uvicorn
   poetry run uvicorn service.main:app --port 8080 --reload
   # Reproduce una llamada con curl en otra terminal y observa la traza
   ```

4. **Métricas**
   ```bash
   curl -s $API/metrics | head -n 50
   # Revisa http_requests_total por status y path
   ```

> Si `/readyz` devuelve 503 por preload fallido, consulta el detalle mínimo que expone y corrige la causa (ver §3).

---

## 2) Reproducción mínima

Elige un tenant afectado:
```bash
CID=${CID:-client_1}
KEY=${KEY:-secret_key_client_1}
curl -s "$API/greet?client_id=$CID" -H "x-api-key: $KEY" | jq .
curl -s "$API/answer?client_id=$CID" -H "x-api-key: $KEY" \
  -H "content-type: application/json" -d '{"message":"hola"}' | jq .
```

- **200 OK** → pasa a análisis histórico (posible pico puntual).  
- **401/429** → **no** es 500; gestionar con runbook de cuotas/auth.  
- **500** → procede a §3 (causas frecuentes).

---

## 3) Causas frecuentes y soluciones

### A) Índice ausente o corrupto
**Síntomas**: `/tenants/<id>/index/status` muestra `exists=false` o errores; `count=0`; excepciones de carga.  
**Acciones**:
```bash
curl -s "$API/tenants/$CID/index/status?client_id=$CID" -H "x-api-key: $KEY" | jq .

# Si falta índice o está corrupto:
python scripts/validate_profiles.py
python scripts/validate_catalog.py --client-id $CID
python scripts/build_index.py --client-id $CID
```
Verifica:
```bash
ls -lh storage/$CID/
cat storage/$CID/index_info.json | jq .
```

### B) Dimensión de embeddings incompatible
**Síntomas**: traza indica `shape mismatch`/`dim!=expected`.  
**Causa**: cambio de modelo D (p. ej., 1024→1536) sin reindexar.  
**Acciones**: reindexa completamente el tenant con el backend correcto (ver A).

### C) Permisos o volumen de `storage/` inválidos
**Síntomas**: errores de E/S (permission denied / read-only).  
**Acciones**:
```bash
# En host
chmod -R 777 storage || sudo chown -R $USER:$USER storage

# Comprueba que el contenedor no corre como root y tiene permiso de escritura
docker compose exec -it pharmaassistant sh -c 'id && ls -ld /app/storage && touch /app/storage/.rwtest && rm /app/storage/.rwtest'
```

### D) Dependencias externas (p. ej., OpenAI) fallan
**Síntomas**: timeouts, 5xx de proveedor, `rate limit` externo.  
**Acciones**:
- Reintentos con backoff (si está implementado).
- Cambiar temporalmente a `--backend hash` y reindexar para seguir operando sin proveedor (degradación controlada).
- Reintentar más tarde y monitorizar.

### E) Datos inválidos (CSV/YAML)
**Síntomas**: KeyError al mapear columnas, parseos de precio fallidos masivamente.  
**Acciones**:
```bash
python scripts/validate_patterns.py
python scripts/validate_profiles.py
python scripts/validate_catalog.py --client-id $CID
```
Corrige el CSV/Prompts y reindexa (§3A).

### F) Errores en inicialización de tenant (preload)
**Síntomas**: `/readyz` 503 con mapa de `errors{tenant: motivo}`.  
**Acciones**: corrige el tenant afectado (índice, perfil, permisos) y reinicia/rehaz preload:
```bash
export PRELOAD_TENANTS="$CID"
poetry run uvicorn service.main:app --port 8080 --reload
```

### G) Recursos insuficientes (OOM/CPU throttling)
**Síntomas**: reinicios, latencia disparada previa a 5xx.  
**Acciones**:
- Aumenta memoria/CPU del proceso/host, o reduce D / tamaño del índice.
- Preload selectivo de tenants críticos para evitar picos.
- Observa p95 y GC; evalúa workers de uvicorn.

---

## 4) Mitigación inmediata

- **Aislar tenant** problemático (si es 1–N): limitar tráfico de ese `client_id`.  
- **Rollback** a imagen estable si el incidente coincide con un release reciente.  
- **Desactivar** temporalmente features experimentales (si existen flags).

### Rollback rápido (local, sin registry)
Sin pipeline de publicación de imagen (ver `docs/ci-cd.md`), el rollback hoy es a nivel de código: vuelve al commit/tag estable anterior y reconstruye.
```bash
git checkout v0.1.5   # o el commit/tag estable conocido
docker compose down && docker compose up --build -d
```

---

## 5) Verificación de recuperación

- **Smoke tests**:
```bash
curl -s $API/healthz | jq .
curl -s "$API/greet?client_id=$CID" -H "x-api-key: $KEY" | jq .
curl -s "$API/answer?client_id=$CID" -H "x-api-key: $KEY" -H "content-type: application/json" -d '{"message":"hola"}' | jq .
```
- **Métricas**: error rate vuelve a normal; p95 estable.  
- **Logs**: ausencia de nuevas trazas de error por ≥ 30 min.

---

## 6) Comunicación

- **Interna**: notifica al canal del equipo (incidente abierto/cerrado, ETA).  
- **Clientes**: si hubo impacto visible, enviar resumen (no técnico) con ventana temporal y estado.  
- **Gestión**: si fue por despliegue, enlaza PR/commit y justifica rollback o hotfix.

---

## 7) Prevención (acciones post-incidente)

- Endurecer **validadores** (`scripts/validate_*`) para el caso observado.  
- Añadir/ajustar **alertas** (error rate, p95 por ruta, no tráfico).  
- Crear **ADR** si el cambio fue de arquitectura (modelo embeddings, almacenamiento).  
- Documentar un **postmortem** (plantilla en `docs/templates/postmortem.md`).

---

## 8) Checklist de cierre

- [ ] Causa raíz identificada y documentada.  
- [ ] Fix aplicado o rollback a estado estable.  
- [ ] Métricas y logs normales por ≥ 1h.  
- [ ] Comunicación a interesados enviada.  
- [ ] Acciones correctivas creadas (issues con owner/fecha).  
- [ ] Postmortem redactado y revisado.

---

## 9) Anexos

### 9.1 Comando para contar 5xx por path (Prometheus)
```promql
sum by (path) (increase(http_requests_total{status=~"5.."}[1h]))
```

### 9.2 Script de estrés controlado (local)
```bash
#!/usr/bin/env bash
API=${1:-http://localhost:8080}
CID=${2:-client_1}
KEY=${3:-secret_key_client_1}
N=${4:-20}
for i in $(seq 1 $N); do
  curl -s "$API/answer?client_id=$CID" -H "x-api-key: $KEY" -H "content-type: application/json" -d '{"message":"hola"}' >/dev/null
done
```

---
