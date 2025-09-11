# service/main.py
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict

from fastapi import FastAPI, HTTPException, Header, Query, Depends, Response
from pydantic import BaseModel
import yaml

from app.pharma_assistant import Settings, PharmaAssistant
from app.profile_resolver import resolve_config_namespace
from service.quota import can_consume, consume  # 👈 NUEVO

from service.cors_security import setup_cors, setup_security_headers

app = FastAPI(title="PharmaAssistant API (SaaS)", version="1.0.0")

# CORS: lee orígenes permitidos de env (coma-separado)
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
setup_cors(app, allowed_origins=ALLOWED_ORIGINS)

# Security headers para todas las respuestas
setup_security_headers(app)


# --- Tenants registry ---
TENANTS_FILE = Path("service/tenants.yaml")
if not TENANTS_FILE.exists():
    raise RuntimeError("service/tenants.yaml not found. Please create it.")

with TENANTS_FILE.open("r", encoding="utf-8") as f:
    TENANTS: Dict[str, Dict[str, str]] = (yaml.safe_load(f) or {}).get("tenants", {})

DEFAULT_DAILY_LIMIT = 1000  # 👈 por si no está definido en tenants.yaml


class ChatIn(BaseModel):
    message: str


# --- Auth simple: API key por cliente ---
def auth_guard(x_api_key: Optional[str] = Header(None), client_id: str = Query(...)):
    tenant = TENANTS.get(client_id)
    if not tenant:
        raise HTTPException(401, f"Unknown client_id: {client_id}")
    expected = tenant.get("api_key")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(401, "Invalid API key")
    return client_id


# --- Quota guard (depende de auth_guard) ---
def quota_guard(
    response: Response,
    client_id: str = Depends(auth_guard),
) -> str:
    tenant = TENANTS.get(client_id, {})
    limit = int(tenant.get("max_requests_per_day", DEFAULT_DAILY_LIMIT))

    ok, remaining = can_consume(client_id, limit)
    if not ok:
        # Rate limit headers útiles
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = "0"
        raise HTTPException(status_code=429, detail="Daily quota exceeded")

    # consume (incrementa) y añade headers
    used, remaining_after = consume(client_id, limit)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining_after)
    return client_id


# --- Assistant cache por cliente ---
@lru_cache(maxsize=32)
def get_assistant_for(client_id: str) -> PharmaAssistant:
    cfg_ns = resolve_config_namespace(tenant_id=client_id, repo_root=Path("."))
    settings = Settings.from_config.__func__(cfg_ns)
    return PharmaAssistant(settings)


# --- Endpoints ---
@app.get("/healthz")
def healthz():
    return {"ok": True, "tenants": list(TENANTS.keys())}

@app.get("/tenants/{client_id}/healthz")
def tenant_healthz(client_id: str):
    try:
        pa = get_assistant_for(client_id)
        _ = pa.greet()
        return {"client_id": client_id, "ok": True}
    except Exception as e:
        raise HTTPException(500, f"Tenant {client_id} failed to load: {e}")

@app.get("/greet")
def greet(client_id: str = Depends(quota_guard)):  # 👈 usa quota_guard
    pa = get_assistant_for(client_id)
    return {"client_id": client_id, "greeting": pa.greet()}

@app.post("/answer")
def answer(payload: ChatIn, client_id: str = Depends(quota_guard)):  # 👈 usa quota_guard
    pa = get_assistant_for(client_id)
    try:
        result = pa.answer(payload.message)
        return {"client_id": client_id, **result}
    except Exception:
        # Evita filtrar internals; devolver error genérico
        raise HTTPException(500, "Internal error while generating the answer")
