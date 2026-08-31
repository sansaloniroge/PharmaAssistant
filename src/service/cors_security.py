from __future__ import annotations
from typing import List, Optional, Callable, Awaitable
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app: FastAPI, allowed_origins: Optional[List[str]] = None) -> None:
    """
    Configura CORS. Si no se especifica, por defecto permite localhost:3000 (tests/CI).
    """
    origins = allowed_origins if (allowed_origins and len(allowed_origins) > 0) else ["http://localhost:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-Request-ID"],
    )

def setup_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response: Response = await call_next(request)

        # Seguridad básica
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=15552000; includeSubDomains")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'")

        if request.method != "GET":
            response.headers.setdefault("Cache-Control", "no-store")

        return response
