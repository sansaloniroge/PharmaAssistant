import pytest
from fastapi.testclient import TestClient

import service.main as svc

@pytest.fixture(autouse=True)
def stub_tenants(monkeypatch):
    # Inyecta un registro de tenants simple en memoria
    monkeypatch.setattr(svc, "TENANTS", {
        "client_1": {"api_key": "k1"},
        "client_2": {"api_key": "k2"},
    })

@pytest.fixture()
def client(monkeypatch):
    # Stub de PharmaAssistant para no depender de OpenAI ni índice
    class StubPA:
        def greet(self): return "Hola desde Stub!"
        def answer(self, msg): return {"answer": f"[stubbed]{msg}", "sources": ["S1", "S2"]}

    def fake_get_assistant_for(client_id: str):
        return StubPA()

    monkeypatch.setattr(svc, "get_assistant_for", fake_get_assistant_for)
    return TestClient(svc.app)

def test_healthz(client: TestClient):
    r = client.get("/healthz")
    assert r.status_code == 200
    js = r.json()
    assert js["ok"] is True
    assert "client_1" in js["tenants"]

def test_tenant_healthz(client: TestClient):
    r = client.get("/tenants/client_1/healthz")
    assert r.status_code == 200
    js = r.json()
    assert js["ok"] is True
    assert js["client_id"] == "client_1"

def test_greet_requires_auth(client: TestClient):
    # sin header → 401
    r = client.get("/greet", params={"client_id": "client_1"})
    assert r.status_code == 401

    # con header correcto → 200
    r = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "k1"})
    assert r.status_code == 200
    assert "Hola" in r.json()["greeting"]

def test_answer_flow(client: TestClient):
    r = client.post(
        "/answer",
        params={"client_id": "client_1"},
        headers={"X-API-Key": "k1"},
        json={"message": "Busco retinol"},
    )
    assert r.status_code == 200
    js = r.json()
    assert js["client_id"] == "client_1"
    assert js["answer"].startswith("[stubbed]")
    assert isinstance(js.get("sources", []), list)
