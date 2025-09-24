# tests/integration/test_logging_middleware.py
import json
from pathlib import Path
import tempfile
import shutil
import pytest
from fastapi.testclient import TestClient

import service.main as svc

@pytest.fixture(autouse=True)
def stub_tenants(monkeypatch):
    # Tenants mínimos
    monkeypatch.setattr(svc, "TENANTS", {
        "client_1": {"api_key": "k1", "max_requests_per_day": 3}
    })

@pytest.fixture(autouse=True)
def tmp_logs(monkeypatch):
    # Redirige logs a un dir temporal (log file por tenant)
    d = Path(tempfile.mkdtemp(prefix="pa_logs_"))
    monkeypatch.setenv("LOG_BASE_DIR", str(d))
    yield d
    shutil.rmtree(d, ignore_errors=True)

@pytest.fixture()
def client(monkeypatch):
    # Stub del assistant para no cargar OpenAI ni índices
    class StubPA:
        def greet(self): return "hola!"
        def answer(self, m): return {"answer": "ok", "sources": []}
    def fake_get_assistant_for(client_id: str):
        return StubPA()
    monkeypatch.setattr(svc, "get_assistant_for", fake_get_assistant_for)
    return TestClient(svc.app)

def test_logging_stdout_and_file(client: TestClient, capsys, tmp_logs: Path):
    # Ejecuta una request
    r = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "k1"})
    assert r.status_code == 200
    assert r.headers.get("X-Request-ID")  # middleware añade request id

    # Captura stdout y valida que hay un JSON con los campos clave
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) >= 1
    last = json.loads(out[-1])
    assert last["client_id"] == "client_1"
    assert last["path"] == "/greet"
    assert last["status"] == 200
    assert isinstance(last["latency_ms"], int)

    # Valida que se escribió el fichero por tenant con esa entrada
    log_file = tmp_logs / "storage" / "client_1" / "usage.log"
    assert log_file.exists()
    lines = [json.loads(x) for x in log_file.read_text(encoding="utf-8").strip().splitlines()]
    assert any(e.get("path") == "/greet" and e.get("status") == 200 for e in lines)
