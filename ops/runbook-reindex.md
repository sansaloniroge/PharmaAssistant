# Runbook — Reindexación (catálogos/índices)

> **Nota de ruta:** el índice real que usa la API en serving se reconstruye solo (primer request tras invalidar la firma) en `storage/<id>/index/` — ver `docs/configuration.md#25-storage-de-índices-storageidindex`. Los comandos de este runbook usan `scripts/build_index.py`, que escribe en `storage/<id>/` (sin `index/`) — hoy una herramienta offline desconectada de lo que lee la API. Para forzar la reconstrucción del índice real, borra `storage/<id>/index/` y deja que el primer request lo regenere.

Procedimiento operativo para **reconstruir los índices** de uno o varios tenants cuando cambian los catálogos CSV, prompts o el backend de embeddings.

---

## 1) ¿Cuándo usarlo?

- Actualización del **`products_catalog.csv`** de un cliente.
- Cambios en **prompts** que afecten la recuperación/score.
- Cambio de **modelo de embeddings** o parámetros (dimensión).
- Corrupción/pérdida de `storage/<tenant>/` o migración de versión (`index_info.json.version`).

**Impacto:** durante la reindexación **no es necesario** parar la API. El impacto aparece al **cargar** el nuevo índice (primer acceso puede ser más lento).

---

## 2) Riesgos y consideraciones

- Si cambias el **modelo/dimensión**, debes reindexar **todo** ese tenant (incompatible con el índice previo).
- Verifica permisos de escritura en `storage/` (el contenedor no debe ser root).
- Mantén un **backup** corto de la carpeta anterior para rollback rápido.

---

## 3) Pre-requisitos (checklist)

- [ ] CSV válido (`scripts/validate_catalog.py` sin errores).  
- [ ] Perfil y prompts presentes (`scripts/validate_profiles.py`).  
- [ ] `OPENAI_API_KEY` configurada si usarás embeddings OpenAI (o usa `--backend hash` en dev).  
- [ ] Espacio en disco suficiente para `embeddings.npy` y `meta.json`.  
- [ ] Accesos al host/volúmenes donde reside `storage/`.

---

## 4) Reindexación de **un tenant**

> Sustituye `<id>` por el client_id, p. ej. `client_1`.

### 4.1 Validaciones previas
```bash
python scripts/validate_patterns.py
python scripts/validate_profiles.py
python scripts/validate_catalog.py --client-id <id>
```

### 4.2 Backup (opcional pero recomendado)
```bash
ts=$(date +%Y%m%d-%H%M)
cp -a storage/<id> "storage/<id>.bak.$ts" 2>/dev/null || true
```

### 4.3 Construcción del índice
**Con OpenAI (si tienes `OPENAI_API_KEY`):**
```bash
python scripts/build_index.py --client-id <id>
```
**Sin OpenAI (desarrollo/local):**
```bash
python scripts/build_index.py --client-id <id> --backend hash
```

### 4.4 Verificación de artefactos
```bash
ls -lh storage/<id>/
cat storage/<id>/index_info.json | jq .
```

### 4.5 Verificación desde la API
```bash
API=${API:-http://localhost:8080}
KEY=secret_key_<id>
curl -s "$API/tenants/<id>/index/status?client_id=<id>" -H "x-api-key: $KEY" | jq .
# Debe mostrar exists=true, count>0, dim esperada
```

### 4.6 Warmup (opcional)
- Reinicia la API **o** arráncala con `PRELOAD_TENANTS="<id>"` para precargar el índice.  
- Comprueba `/readyz`:
```bash
curl -i "$API/readyz"
```

---

## 5) Reindexación de **todos los tenants**

```bash
python scripts/rebuild_all.py
```

Verifica cada carpeta en `storage/` y, si usas API, recorre el endpoint por tenant:
```bash
for cid in client_1 client_2; do
  curl -s "$API/tenants/$cid/index/status?client_id=$cid" -H "x-api-key: secret_key_$cid" | jq .
done
```

---

## 6) Rollout seguro

- Realiza la reindex fuera de horas pico si el índice es grande.  
- Usa `PRELOAD_TENANTS` para calentar los tenants críticos.  
- Observa métricas tras el cambio: **error rate** y **p95** en `/answer`.  
- Si notas regresión grave, **rollback** a la carpeta de backup.

---

## 7) Rollback (rápido)

```bash
# Detén cualquier proceso que esté escribiendo
ts="<marca_tiempo_del_backup>"
rm -rf storage/<id>
cp -a "storage/<id>.bak.$ts" storage/<id>
# (Opcional) Reinicia API o fuerza warmup
```

Verifica de nuevo con `/tenants/<id>/index/status`.

---

## 8) Troubleshooting

**“Index files not found…”**  
- Asegúrate de que `storage/<id>/embeddings.npy` y `meta.json` se generaron.  
- Comprueba permisos del volumen `storage/` (en Docker a veces el host crea archivos con root).

**Dimensión incorrecta (`dim` no coincide)**  
- Estás mezclando embeddings de distinta dimensión. Reindexa todo el tenant con el backend correcto.

**401/429 en endpoints**  
- Usa `x-api-key` y `client_id` correctos. Verifica `service/tenants.yaml`.

**Latencia alta tras reindex**  
- Usa `PRELOAD_TENANTS` para warmup. Revisa CPU/RAM del host/pod.

**Errores 500 genéricos**  
- Mira logs JSON; ejecuta `python scripts/validate_*` y reindexa. Comprueba que `count` de `meta.json` coincide con filas de `embeddings.npy`.

---

## 9) Notas operativas

- Mantén anotado el **modelo** y **versión** en `index_info.json.version` (útil para ADRs y auditoría).  
- Para catálogos grandes, considera procesar por lotes o paginación en la ingesta.  
- Si varios tenants comparten taxonomía, sincroniza `data/patterns/` y documenta en ADR.

---

## 10) Anexos

### 10.1 Makefile (opcional)
```makefile
reindex-%:
	python scripts/validate_catalog.py --client-id $* && \
	python scripts/build_index.py --client-id $*

reindex-all:
	python scripts/rebuild_all.py
```

### 10.2 Comandos útiles
```bash
# Ver tamaño y forma del embedding (npy)
python - <<'PY'
import numpy as np, sys, json
import os
cid = os.getenv("CID","client_1")
a = np.load(f"storage/{cid}/embeddings.npy")
print(json.dumps({"count": int(a.shape[0]), "dim": int(a.shape[1])}))
PY
```

---

**Checklist final**
- [ ] Validaciones previas OK.  
- [ ] Backup creado.  
- [ ] `build_index.py` ejecutado sin errores.  
- [ ] `index_info.json` coherente (count/dim/version).  
- [ ] Endpoint `/tenants/<id>/index/status` en verde.  
- [ ] Warmup realizado si aplica.  
- [ ] Métricas y logs sin anomalías tras el cambio.
