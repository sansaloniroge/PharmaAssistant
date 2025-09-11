# tests/app/test_profile_resolver.py
from pathlib import Path
from types import SimpleNamespace
import tempfile
import shutil
import yaml
import os
import pytest

from app.profile_resolver import resolve_paths, resolve_config_namespace

BASE_YAML = {
    "version": 1,
    "defaults": {
        "top_k": 5,
        "temperature": 0.6,
        "models": {"embedding": "text-embedding-3-large", "chat": "gpt-4o-mini"},
        "paths": {
            "system_prompt": "data/general_prompts/system_prompt.txt",
            "compose_prompt": "data/general_prompts/compose_prompt.txt",
            "greeting_prompt": "data/general_prompts/greeting_prompt.txt",
            "no_match_prompt": "data/general_prompts/no_match_prompt.txt",
            "few_shot_prompt": "data/general_prompts/few_shot_prompt.txt",
            "schema_map": "data/patterns/schema_map.yaml",
            "price_patterns": "data/patterns/price_patterns.yaml",
            "category_patterns": "data/patterns/category_patterns.yaml",
            "skin_types": "data/patterns/skin_types.yaml",
            "medical_terms": "data/patterns/medical_terms.yaml",
        },
    }
}

CLIENT_YAML = {
    "store": {"id": "client_1_id", "name": "Client 1", "locale": "es-ES", "tone": "warm"},
    "overrides": {
        "top_k": 6,
        "paths": {
            "data_csv": "data/clients/client_1/products_catalog.csv"
            # no override for prompts/patterns → fallback to global
        },
    },
}

@pytest.fixture()
def tmp_repo():
    # Crea una estructura mínima temporal del repo
    tmp = Path(tempfile.mkdtemp(prefix="pa_repo_"))
    try:
        # perfiles
        (tmp / "profiles" / "clients").mkdir(parents=True, exist_ok=True)
        (tmp / "profiles" / "base.yaml").write_text(yaml.safe_dump(BASE_YAML), encoding="utf-8")
        (tmp / "profiles" / "clients" / "client_1.yaml").write_text(
            yaml.safe_dump(CLIENT_YAML), encoding="utf-8"
        )

        # data global
        (tmp / "data" / "patterns").mkdir(parents=True, exist_ok=True)
        for f in ["schema_map.yaml", "price_patterns.yaml", "category_patterns.yaml", "skin_types.yaml", "medical_terms.yaml"]:
            (tmp / "data" / "patterns" / f).write_text("key: value\n", encoding="utf-8")
        (tmp / "data" / "general_prompts").mkdir(parents=True, exist_ok=True)
        for f in ["system_prompt.txt", "compose_prompt.txt", "greeting_prompt.txt", "no_match_prompt.txt", "few_shot_prompt.txt"]:
            (tmp / "data" / "general_prompts" / f).write_text("prompt", encoding="utf-8")

        # cliente
        (tmp / "data" / "clients" / "client_1").mkdir(parents=True, exist_ok=True)
        (tmp / "data" / "clients" / "client_1" / "products_catalog.csv").write_text("name,price\nA,10\n", encoding="utf-8")
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def test_resolve_paths_fallbacks_and_csv(tmp_repo: Path):
    paths = resolve_paths("client_1", repo_root=tmp_repo, data_root=tmp_repo / "data", profiles_root=tmp_repo / "profiles")
    # Debe elegir el CSV del cliente
    assert (tmp_repo / "data" / "clients" / "client_1" / "products_catalog.csv") == paths["DATA_PATH"]
    # Debe construir INDEX_DIR por defecto si no está en profile
    assert str(paths["INDEX_DIR"]).endswith("storage/client_1/index") or "storage" in str(paths["INDEX_DIR"]).lower()

    # Prompts (no hay overrides → debe usar globales)
    assert (tmp_repo / "data" / "general_prompts" / "system_prompt.txt") == paths["SYSTEM_PROMPT_PATH"]
    assert (tmp_repo / "data" / "general_prompts" / "compose_prompt.txt") == paths["COMPOSE_PROMPT_PATH"]

    # Patterns (globales)
    assert (tmp_repo / "data" / "patterns" / "schema_map.yaml") == paths["SCHEMA_MAP_PATH"]
    assert (tmp_repo / "data" / "patterns" / "category_patterns.yaml") == paths["CATEGORY_PATTERNS_PATH"]

def test_resolve_config_namespace_values(tmp_repo: Path):
    ns = resolve_config_namespace("client_1", repo_root=tmp_repo, data_root=tmp_repo / "data", profiles_root=tmp_repo / "profiles")
    # Campos requeridos por Settings.from_config
    assert ns.DATA_PATH.endswith("products_catalog.csv")
    assert ns.TOP_K == 6
    assert ns.TEMPERATURE == 0.6
    assert ns.EMBEDDING_MODEL == "text-embedding-3-large"
    assert ns.CHAT_MODEL == "gpt-4o-mini"
    assert ns.STORE_NAME == "Client 1"
