# tests/integration/test_service_quota.py
import os
import json
from pathlib import Path
import tempfile
import shutil
import pytest
from fastapi.testclient import TestClient

import service.main as svc
import service.quota as quota

@pytest.fixture(autouse=True)
def tmp_quota_dir(monkeypatch):
    # Forzamos la base de cuotas a un directorio temporal
    d = Path(tempfile.mkdtemp(prefix="pa_quota_"))
    monkeypatch.setenv("QUOTA_BASE_DIR", str(d))
    # recargar módulo quota para que coja el nuevo env
    import importlib
    importlib.reload(quota)
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture(autouse=True)
def tenants_with_limit(monkeypatch):
    # Inyectamos tenants con límite muy bajo para test
    monkeypatch.setattr(svc, "TENANTS", {
        "client_1": {"api_key": "k1", "max_requests_per_day": 2},
    })

@pytest.fixture()
def client(monkeypatch):
    # Stub del assistant para que no cargue índices/llame a OpenAI
    class StubPA:
        def greet(self): return "hola!"
        def answer(self, m): return {"answer": "ok", "sources": []}
    def fake_get_assistant_for(client_id: str):
        return StubPA()
    monkeypatch.setattr(svc, "get_assistant_for", fake_get_assistant_for)
    return TestClient(svc.app)

def _headers():
    return {"X-API-Key": "k1"}

def test_quota_allows_first_two_requests_and_blocks_third(client: TestClient):
    # 1ª request (200) remaining debe decrementar
    r1 = client.get("/greet", params={"client_id": "client_1"}, headers=_headers())
    assert r1.status_code == 200
    assert r1.headers.get("X-RateLimit-Limit") == "2"
    assert r1.headers.get("X-RateLimit-Remaining") in ("1", "0")  # según timing

    # 2ª request (200)
    r2 = client.post("/answer", params={"client_id": "client_1"}, headers=_headers(), json={"message": "hi"})
    assert r2.status_code == 200
    assert r2.headers.get("X-RateLimit-Limit") == "2"
    assert r2.headers.get("X-RateLimit-Remaining") in ("0",)  # ya sin crédito

    # 3ª request (429)
    r3 = client.get("/greet", params={"client_id": "client_1"}, headers=_headers())
    assert r3.status_code == 429
    assert r3.json()["detail"].lower().startswith("daily quota exceeded")
    assert r3.headers.get("X-RateLimit-Limit") == "2"
    assert r3.headers.get("X-RateLimit-Remaining") == "0"
