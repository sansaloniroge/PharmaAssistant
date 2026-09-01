"""
Cross-tenant isolation tests.

Unlike test_service_auth_negatives.py (unknown/missing/garbage API keys) and
test_service_quota.py (single-tenant quota accounting), these tests actively try
to break the multi-tenant boundary using another tenant's *valid* credentials,
and verify quota/catalog data never leak between tenants.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import service.main as svc
import service.quota as quota
from app.profile_resolver import resolve_paths, resolve_config_namespace

# Quota storage isolation (a fresh QUOTA_BASE_DIR per test) is handled by the
# autouse `_isolated_quota_storage` fixture in tests/conftest.py.


# ---------------------------------------------------------------------------
# 1) Auth boundary: a tenant's own API key must never authorize another tenant
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def stub_tenants(monkeypatch):
    monkeypatch.setattr(svc, "TENANTS", {
        "client_1": {"api_key": "k1"},
        "client_2": {"api_key": "k2"},
    })


@pytest.fixture()
def client(monkeypatch):
    class StubPA:
        def __init__(self, tenant_id: str):
            self.tenant_id = tenant_id

        def greet(self):
            return f"hola desde {self.tenant_id}"

        def answer(self, m):
            return {"answer": f"[{self.tenant_id}] {m}", "sources": [f"{self.tenant_id}-product"]}

    monkeypatch.setattr(svc, "get_assistant_for", lambda client_id: StubPA(client_id))
    return TestClient(svc.app)


def test_tenant_api_key_rejected_for_other_tenant(client: TestClient):
    # client_1's real key must not authorize client_2, and vice versa.
    r = client.get("/greet", params={"client_id": "client_2"}, headers={"X-API-Key": "k1"})
    assert r.status_code == 401

    r = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "k2"})
    assert r.status_code == 401

    # sanity: each tenant's own key still works on its own client_id
    r = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "k1"})
    assert r.status_code == 200
    r = client.get("/greet", params={"client_id": "client_2"}, headers={"X-API-Key": "k2"})
    assert r.status_code == 200


def test_tenant_api_key_rejected_for_other_tenant_index_status(client: TestClient):
    r = client.get("/tenants/client_2/index/status", headers={"X-API-Key": "k1"})
    assert r.status_code == 401


def test_answer_never_mixes_up_tenant_identity(client: TestClient):
    r1 = client.post(
        "/answer", params={"client_id": "client_1"}, headers={"X-API-Key": "k1"},
        json={"message": "hi"},
    )
    r2 = client.post(
        "/answer", params={"client_id": "client_2"}, headers={"X-API-Key": "k2"},
        json={"message": "hi"},
    )
    assert r1.json()["sources"] == ["client_1-product"]
    assert r2.json()["sources"] == ["client_2-product"]


# ---------------------------------------------------------------------------
# 2) Quota isolation: consuming one tenant's quota must not affect another's
# ---------------------------------------------------------------------------

def test_quota_consumption_does_not_leak_across_tenants():
    limit = 2
    # Exhaust client_1's quota completely.
    quota.consume("client_1", limit)
    quota.consume("client_1", limit)
    ok, remaining = quota.can_consume("client_1", limit)
    assert ok is False
    assert remaining == 0

    # client_2 must still have its full quota available.
    ok, remaining = quota.can_consume("client_2", limit)
    assert ok is True
    assert remaining == limit
    assert quota.get_usage_today("client_2") == 0


def test_quota_http_isolation_between_tenants(client: TestClient):
    svc.TENANTS["client_1"]["max_requests_per_day"] = 1
    svc.TENANTS["client_2"]["max_requests_per_day"] = 1

    r1 = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "k1"})
    assert r1.status_code == 200
    # client_1 is now out of quota for today...
    r1_again = client.get("/greet", params={"client_id": "client_1"}, headers={"X-API-Key": "k1"})
    assert r1_again.status_code == 429

    # ...but client_2 is unaffected.
    r2 = client.get("/greet", params={"client_id": "client_2"}, headers={"X-API-Key": "k2"})
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# 3) Catalog/data isolation: a tenant's resolved paths must never point at
#    another tenant's files, even when one tenant is missing overrides.
# ---------------------------------------------------------------------------

@pytest.fixture()
def two_tenant_repo(tmp_path: Path) -> Path:
    (tmp_path / "profiles" / "clients").mkdir(parents=True)
    (tmp_path / "profiles" / "base.yaml").write_text(
        "version: 1\ndefaults:\n  top_k: 5\n  temperature: 0.6\n", encoding="utf-8"
    )

    for tenant, marker in [("tenant_a", "UNIQUE_PRODUCT_A"), ("tenant_b", "UNIQUE_PRODUCT_B")]:
        client_dir = tmp_path / "data" / "clients" / tenant
        client_dir.mkdir(parents=True)
        (client_dir / "products_catalog.csv").write_text(
            f"product_name\n{marker}\n", encoding="utf-8"
        )
        (tmp_path / "profiles" / "clients" / f"{tenant}.yaml").write_text(
            f"overrides:\n  paths:\n    data_csv: data/clients/{tenant}/products_catalog.csv\n",
            encoding="utf-8",
        )
    return tmp_path


def test_resolved_catalog_paths_do_not_cross_tenants(two_tenant_repo: Path):
    paths_a = resolve_paths("tenant_a", repo_root=two_tenant_repo)
    paths_b = resolve_paths("tenant_b", repo_root=two_tenant_repo)

    assert paths_a["DATA_PATH"] != paths_b["DATA_PATH"]
    assert paths_a["INDEX_DIR"] != paths_b["INDEX_DIR"]

    content_a = paths_a["DATA_PATH"].read_text(encoding="utf-8")
    content_b = paths_b["DATA_PATH"].read_text(encoding="utf-8")
    assert "UNIQUE_PRODUCT_A" in content_a and "UNIQUE_PRODUCT_B" not in content_a
    assert "UNIQUE_PRODUCT_B" in content_b and "UNIQUE_PRODUCT_A" not in content_b


def test_resolved_config_namespace_keeps_tenants_on_separate_index_dirs(two_tenant_repo: Path):
    cfg_a = resolve_config_namespace("tenant_a", repo_root=two_tenant_repo)
    cfg_b = resolve_config_namespace("tenant_b", repo_root=two_tenant_repo)

    assert cfg_a.DATA_PATH != cfg_b.DATA_PATH
    assert cfg_a.INDEX_DIR != cfg_b.INDEX_DIR
    assert "tenant_a" in cfg_a.INDEX_DIR
    assert "tenant_b" in cfg_b.INDEX_DIR


def test_missing_tenant_override_does_not_fall_back_to_another_tenants_catalog(two_tenant_repo: Path):
    # tenant_c has no profile/override at all: it must fail closed (no catalog
    # found) rather than silently resolving to tenant_a's or tenant_b's data.
    with pytest.raises(FileNotFoundError):
        resolve_paths("tenant_c", repo_root=two_tenant_repo)
