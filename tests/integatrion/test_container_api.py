# tests/integration/test_container_api.py
import os
import requests
import pytest

BASE_URL = os.getenv("PA_BASE_URL", "http://127.0.0.1:8080")
CLIENT_ID = os.getenv("PA_CLIENT_ID", "client_1")
API_KEY = os.getenv("PA_API_KEY", "secret_key_client_1")

def _url(path: str) -> str:
    return f"{BASE_URL}{path}"

def _service_available() -> bool:
    try:
        r = requests.get(_url("/healthz"), timeout=3)
        return r.status_code == 200
    except Exception:
        return False

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(
        not _service_available(),
        reason="PharmaAssistant container not reachable at PA_BASE_URL",
    ),
]

def test_healthz_returns_tenants():
    r = requests.get(_url("/healthz"), timeout=5)
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("ok") is True
    assert isinstance(payload.get("tenants"), list)
    assert CLIENT_ID in payload["tenants"]

def test_tenant_healthz_forces_load():
    r = requests.get(_url(f"/tenants/{CLIENT_ID}/healthz"), timeout=10)
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("ok") is True
    assert payload.get("client_id") == CLIENT_ID

def test_greet_with_auth_header():
    r = requests.get(
        _url("/greet"),
        params={"client_id": CLIENT_ID},
        headers={"X-API-Key": API_KEY},
        timeout=10,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("client_id") == CLIENT_ID
    assert isinstance(payload.get("greeting"), str)
    assert len(payload["greeting"]) > 0

def test_answer_with_auth_header():
    r = requests.post(
        _url("/answer"),
        params={"client_id": CLIENT_ID},
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={"message": "Busco un serum con retinol para piel grasa"},
        timeout=20,
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload.get("client_id") == CLIENT_ID
    assert "answer" in payload
    assert isinstance(payload["answer"], str)
