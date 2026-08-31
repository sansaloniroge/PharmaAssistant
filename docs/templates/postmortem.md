# Postmortem — <Título del incidente> (YYYY-MM-DD)

Plantilla para documentar incidentes de forma **clara, accionable y sin culpabilizar**.  
Objetivo: entender qué pasó, por qué, cómo lo resolvimos y qué haremos para evitar su repetición.

---

## 1) Resumen ejecutivo
- **Fecha/Hora (inicio–fin):** <YYYY-MM-DD hh:mm> — <YYYY-MM-DD hh:mm> (TZ)
- **Severidad:** SEV-1 | SEV-2 | SEV-3
- **Servicios afectados:** <API / Tenants / Región>
- **Impacto en usuarios/clientes:** <nº, % tráfico, funcionalidades>
- **Estado actual:** Resuelto | Mitigado | En curso
- **Owner del postmortem:** <nombre/área>

## 2) Línea temporal (UTC o TZ del equipo)
Enumera eventos clave con timestamps precisos.
- hh:mm — Detección (alerta, cliente, etc.)
- hh:mm — Primer diagnóstico / hipótesis
- hh:mm — Acciones de mitigación (qué, quién, resultado)
- hh:mm — Comunicación a stakeholders
- hh:mm — Resolución

> Adjunta enlaces a gráficos, dashboards, PRs y despliegues.

## 3) Detección y cobertura
- **Cómo se detectó:** alerta automática | reporte cliente | monitoreo manual
- **Alertas activadas:** sí/no (reglas, severidades)
- **MTTD (tiempo hasta detección):** <min>
- **Observaciones:** ¿Qué faltó para detectarlo antes? ¿Falsos negativos?

## 4) Impacto
- **Usuarios/Tenants afectados:** <lista o %>
- **Duración del impacto:** <min>
- **Errores y síntomas:** 5xx, timeouts, respuestas incorrectas, etc.
- **KPIs afectados:** error rate, p95/p99, QPS, recomendaciones_total, etc.

## 5) Causa raíz (RCA)
Usa 5 Whys o Ishikawa de forma breve.
- **Problema técnico concreto:** <qué falló>
- **Por qué 1:** …
- **Por qué 2:** …
- **Por qué 3:** …
- **Por qué 4:** …
- **Por qué 5:** …
- **Contribuyentes/condiciones previas:** deuda técnica, cambios recientes, picos de tráfico, datos corruptos.

## 6) Qué funcionó / Qué no
- **Funcionó:** herramientas, playbooks, comunicación, *feature flags*, rollback.
- **No funcionó / Obstáculos:** acceso, permisos, falta de alertas, ruido en logs, documentación desactualizada.

## 7) Resolución y verificación
- **Acciones que restauraron el servicio:** (ordenadas)
- **Verificación de la solución:** smoke tests, métricas estabilizadas, feedback cliente.

## 8) Acciones correctivas (CAPA)
Enumera tareas accionables con propietarios y fechas. Usa formato check-list.

| # | Acción | Tipo (Bug/Doc/Alerta/Proceso) | Owner | Fecha objetivo | Estado |
|---|-------|--------------------------------|-------|----------------|--------|
| 1 | …     | Alerta                         | @user | YYYY-MM-DD     | ☐      |
| 2 | …     | Código                         | @user | YYYY-MM-DD     | ☐      |
| 3 | …     | Documentación                  | @user | YYYY-MM-DD     | ☐      |

> Prioriza acciones que **previenen** la recurrencia y **mejoran la detección**.

## 9) Comunicación
- **Interna:** a qué canales/equipos se comunicó y cuándo.
- **Externa (clientes):** resumen no técnico, tiempos, siguientes pasos.
- **Actualizaciones:** enlace a incident report público (si aplica).

## 10) Evidencias y anexos
- Enlaces a PRs, commits, despliegues.
- Dashboards/Grafana, paneles de Prometheus (capturas o URLs).
- Logs relevantes (anonimizados).
- Artefactos (configs, índices) con hashes/versions (`index_info.json.version`).

## 11) Lecciones aprendidas
- **Técnicas:** diseño, límites, timeouts, backoff, tests, validaciones.
- **Proceso:** handoffs, guardias, comunicación, runbooks.
- **Herramientas:** gaps de observabilidad, métricas faltantes, tracing.

## 12) Checklist de cierre
- [ ] Acciones correctivas creadas como issues con prioridad/owner.
- [ ] Alertas ajustadas/verificadas (falsos negativos/respuesta).
- [ ] Documentación actualizada (runbooks, SOPs, *getting started*).
- [ ] Postmortem compartido y revisado por el equipo.
- [ ] Fecha para revisión de efectividad de acciones (D+14).

---

### Anexo A — Ejemplo breve

**Incidente:** Pico de 5xx en `/answer` tras despliegue v0.2.0 (SEV-2)  
**Línea temporal:**  
- 09:12 Alerta HighErrorRate (5m > 5%)  
- 09:16 Identificado regress en normalización de precios (CSV edge cases)  
- 09:25 Rollback a imagen `:0.1.5` (errores normalizan)  
- 10:40 Hotfix `0.2.1` desplegado (tests de catálogo endurecidos)

**Causa raíz:** validación insuficiente de `Price` (locale `,` vs `.`).  
**Acciones:**  
- Añadir test en `validate_catalog.py` para locales (Owner @data, 2025-09-25).  
- Alerta p95 `/answer` > 800ms 10m (Owner @sre, 2025-09-20).  
- Checklist CI para “data changed” obliga a `validate_*` (Owner @platform, 2025-09-22).

---

> Mantén la cultura **blameless**: el objetivo es aprender y reforzar el sistema, no señalar culpables.
