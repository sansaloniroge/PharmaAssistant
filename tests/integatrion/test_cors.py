from fastapi.testclient import TestClient
import os
import service.main as svc
import pytest

@pytest.fixture(autouse=True)
def stub_env_and_tenants(monkeypatch):
    # Permite localhost como origen para los tests
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000")
    # Re-cargar CORS si ya estaba inicializado: en tests suele valer así
    monkeypatch.setattr(svc, "TENANTS", {"client_1": {"api_key": "k1", "max_requests_per_day": 5}})

@pytest.fixture()
def client(monkeypatch):
    class StubPA:
        def greet(self): return "hola!"
        def answer(self, m): return {"answer": "ok", "sources": []}
    monkeypatch.setattr(svc, "get_assistant_for", lambda _: StubPA())
    return TestClient(svc.app)

def test_cors_preflight_options(client: TestClient):
    # Simula preflight desde frontend http://localhost:3000
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-API-Key, Content-Type",
    }
    r = client.options("/greet", params={"client_id": "client_1"}, headers=headers)
    assert r.status_code in (200, 204)
    # Debe devolver cabeceras de CORS
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-methods" in r.headers
    assert "access-control-allow-headers" in r.headers

def test_cors_get_with_origin(client: TestClient):
    r = client.get(
        "/greet",
        params={"client_id": "client_1"},
        headers={"X-API-Key": "k1", "Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
