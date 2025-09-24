# service/logging_middleware.py
from __future__ import annotations
import json
import os
import time
import uuid
from pathlib import Path
from typing import Callable, Awaitable
from fastapi import Request, Response, FastAPI

def _tenant_log_path(client_id: str) -> Path:
    # Se puede redirigir con LOG_BASE_DIR (útil en tests/CI)
    base = Path(os.getenv("LOG_BASE_DIR", "../tests/integatrion"))
    p = base / "storage" / client_id / "usage.log"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _json_dump_line(entry: dict) -> str:
    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))

def setup_logging_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def log_requests(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
        start = time.time()
        rid = str(uuid.uuid4())
        path = request.url.path
        method = request.method
        client_id = request.query_params.get("client_id") or "n/a"

        # Llamada a la ruta
        response: Response
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception as e:
            status = 500
            # imprimimos log de error y relanzamos
            entry_err = {
                "ts": time.time(),
                "rid": rid,
                "client_id": client_id,
                "method": method,
                "path": path,
                "status": status,
                "error": str(e.__class__.__name__),
            }
            print(_json_dump_line(entry_err))
            raise

        latency_ms = int((time.time() - start) * 1000)

        # Headers de rate limit si existen
        limit = response.headers.get("X-RateLimit-Limit")
        remaining = response.headers.get("X-RateLimit-Remaining")

        entry = {
            "ts": time.time(),
            "rid": rid,
            "client_id": client_id,
            "method": method,
            "path": path,
            "status": status,
            "latency_ms": latency_ms,
        }
        if limit is not None:
            entry["rate_limit"] = {"limit": int(limit), "remaining": int(remaining or 0)}

        # 1) stdout (para CloudWatch)
        print(_json_dump_line(entry))

        # 2) fichero por tenant (si hay client_id)
        if client_id != "n/a":
            try:
                log_path = _tenant_log_path(client_id)
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(_json_dump_line(entry) + "\n")
            except Exception:
                # no rompemos la request por fallo de logging
                pass

        # Propaga request id al cliente (útil para soporte)
        response.headers["X-Request-ID"] = rid
        return response
