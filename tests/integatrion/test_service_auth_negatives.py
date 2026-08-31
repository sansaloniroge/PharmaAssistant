import pytest
from fastapi.testclient import TestClient
import service.main as svc

@pytest.fixture(autouse=True)
def stub_tenants(monkeypatch):
    monkeypatch.setattr(svc, "TENANTS", {"client_1": {"api_key": "k1"}})

@pytest.fixture()
def client():
    return TestClient(svc.app)

def test_unknown_client_id(client: TestClient):
    r = client.get("/greet", params={"client_id": "nope"}, headers={"X-API-Key": "k1"})
    assert r.status_code == 401

def test_missing_api_key(client: TestClient):
    r = client.get("/greet", params={"client_id": "client_1"})
    assert r.status_code == 401

def test_wrong_api_key(client: TestClient):
    r = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "bad"})
    assert r.status_code == 401
