# Runbook — Restaurar `storage/` (índices por tenant)

> **Nota de ruta:** el índice real que usa la API en serving vive en `storage/<id>/index/` (sin `index_info.json`, `meta.json` con `signature`) — ver `docs/configuration.md#25-storage-de-índices-storageidindex`. Este runbook usa la ruta antigua `storage/<id>/` (sin `index/`), que es la que escribe la herramienta offline `scripts/build_index.py`, hoy desconectada de lo que lee la API. Ajusta las rutas según cuál de los dos estés restaurando.

Procedimiento para **restaurar o reconstruir** el almacenamiento de índices (`storage/<tenant>/`) cuando se pierde, corrompe o se migra de host. Incluye verificación y medidas preventivas.

---

## 1) Contexto y alcance

- Cada tenant mantiene sus artefactos de indexado en:
  ```
  storage/<id>/
  ├── embeddings.npy   # float32 [N, D]
  ├── meta.json        # N objetos (filas del CSV)
  └── index_info.json  # {count, dim, bytes, version}
  ```
- La API **lee** estos artefactos en tiempo de ejecución (carga en caliente o en startup con `PRELOAD_TENANTS`).

**Casos típicos:**
- Eliminación accidental / corrupción de `storage/<id>`.
- Migración a un nuevo host/nodo (cambio de ruta/disco).
- Cambio de **versión de índice** (p. ej., dimensión del embedding) que requiere regeneración.

---

## 2) Fuentes de verdad (prioridad)

1. `data/clients/<id>/products_catalog.csv`  ← **principal**
2. `data/clients/<id>/prompts/*.txt` (si influyen en la recuperación)
3. **Backups** previos de `storage/<id>` (tar/zip, snapshot)
4. `index_info.json` (si existe) para inspeccionar versión/dim esperada

> Si el CSV está intacto, **reconstruir** el índice es preferible a restaurar binarios antiguos.

---

## 3) Diagnóstico y verificación rápida

```bash
CID=<id>
ls -lh storage/$CID || echo "no existe la carpeta"
test -f storage/$CID/embeddings.npy || echo "falta embeddings.npy"
test -f storage/$CID/meta.json || echo "falta meta.json"
test -f storage/$CID/index_info.json || echo "falta index_info.json" && cat storage/$CID/index_info.json | jq .
```

Comprobar estado vía API (si disponible):
```bash
API=${API:-http://localhost:8080}
KEY=secret_key_$CID
curl -s "$API/tenants/$CID/index/status?client_id=$CID" -H "x-api-key: $KEY" | jq .
```

---

## 4) Escenario A — Reconstrucción desde CSV (recomendado)

### 4.1 Validar datos
```bash
python scripts/validate_patterns.py
python scripts/validate_profiles.py
python scripts/validate_catalog.py --client-id $CID
```

### 4.2 Construir índice
- Con OpenAI (si tienes `OPENAI_API_KEY` y backend configurado):
  ```bash
  python scripts/build_index.py --client-id $CID
  ```
- Sin OpenAI (modo determinista de desarrollo):
  ```bash
  python scripts/build_index.py --client-id $CID --backend hash
  ```

### 4.3 Verificar artefactos
```bash
ls -lh storage/$CID
cat storage/$CID/index_info.json | jq .
python - <<'PY'
import numpy as np, os, json
cid=os.getenv("CID","client_1")
a=np.load(f"storage/{cid}/embeddings.npy")
print(json.dumps({"count": int(a.shape[0]), "dim": int(a.shape[1])}))
PY
```

### 4.4 Verificar API
```bash
curl -s "$API/tenants/$CID/index/status?client_id=$CID" -H "x-api-key: $KEY" | jq .
```

---

## 5) Escenario B — Restaurar desde backup (tar/zip/S3)

### 5.1 Restaurar desde archivo `.tar.gz`
```bash
CID=<id>
TS=2025-09-18            # marca de tiempo del backup
mkdir -p storage/$CID
tar -xzf backups/storage_${CID}_${TS}.tar.gz -C storage/$CID --strip-components=2
# (ajusta --strip-components según la estructura interna del tar)
```

### 5.2 Restaurar desde S3 (ejemplo)
```bash
aws s3 cp s3://tu-bucket/backups/storage_${CID}_${TS}.tar.gz /tmp/
tar -xzf /tmp/storage_${CID}_${TS}.tar.gz -C storage/
```

### 5.3 Verificación
```bash
ls -lh storage/$CID
cat storage/$CID/index_info.json | jq .
```

> Si los artefactos restaurados no coinciden con tu versión/dim actual, **reconstruye** (ver §4).

---

## 6) Escenario C — Migración de host / ruta

### 6.1 Rsync (recomendado)
```bash
SRC_HOST=old-host
DST=storage/
CID=<id>
rsync -avz ${SRC_HOST}:/opt/pharma/storage/${CID}/ ${DST}/${CID}/
```

### 6.2 SCP (alternativa)
```bash
scp -r user@old-host:/opt/pharma/storage/${CID} storage/
```

### 6.3 Permisos
```bash
# Asegura que el proceso puede leer/escribir
chmod -R 755 storage/$CID || true
# En Docker: si el contenedor no es root puede requerir chown en el host
# chown -R $(id -u):$(id -g) storage/$CID
```

Verificación como en §4.3 y §4.4.

---

## 7) Escenario D — Cambio de versión (dimensión, backend)

Si cambiaste de modelo de embeddings o dimensión `D`:
- **No** reutilices `embeddings.npy` previos → **reindexa** todo el tenant (§4).
- Actualiza `index_info.json.version` automáticamente con el script (debería reflejar la nueva versión).

> Documenta el cambio con un **ADR** (`docs/templates/adr.md`) y registra la versión nueva.

---

## 8) Warmup y readiness (opcional)

Para evitar latencias de primer acceso, precalienta el tenant tras restaurar:
```bash
export PRELOAD_TENANTS="$CID"
poetry run uvicorn service.main:app --port 8080 --reload
curl -i "$API/readyz"
```

---

## 9) Troubleshooting

**Faltan archivos tras tar/rsync**  
- Revisa rutas internas del tar y el `--strip-components`.
- Comprueba permisos/propietario en el destino.

**`dim` no coincide**  
- Mezcla de backends o versiones. Reindexa todo el tenant.

**Errores de E/S (permission denied)**  
- Volúmenes montados **read-only** o usuario del contenedor sin permisos. Ajusta permisos en host.

**`/tenants/<id>/index/status` sigue diciendo `exists=false`**  
- Verifica `STORAGE_BASE` (por defecto `storage/`) y rutas relativas vs absolutas.
- Reinicia la API o fuerza warmup.

---

## 10) Prevención (mejores prácticas)

- Backups periódicos de `data/` y **snapshots** de `storage/` (si no es trivial reconstruir).
- Automatiza un **reindex nocturno** si el catálogo cambia con frecuencia.
- Mantén versionado `index_info.json.version` y registra cambios en ADRs.
- Verifica en CI la coherencia de catálogos (`scripts/validate_*`).

---

## 11) Rollback rápido (si la restauración degrada resultados)

1. Renombra la carpeta actual y vuelve al backup inmediato anterior:
   ```bash
   mv storage/$CID storage/${CID}.bad.$(date +%s)
   cp -a storage/${CID}.bak.<TS> storage/$CID
   ```
2. Reinicia/warmup y verifica métricas y `/greet`/`/answer`.

---

## 12) Checklist de cierre

- [ ] Artefactos presentes: `embeddings.npy`, `meta.json`, `index_info.json`.  
- [ ] `index_info.json` coherente (count/dim/version).  
- [ ] `/tenants/<id>/index/status` responde `exists=true`.  
- [ ] Warmup realizado si aplica (`/readyz` OK).  
- [ ] Métricas y logs sin errores durante ≥ 30 min.  
- [ ] Incidencia documentada (postmortem si fue severo).

---

## 13) Anexos

### 13.1 Crear backup `.tar.gz` de un tenant
```bash
CID=<id>
mkdir -p backups
tar -czf backups/storage_${CID}_$(date +%Y%m%d-%H%M).tar.gz storage/$CID
ls -lh backups | tail -n 1
```

### 13.2 Script rápido de sanity-check de un índice
```bash
#!/usr/bin/env bash
CID=${1:-client_1}
test -f storage/$CID/embeddings.npy || { echo "falta embeddings.npy"; exit 1; }
test -f storage/$CID/meta.json || { echo "falta meta.json"; exit 1; }
test -f storage/$CID/index_info.json || { echo "falta index_info.json"; exit 1; }
python - <<'PY'
import numpy as np, os, json
cid=os.getenv("CID","client_1")
a=np.load(f"storage/{cid}/embeddings.npy")
print(json.dumps({"count": int(a.shape[0]), "dim": int(a.shape[1])}))
PY
cat storage/$CID/index_info.json | jq .
```

---

Con esto deberías poder restaurar el `storage/` de cualquier tenant de forma segura y verificable.
