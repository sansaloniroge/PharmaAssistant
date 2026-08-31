# SECURITY.md — PharmaAssistant

Documento de **seguridad** para desarrollo y operación del sistema. Resume **controles técnicos**, **buenas prácticas**, procesos de **gestión de vulnerabilidades** y **respuestas a incidentes**.

> Este proyecto procesa consultas y sugiere productos; no debería almacenar PII sensible. Si el contexto cambia (p. ej., historiales), actualiza esta guía y aplica controles adicionales.

---

## 1) Superficie y modelo de amenazas (alto nivel)

**Actores:** usuarios finales (frontend / integraciones), operadores internos, CI/CD, infraestructura (contenedores, registry, artefactos).  
**Activos:** API (FastAPI), catálogos `data/clients/*`, índices `storage/*`, claves (`OPENAI_API_KEY`, API keys tenants), imagen Docker, pipelines CI.  
**Riesgos principales:**
- Exposición de **claves** o **tenants.yaml** en repos/imagenes/logs.
- **RCE** o abuso de endpoints (DoS / consumo elevado).
- **Fuga de datos** (catálogos/índices) por permisos o volúmenes mal configurados.
- **Supply chain** (deps Python, Docker base image, OIDC mal configurado).
- Configuración débil (CORS abierto, headers inseguros, TLS ausente).

---

## 2) Controles técnicos (runtime)

### 2.1 Autenticación y autorización
- **API key por tenant** (`x-api-key`) + `client_id` (query).  
- Rechazo genérico: `401` si key inválida o tenant desconocido.  
- Mantener claves fuera de repos; inyectarlas por **entorno** o **secret manager**.

### 2.2 Rate limiting / Cuotas
- Límite **diario** por tenant (`max_requests_per_day` en `service/tenants.yaml`).  
- Cabeceras: `X-RateLimit-Limit`, `X-RateLimit-Remaining`.  
- Respuesta al exceso: `429` (“Daily quota exceeded”).

### 2.3 CORS y cabeceras de seguridad
- CORS restringido por `ALLOWED_ORIGINS` (coma-separado, **URLs completas**).  
- Cabeceras recomendadas en todas las respuestas (middleware):
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: no-referrer`
  - `Permissions-Policy: geolocation=(), microphone=(), camera=()`
  - `Content-Security-Policy: default-src 'none'` *(para APIs, ajusta si sirves UI)*

### 2.4 Transporte
- **TLS** obligatorio en producción (terminación en LB/Ingress).  
- Deshabilitar protocolos/ciphers inseguros; forzar TLS 1.2+.

### 2.5 Logs
- **JSON** a stdout (sin PII ni secretos).  
- Incluir: método, ruta, código, latencia, `tenant`.  
- **No** registrar bodies ni headers sensibles (`x-api-key`).
- Rotación/retención gestionada por la plataforma (stdout).

### 2.6 Métricas
- Exponer en `/metrics` (Prometheus).  
- Proteger el endpoint si es público (ingress privado o autenticación a nivel de red).

### 2.7 Almacenamiento
- Índices en `storage/<tenant>/`; permisos mínimos de escritura.  
- Evitar que el contenedor ejecute como **root** (imagen no-root).  
- Backups y restauración documentados (ver `ops/runbook-restore-storage.md`).

---

## 3) Gestión de secretos

- **Nunca** versionar claves reales (`service/tenants.yaml`, `OPENAI_API_KEY`).  
- En contenedores, **montar** `service/tenants.yaml` como read-only o usar gestor (AWS Secrets Manager, etc.).  
- Rotación periódica (ver `ops/runbook-rotate-keys.md`).  
- Sanitizar logs y respuestas ante errores (errores 500 **genéricos**).

**Ejemplo de uso seguro (curl):**
```bash
API=http://localhost:8080
CID=client_1
KEY=secret_key_client_1
curl -s "$API/greet?client_id=$CID" -H "x-api-key: $KEY"
```

---

## 4) Supply chain y dependencias

- **Poetry** con `poetry.lock` versionado.  
- Actualizaciones periódicas de dependencias (semana/mes).  
- **Dockerfile** multi-stage, imagen **slim**, usuario no-root, `.dockerignore` para excluir datos/secretos.  
- Sin pipeline de publicación de imagen todavía (ver `docs/ci-cd.md`) — cuando exista, debería usar OIDC en vez de credenciales estáticas y un escaneo de vulnerabilidades (p. ej. Trivy) antes de publicar.

---

## 5) Desarrollo seguro

Checklist rápida para PRs:
- [ ] No exponer claves en código, tests o fixtures.  
- [ ] Sanitizar errores (`raise HTTPException(500, "Internal error…")`).  
- [ ] Añadir validaciones de entrada (tipos, tamaños).  
- [ ] Lint/Typecheck/Tests **verdes** (workflows CI).  
- [ ] Revisar cambios en `data/` con los scripts de validación (CSV/YAML).  
- [ ] Confirmar que CORS no está abierto (`*`).  

---

## 6) Endpoints sensibles y pruebas

- `/answer` y `/greet` requieren `x-api-key` y `client_id`.  
- `/metrics`: restringir acceso (red/ACL).  
- `/readyz`: no debe filtrar secretos; devuelve diagnóstico mínimo.  
- `/tenants/{id}/index/status`: no revelar rutas internas si no es necesario; útil para SRE.

**Smoke tests:**
```bash
# 401 por key inválida
curl -i "http://localhost:8080/greet?client_id=client_1" -H "x-api-key: WRONG"

# 429 al exceder cuota (simular en tests)
# -> verificar cabeceras X-RateLimit-*
```

---

## 7) Gestión de vulnerabilidades

- Canal interno para reportes: **security@tu-dominio.com**.  
- SLA sugerido para triage: **72h**; parcheo: **7–14 días** según severidad.  
- Etiquetar issues como `security` y mantener historial (sin datos sensibles).  
- Evaluar CVEs críticos de dependencias (`pip-audit`/Trivy) y plan de actualización.

---

## 8) Respuesta a incidentes (resumen)

1. **Detección**: alertas (error rate/latencia), reportes externos, hallazgos CI.  
2. **Contención**: reducir tráfico al tenant afectado, **rollback** a imagen estable, bloquear credenciales si aplica.  
3. **Erradicación**: aplicar fix/rotación de claves; reindex si hubo corrupción.  
4. **Recuperación**: monitorizar métricas y registros; smoke-tests.  
5. **Lecciones**: redactar **postmortem** (`docs/templates/postmortem.md`), acciones preventivas y actualización de docs.

---

## 9) Privacidad y retención de datos

- El sistema **no persiste conversaciones** por defecto (stateless).  
- Catálogos e índices pueden considerarse **datos de negocio** → aplicar retención definida por el cliente.  
- Solicitudes de borrado: eliminar carpeta `storage/<tenant>/` y regenerar si procede.  
- Cumple con políticas de la organización (GDPR/LOPDGDD si aplica).

---

## 10) Configuración de seguridad en despliegues

- **Docker Compose**: montar `tenants.yaml` en **read-only**; ajustar permisos de `storage/`.  
- **LB/Firewall**: limitar acceso público a `/metrics` y endpoints internos.

---

## 11) Auditoría rápida (self-check)

- [ ] `ALLOWED_ORIGINS` definido (no `*`).  
- [ ] `x-api-key` exigido en endpoints funcionales.  
- [ ] `service/tenants.yaml` **fuera** de la imagen y del repositorio público.  
- [ ] Imagen base slim + usuario **no-root**.  
- [ ] Logs sin PII/secretos.  
- [ ] Alertas básicas (error rate, p95, no tráfico).  
- [ ] Rotación de claves documentada (`ops/runbook-rotate-keys.md`).

---

## 12) Contacto de seguridad / Divulgación responsable

- Reportes: **security@tu-dominio.com**  
- Clave PGP (opcional): publica fingerprint y procedimiento.  
- Reconocimientos: mantener un `SECURITY-ACKS.md` si se desea.

---

Mantén este documento sincronizado con cambios de arquitectura, dependencias y procesos operativos.
