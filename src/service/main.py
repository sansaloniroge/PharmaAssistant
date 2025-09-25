import logging
import os
import time

from prometheus_client import Counter
import yaml
from pydantic import BaseModel
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict, Callable, Awaitable
from fastapi import FastAPI, Request, HTTPException, Header, Depends, Response

from app.pharma_assistant import PharmaAssistant, Settings
from app.profile_resolver import resolve_config_namespace
from service.cors_security import setup_cors, setup_security_headers
from service.index_loader import load_index, index_status
from service.logging_setup import setup_logging
from service.metrics import register_metrics
from service.quota import can_consume, consume

log = logging.getLogger("app")
setup_logging(os.getenv("LOG_LEVEL", "INFO"))

# Métrica de negocio
RECS_TOTAL = Counter("recommendations_total", "Total recommendations", ["client_id"], registry=None)
RECS_CREATED = Counter("recommendations_created", "Created recommendations", ["client_id"], registry=None)
REQUESTS = Counter("recommendations", "Number of recommendation requests", ["client_id"], registry=None)
app = FastAPI(title="PharmaAssistant API (SaaS)", version="1.0.0")
register_metrics(app)

# CORS
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
setup_cors(app, allowed_origins=ALLOWED_ORIGINS)
setup_security_headers(app)

# --- Tenants registry ---
TENANTS_PATH = Path(__file__).with_name("tenants.yaml")
if TENANTS_PATH.exists():
    try:
        _raw = yaml.safe_load(TENANTS_PATH.read_text(encoding="utf-8")) or {}
        TENANTS: dict[str, dict] = _raw  # ajusta el tipo si lo tienes definido
    except Exception:
        log.exception("Failed to load tenants.yaml; using empty config")
        TENANTS = {}
else:
    log.warning("service/tenants.yaml not found; using empty config (tests).")
    TENANTS = {}

DEFAULT_DAILY_LIMIT = 1000

class ChatIn(BaseModel):
    message: str

# --- Auth simple: API key por cliente ---
def auth_guard(request: Request, x_api_key: Optional[str] = Header(None)) -> str:
    """
    Valida la API key y obtiene client_id de forma segura:
    - Primero desde el path (/{client_id})
    - Si no está, desde la query (?client_id=...)
    """
    client_id = request.path_params.get("client_id") or request.query_params.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="client_id is required")

    tenant = TENANTS.get(str(client_id))
    if not tenant:
        raise HTTPException(status_code=401, detail=f"Unknown client_id: {client_id}")

    expected = tenant.get("api_key")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return str(client_id)


# --- Quota guard ---
def quota_guard(response: Response, client_id: str = Depends(auth_guard)) -> str:
    tenant = TENANTS.get(client_id, {})
    limit = int(tenant.get("max_requests_per_day", DEFAULT_DAILY_LIMIT))
    ok, _ = can_consume(client_id, limit)
    if not ok:
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = "0"
        raise HTTPException(status_code=429, detail="Daily quota exceeded")
    used, remaining_after = consume(client_id, limit)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining_after)
    return client_id

# --- Assistant cache por cliente ---
@lru_cache(maxsize=32)
def get_assistant_for(client_id: str) -> PharmaAssistant:
    cfg_ns = resolve_config_namespace(tenant_id=client_id, repo_root=Path("../../service"))
    settings = Settings.from_config(cfg_ns)
    return PharmaAssistant(settings)

# --- Readiness & preload opcional ---
_PRELOAD = [t.strip() for t in os.getenv("PRELOAD_TENANTS", "").split(",") if t.strip()]
_READY = {"ok": False, "errors": {}, "index": {}}

@app.on_event("startup")
async def _startup_preload():
    # Si declaras PRELOAD_TENANTS="client_1,client_2" se intentan preparar en arranque
    if not _PRELOAD:
        _READY["ok"] = True
        return

    errors = {}
    index_map = {}
    for tenant_id in _PRELOAD:
        try:
            # 1) fuerza init del asistente
            _ = get_assistant_for(tenant_id)
            # 2) intenta cargar índice en caliente (si falta, no bloquea la app)
            try:
                embeds, meta = load_index(tenant_id)
                index_map[tenant_id] = {"count": int(embeds.shape[0]), "dim": int(embeds.shape[1])}
            except Exception as ie:
                errors[tenant_id] = f"index: {ie}"
        except Exception as e:
            errors[tenant_id] = f"assistant: {e}"

    _READY["errors"] = errors
    _READY["index"] = index_map
    _READY["ok"] = len(errors) == 0

@app.get("/readyz")
def readyz():
    if _READY["ok"]:
        return {"ok": True, "preloaded": _PRELOAD, "index": _READY["index"]}
    return Response(status_code=503, content=str({"ok": False, "errors": _READY["errors"]}))

# --- Endpoints ---
@app.get("/healthz")
def healthz():
    return {"ok": True, "tenants": list(TENANTS.keys())}

@app.get("/tenants/{client_id}/healthz")
def tenant_healthz(client_id: str) -> Dict[str, object]:
    try:
        pa = get_assistant_for(client_id)
        _ = pa.greet()
        return {"client_id": client_id, "ok": True}
    except Exception:
        log.exception("Tenant %s failed to load", client_id)
        raise HTTPException(500, "Tenant failed to load")

@app.get("/tenants/{client_id}/index/status")
def tenant_index_status(client_id: str, _: str = Depends(auth_guard)) -> Dict[str, object]:
    """Devuelve estado del índice del tenant (tamaño, dimensión, ruta)."""
    return index_status(client_id)

@app.get("/greet")
def greet(client_id: str = Depends(quota_guard)) -> Dict[str, object]:
    pa = get_assistant_for(client_id)
    return {"client_id": client_id, "greeting": pa.greet()}

@app.post("/answer")
def answer(payload: ChatIn, client_id: str = Depends(quota_guard)) -> Dict[str, object]:
    pa = get_assistant_for(client_id)
    try:
        result = pa.answer(payload.message)
        RECS_TOTAL.labels(client_id).inc()
        return {"client_id": client_id, **result}
    except Exception:
        log.exception("Error while generating the answer for client_id=%s", client_id)
        raise HTTPException(500, "Internal error while generating the answer")

@app.middleware("http")
async def access_log(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    t0 = time.perf_counter()
    resp = await call_next(request)
    dur_ms = round((time.perf_counter() - t0) * 1000, 2)
    tenant = request.query_params.get("client_id") or request.headers.get("x-tenant-id") or "-"
    log.info(f"{request.method} {request.url.path} {resp.status_code} {dur_ms}ms tenant={tenant}")
    return resp
