from pathlib import Path
import yaml
import pytest

from app.profile_loader import deep_merge, load_tenant_profile


# ---------- helpers ----------

def ydump(path: Path, data: dict | None):
    path.write_text(yaml.safe_dump(data if data is not None else {}, sort_keys=False), encoding="utf-8")


# ---------- deep_merge tests ----------

def test_deep_merge_basic_override():
    base = {"a": 1, "b": {"x": 1, "y": 2}}
    override = {"b": {"y": 99}, "c": 3}
    out = deep_merge(base, override)
    assert out == {"a": 1, "b": {"x": 1, "y": 99}, "c": 3}
    # base debe permanecer intacto
    assert base == {"a": 1, "b": {"x": 1, "y": 2}}


def test_deep_merge_non_dict_overwrites_dict():
    base = {"a": {"x": 1}}
    override = {"a": 42}  # valor escalar reemplaza al dict
    out = deep_merge(base, override)
    assert out["a"] == 42


def test_deep_merge_dict_overwrites_scalar():
    base = {"a": 42}
    override = {"a": {"x": 1}}
    out = deep_merge(base, override)
    assert out["a"] == {"x": 1}


def test_deep_merge_with_none_override():
    base = {"a": 1}
    out = deep_merge(base, None)
    assert out == {"a": 1}


def test_deep_merge_nested_levels():
    base = {"a": {"b": {"c": 1, "d": 2}}, "k": 0}
    override = {"a": {"b": {"c": 7}, "e": 9}}
    out = deep_merge(base, override)
    assert out == {"a": {"b": {"c": 7, "d": 2}, "e": 9}, "k": 0}


# ---------- load_tenant_profile tests ----------

def test_load_tenant_profile_happy_path(tmp_path: Path):
    profiles = tmp_path / "profiles"
    (profiles / "clients").mkdir(parents=True)

    base = {
        "defaults": {
            "paths": {"data": "data.csv", "prompts": {"system": "sys.txt"}},
            "model": {"name": "gpt-4o-mini", "temp": 0.6},
            "flags": {"a": True, "b": False},
        }
    }
    tenant = {
        "store": {"name": "Farmacia Sansaloni", "locale": "es-ES"},
        "overrides": {
            "model": {"temp": 0.3},  # override puntual
            "paths": {"prompts": {"compose": "compose.txt"}},  # merge profundo
            "flags": {"b": True, "c": True},  # extiende flags
        },
    }

    ydump(profiles / "base.yaml", base)
    ydump(profiles / "clients" / "farmacia_sansaloni.yaml", tenant)

    cfg = load_tenant_profile(profiles, "farmacia_sansaloni")

    # defaults + overrides (deep merge)
    assert cfg["paths"]["data"] == "data.csv"
    assert cfg["paths"]["prompts"]["system"] == "sys.txt"
    assert cfg["paths"]["prompts"]["compose"] == "compose.txt"  # agregado por override
    assert cfg["model"]["name"] == "gpt-4o-mini"
    assert cfg["model"]["temp"] == 0.3  # override aplicado
    # flags combinados
    assert cfg["flags"] == {"a": True, "b": True, "c": True}
    # store copiado tal cual del tenant
    assert cfg["store"] == {"name": "Farmacia Sansaloni", "locale": "es-ES"}


def test_load_tenant_profile_missing_tenant_raises(tmp_path: Path):
    profiles = tmp_path / "profiles"
    (profiles / "clients").mkdir(parents=True)
    ydump(profiles / "base.yaml", {"defaults": {}})

    with pytest.raises(FileNotFoundError):
        load_tenant_profile(profiles, "no_such_tenant")


def test_load_tenant_profile_empty_files(tmp_path: Path):
    profiles = tmp_path / "profiles"
    (profiles / "clients").mkdir(parents=True)

    # base vacío → defaults = {}
    ydump(profiles / "base.yaml", {})
    # tenant sin overrides ni store explícitos
    ydump(profiles / "clients" / "foo.yaml", {"overrides": {}, "store": {"name": "Foo"}})

    cfg = load_tenant_profile(profiles, "foo")
    assert cfg.get("store", {}).get("name") == "Foo"
    # sin defaults ni overrides, cfg debe ser mínimo
    assert cfg.get("paths") is None
    assert cfg.get("model") is None


def test_load_tenant_profile_override_replaces_scalar(tmp_path: Path):
    profiles = tmp_path / "profiles"
    (profiles / "clients").mkdir(parents=True)

    base = {"defaults": {"model": "gpt-3.5"}}
    tenant = {"store": {"name": "X"}, "overrides": {"model": {"name": "gpt-4o", "temp": 0.2}}}
    ydump(profiles / "base.yaml", base)
    ydump(profiles / "clients" / "x.yaml", tenant)

    cfg = load_tenant_profile(profiles, "x")
    assert cfg["model"] == {"name": "gpt-4o", "temp": 0.2}


def test_load_tenant_profile_deep_merge_multiple_levels(tmp_path: Path):
    profiles = tmp_path / "profiles"
    (profiles / "clients").mkdir(parents=True)

    base = {"defaults": {"paths": {"prompts": {"system": "sys.txt", "compose": "c1.txt"}}}}
    tenant = {"store": {"name": "Y"}, "overrides": {"paths": {"prompts": {"compose": "c2.txt", "greeting": "g.txt"}}}}
    ydump(profiles / "base.yaml", base)
    ydump(profiles / "clients" / "y.yaml", tenant)

    cfg = load_tenant_profile(profiles, "y")
    assert cfg["paths"]["prompts"]["system"] == "sys.txt"
    assert cfg["paths"]["prompts"]["compose"] == "c2.txt"   # override
    assert cfg["paths"]["prompts"]["greeting"] == "g.txt"   # añadido


def test_load_tenant_profile_tenant_id_with_hyphen(tmp_path: Path):
    profiles = tmp_path / "profiles"
    (profiles / "clients").mkdir(parents=True)
    ydump(profiles / "base.yaml", {"defaults": {"flags": {"x": True}}})
    tenant_id = "derma-care-barcelona"
    ydump(profiles / "clients" / f"{tenant_id}.yaml", {"store": {"name": "DermaCare BCN"}, "overrides": {"flags": {"y": 1}}})

    cfg = load_tenant_profile(profiles, tenant_id)
    assert cfg["store"]["name"] == "DermaCare BCN"
    assert cfg["flags"] == {"x": True, "y": 1}
