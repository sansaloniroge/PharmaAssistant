"""
Regression test for get_assistant_for()'s repo_root resolution.

Unlike every other test in this suite, this one does NOT stub out
get_assistant_for -- it exercises the real function (with PharmaAssistant
itself stubbed, so no OpenAI call happens) to prove it resolves a real
tenant's config to files that actually exist on disk. Every other test
monkeypatches get_assistant_for entirely, so a broken repo_root here would
never surface anywhere else in CI.
"""
import pytest

import service.main as svc

REAL_TENANT_ID = "farmacia_carmen_sanjuan"


@pytest.fixture()
def captured_settings(monkeypatch):
    captured: dict = {}

    class CapturingStub:
        def __init__(self, settings):
            captured["settings"] = settings

    monkeypatch.setattr(svc, "PharmaAssistant", CapturingStub)
    svc.get_assistant_for.cache_clear()
    yield captured
    svc.get_assistant_for.cache_clear()


def test_get_assistant_for_resolves_real_tenant_catalog_that_exists_on_disk(captured_settings):
    svc.get_assistant_for(REAL_TENANT_ID)
    settings = captured_settings["settings"]

    assert settings.DATA_PATH.exists(), (
        f"get_assistant_for resolved DATA_PATH={settings.DATA_PATH!r} for tenant "
        f"'{REAL_TENANT_ID}', but that file does not exist. In the real deployment "
        "(Docker WORKDIR /app, or `uvicorn` run from the repo root locally) this means "
        "every /greet and /answer call 500s for every tenant."
    )
    assert settings.DATA_PATH.name == "products_catalog.csv"
    assert REAL_TENANT_ID in str(settings.DATA_PATH)
