from fastapi.testclient import TestClient
import service.main as svc
import pytest

@pytest.fixture(autouse=True)
def stub_tenants(monkeypatch):
    monkeypatch.setattr(svc, "TENANTS", {"client_1": {"api_key": "k1", "max_requests_per_day": 5}})

@pytest.fixture()
def client(monkeypatch):
    class StubPA:
        def greet(self): return "hola!"
        def answer(self, m): return {"answer": "ok", "sources": []}
    monkeypatch.setattr(svc, "get_assistant_for", lambda _: StubPA())
    return TestClient(svc.app)

def test_security_headers_present(client: TestClient):
    r = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "k1"})
    assert r.status_code == 200

    # Básicos
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert r.headers.get("Permissions-Policy") is not None
    assert r.headers.get("Content-Security-Policy") == "default-src 'none'"

    # Rate-limit expuestos por CORS
    assert "X-RateLimit-Limit" in r.headers
    assert "X-RateLimit-Remaining" in r.headers

    # Request ID del logging middleware
    assert "X-Request-ID" in r.headers
