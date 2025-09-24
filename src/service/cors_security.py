from __future__ import annotations
from typing import List, Optional
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app: FastAPI, allowed_origins: Optional[List[str]] = None) -> None:
    """
    Configura CORS. Para API pública típica, restringe a tu frontend/domino(s).
    allowed_origins puede venir de env: "https://app.tu-dom.com,https://otro.com"
    """
    origins = allowed_origins or []
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Authorization", "Content-Type", "X-API-Key",
            "X-Requested-With", "Accept", "Origin"
        ],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
        max_age=600,
    )

def setup_security_headers(app: FastAPI) -> None:
    """
    Añade cabeceras de seguridad razonables para una API JSON.
    Nota: HSTS solo tiene efecto sobre HTTPS (actívalo si estás detrás de ALB/TLS).
    CSP en una API puede ser minimalista; aquí la dejamos muy restrictiva.
    """
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response: Response = await call_next(request)

        # Protecciones básicas
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-XSS-Protection", "0")  # obsoleto pero explícito

        # HSTS (solo si sirves por HTTPS). Si no hay TLS delante, puedes desactivarlo.
        # max-age de 6 meses; ajusta si lo prefieres.
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=15552000; includeSubDomains")

        # Permissions Policy (limita APIs del navegador; irrelevante para API, pero endurece por si se embebe)
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

        # Content Security Policy (API: no sirve HTML; bloquea por defecto)
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'")

        # Cache control para endpoints dinámicos (ajusta si tienes recursos cacheables)
        if request.method != "GET":
            response.headers.setdefault("Cache-Control", "no-store")

        return response
