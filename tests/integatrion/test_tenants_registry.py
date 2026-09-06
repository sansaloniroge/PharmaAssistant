"""
Regression test for service/tenants.yaml itself (the real file, not a stub).

Every other test in this suite monkeypatches svc.TENANTS, so a real tenant
missing from this file -- or docker-compose.yml preloading a tenant that
isn't in it -- would never surface anywhere else in CI.
"""
import re
from pathlib import Path

import yaml

TENANTS_PATH = Path(__file__).resolve().parents[2] / "src" / "service" / "tenants.yaml"
DOCKER_COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"

REAL_CATALOG_TENANT_ID = "farmacia_carmen_sanjuan"


def _load_tenants() -> dict:
    return yaml.safe_load(TENANTS_PATH.read_text(encoding="utf-8")) or {}


def test_real_catalog_tenant_is_registered_for_auth():
    tenants = _load_tenants()
    assert REAL_CATALOG_TENANT_ID in tenants, (
        f"'{REAL_CATALOG_TENANT_ID}' has a real catalog/profile on disk but isn't in "
        "src/service/tenants.yaml -- it can't authenticate."
    )
    assert tenants[REAL_CATALOG_TENANT_ID].get("api_key")


def test_docker_compose_preloads_a_registered_tenant():
    tenants = _load_tenants()
    compose_text = DOCKER_COMPOSE_PATH.read_text(encoding="utf-8")

    match = re.search(r"PRELOAD_TENANTS:\s*\$\{PRELOAD_TENANTS:-([^}]*)\}", compose_text)
    assert match, "docker-compose.yml's PRELOAD_TENANTS default pattern changed; update this test"

    preloaded_ids = [t.strip() for t in match.group(1).split(",") if t.strip()]
    assert preloaded_ids, "docker-compose.yml preloads no tenants by default"
    for tenant_id in preloaded_ids:
        assert tenant_id in tenants, (
            f"docker-compose.yml preloads '{tenant_id}' by default, but it isn't in tenants.yaml "
            "-- a fresh `docker compose up` would fail to preload it."
        )
