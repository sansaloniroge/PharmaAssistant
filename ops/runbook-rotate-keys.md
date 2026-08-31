# Runbook — Rotación de claves y secretos

Procedimiento operativo para **rotar claves** de PharmaAssistant de forma segura y con mínima interrupción. Cubre rotación de **API keys por tenant** y **OPENAI_API_KEY**. Incluye verificación, rollback y automatización.

---

## 0) Alcance

**Claves/secretos cubiertos:**
- `service/tenants.yaml` → `api_key` por `client_id` (autenticación de la API).
- `OPENAI_API_KEY` (uso opcional en indexado/LLM).

> No hay pipeline de CI/CD con secretos de publicación (AWS/ECR) — se eliminó porque nunca llegó a funcionar (ver `docs/ci-cd.md`). Este runbook cubre solo lo que existe de verdad: local/Docker Compose.

---

## 1) ¿Cuándo rotar?

- Sospecha de **exposición** (repo, logs, soporte, issue).
- **Baja higiene** (claves compartidas entre equipos o entornos).
- **Política** periódica (trimestral/semestral).
- Cambio de proveedor o migración de entorno.

**Objetivo:** realizar la rotación sin afectar a los clientes; anunciar cambios si impactan integraciones.

---

## 2) Preparación (checklist)

- [ ] Identificar **qué** clave rotar y **dónde** se usa (API, scripts, CI, despliegues).
- [ ] Confirmar **procedimiento de comunicación** con clientes afectados.
- [ ] Acceso a la plataforma donde residan secretos (env, secret manager, repos).  
- [ ] Ventana y **plan de rollback** listo (clave anterior conservada un tiempo).

---

## 3) Rotar API keys por tenant (`service/tenants.yaml`)

### 3.1 Generar nueva clave
Usa un generador de secretos (mín. 32 chars, base64/hex):
```bash
python - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(48)))
PY
```
Guárdala temporalmente en un canal seguro (gestor de contraseñas).

### 3.2 Actualizar `service/tenants.yaml`
```yaml
tenants:
  client_1:
    api_key: "NUEVA_CLAVE_LARGA"
    max_requests_per_day: 1000
```
> Si quieres **período de transición**, soporta **dos claves** en código (lista de válidas) y elimina la antigua tras 24–72h.

### 3.3 Despliegue / recarga
- **Local/Compose**: reinicia el servicio para que lea el archivo.
  ```bash
  docker compose restart pharmaassistant
  ```

### 3.4 Verificación
```bash
# Debe fallar con la clave antigua -> 401
curl -i "http://HOST:8080/greet?client_id=client_1" -H "x-api-key: CLAVE_ANTIGUA"

# Debe funcionar con la clave nueva -> 200
curl -i "http://HOST:8080/greet?client_id=client_1" -H "x-api-key: NUEVA_CLAVE_LARGA"
```

### 3.5 Comunicación al cliente
Enviar correo/nota con:
- Fecha de **activación** y **expiración** de la clave anterior.
- Procedimiento para actualizar su integración.
- Contacto para soporte.

> Mantén la clave anterior operativa **un tiempo limitado** para evitar cortes.

---

## 4) Rotar `OPENAI_API_KEY` (u otro proveedor LLM)

### 4.1 Crear/generar clave nueva en el proveedor
- Registra y almacena la nueva clave en tu **secret manager** o variable de entorno.

### 4.2 Actualizar variable de entorno

**Local/Compose** (`.env` o `docker-compose.yml`):
```bash
export OPENAI_API_KEY="sk-***NUEVA***"
docker compose up -d --build
```

### 4.3 Verificación
- Reindexa un tenant de prueba (si el backend por defecto usa OpenAI):
  ```bash
  python scripts/build_index.py --client-id client_1
  ```
- Ejecuta smoke tests:
  ```bash
  curl -s "http://HOST:8080/healthz" | jq .
  curl -s "http://HOST:8080/greet?client_id=client_1" -H "x-api-key: NUEVA_CLAVE_CLIENTE" | jq .
  ```

### 4.4 Contingencia
Si el proveedor está caído o la nueva clave falla:
- Conmuta a **backend determinista** para seguir operando (degradado controlado):
  ```bash
  python scripts/build_index.py --client-id client_1 --backend hash
  ```
- Documenta incidencia y planifica reindex real cuando el proveedor esté estable.

---

## 5) Rollback

- Conserva las **claves antiguas** durante un período corto y en un almacén seguro.
- Si la nueva clave causa fallo, **reaplica** la anterior temporalmente:
  ```yaml
  # service/tenants.yaml
  tenants:
    client_1:
      api_key: "CLAVE_ANTERIOR"
  ```
- Reinicia servicio y notifica el incidente. Programa una **segunda rotación** con diagnóstico resuelto.

---

## 6) Automatización (opcional)

### 6.1 Script de rotación de key por tenant
```bash
#!/usr/bin/env bash
TENANTS=service/tenants.yaml
CID="$1"
NEWKEY="$2"
[ -z "$CID" -o -z "$NEWKEY" ] && { echo "uso: $0 <client_id> <new_key>"; exit 1; }
python - <<PY
import yaml, sys
f="$TENANTS"
with open(f, "r", encoding="utf-8") as fh:
    data=yaml.safe_load(fh) or {}
data.setdefault("tenants", {}).setdefault("$CID", {})["api_key"] = "$NEWKEY"
with open(f, "w", encoding="utf-8") as fh:
    yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)
print("actualizado", f)
PY
```

### 6.2 Doble clave temporal (grace period)
Puedes extender `auth_guard` para aceptar **lista de claves** por tenant y planificar un **apagado programado** de la clave antigua.

---

## 7) Seguridad y buenas prácticas

- **Nunca** versionar claves reales; usa env/secret manager.
- Limitar la exposición de `service/tenants.yaml` (montar **read-only**).
- No registrar `x-api-key` ni `OPENAI_API_KEY` en logs.
- Anotar rotaciones en un registro interno (ticketing) con fecha/owner/justificación.
- Establecer **rotación periódica** y recordatorios (automation o calendario).

---

## 8) Verificación de cierre

- [ ] Key nueva funcional (200 OK en `/greet` / `/answer`).  
- [ ] Key antigua bloqueada (401).  
- [ ] Sin incremento de errores 4xx/5xx post-rotación.  
- [ ] Comunicación al cliente confirmada (si aplica).  
- [ ] Tickets/documentación actualizados.

---

## 9) Plantillas útiles

### 9.1 Mensaje a cliente (ejemplo)
```
Asunto: Rotación de API key — <cliente>

Hola <contacto>,

Por seguridad, rotaremos vuestra API key el <fecha/hora, TZ>. 
La nueva clave será válida desde ese momento y la actual dejará de funcionar el <fecha/hora, TZ>.

Nueva API key: <se entrega por canal seguro>

Por favor, actualizad vuestras integraciones antes de la fecha indicada.
Para cualquier duda, escribid a soporte@tu-dominio.com.

Gracias,
Equipo PharmaAssistant
```

---

**Registro de cambios (incluir en ticket interno):**
- Fecha/hora rotación, claves afectadas, owner, verificación, incidencias.
