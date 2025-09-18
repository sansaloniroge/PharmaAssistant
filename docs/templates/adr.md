# ADR: <título corto y descriptivo>

- **ID:** ADR-<número secuencial>  
- **Estado:** Propuesto | Aceptado | Rechazado | Reemplazado por ADR-XX  
- **Fecha:** YYYY-MM-DD  
- **Autor/es:** <equipo/personas>  
- **Ámbito:** Backend | Ingesta | Observabilidad | CI/CD | Seguridad | Infra

---

## Contexto

> ¿Qué problema queremos resolver? ¿Por qué ahora? Incluye el *background* necesario y los requisitos (funcionales, no funcionales, de compliance, de coste, etc.).  
> Aclara supuestos y constraints (tecnológicos, organizativos).

- Problema / necesidad:
- Usuarios/tenants impactados:
- Requisitos clave (SLO/SLA, coste, privacidad, etc.):
- Alternativas conocidas o constraints:

## Decisión

> La decisión concreta que tomamos. Debe ser **clara y verificable**.

- Decisión:
- Alcance (in/out):
- Compatibilidad (backward/forward):
- Fecha objetivo / horizonte temporal:

## Alternativas consideradas

> Lista breve con pros/cons y por qué se descartaron.

1. Opción A — Descripción corta  
   - Pros:  
   - Contras:  
   - Motivo de descarte:
2. Opción B — …

## Consecuencias

> ¿Qué cambia al adoptar esta decisión? Incluye efectos técnicos, de equipo, coste, y riesgos.

- **Positivas:**  
  - …
- **Negativas / trade‑offs:**  
  - …
- **Riesgos:**  
  - …
- **Mitigaciones:**  
  - …

## Plan de implementación

> Roadmap y pasos operativos. Define *owners*, hitos y criterios de aceptación.

- Fase 1 (PoC / spike)
- Fase 2 (MVP / habilitadores)
- Fase 3 (generalización / limpieza técnica)
- Migración / datos / compatibilidad:
- Validación y rollout (canary, feature flag, por tenant):

## Impacto en contratos y datos

- **API / Endpoints:** cambios en rutas, payloads, códigos.  
- **Formatos de índice / catálogos:** versiones, migración (`index_info.json: version`).  
- **Compatibilidad multi‑tenant:** permisos, cuotas, *profiles* y *prompts*.  

## Seguridad y cumplimiento

- Autenticación/autorización, manejo de secretos.  
- CORS / headers / *rate limiting*.  
- Consideraciones GDPR/retención si aplica.

## Observabilidad y operación

- **Métricas a vigilar:** `http_*`, `recommendations_total`, p95, error rate.  
- **Alertas nuevas o umbrales:** …  
- **Logging/tracing:** spans/fields relevantes.  
- **Rollback plan:** cómo revertir (tags de imagen, switches, versión de índice).  
- **Runbooks afectados:** enlazar a `ops/`.

## Coste y rendimiento

- Estimación de coste (CPU, memoria, llamadas externas).  
- Impacto en latencia *p95/p99*.  
- Oportunidades de *caching* / *preload*.

## Preguntas abiertas

- …

## Referencias

- Issues/PRs relacionados: …  
- Documentos/poCs: …  
- Enlaces externos: …

---

### Sugerencias de uso

- **Nombre de archivo:** `docs/adrs/ADR-00X-<slug>.md`  
- **Proceso:** abre PR con el ADR en estado *Propuesto* → revisión → merge como *Aceptado* o *Rechazado*.  
- **Sustituciones:** si este ADR reemplaza a otro, indícalo en **Estado** y referencia cruzada.

---

## Ejemplo mínimo (rellenable)

```markdown
# ADR: Migrar embeddings a text-embedding-3-small
- ID: ADR-007
- Estado: Aceptado
- Fecha: 2025-09-18
- Autor/es: Backend Team
- Ámbito: Ingesta

## Contexto
Necesitamos reducir coste por millón de tokens ~40% manteniendo calidad suficiente.

## Decisión
Usar `text-embedding-3-small` y fijar `D=1536`. Versionar `index_info.json` a `"v2"`.

## Alternativas consideradas
- Mantener modelo actual — Contras: coste alto.  
- Modelo local open-source — Contras: peor recall en nuestro corpus y más complejidad operativa.

## Consecuencias
- Positivas: coste ↓40%, throughput ↑.  
- Negativas: ligeras diferencias en ranking; reindex completo requerido.

## Plan de implementación
1) Script de reindex (scripts/build_index.py soporta backend nuevo).  
2) Reindex por tenant y validación de `count`/`dim`.  
3) Rollout progresivo (PRELOAD_TENANTS) y monitoreo de p95/error.

## Impacto en contratos y datos
`index_info.json.version = "v2"`; `dim=1536`.

## Seguridad y cumplimiento
Sin cambios (no PII).

## Observabilidad y operación
Alertar si `error rate > 3%` en `/answer` durante rollout; rollback a `"v1"` si aplica.

## Coste y rendimiento
Coste por llamada ↓; latencia media ↓ ~15%.

## Preguntas abiertas
¿Afecta a recall en categorías de baja frecuencia?

## Referencias
PR #123, doc interno con evaluación offline.
```
