import yaml
from pathlib import Path
from copy import deepcopy

def deep_merge(base: dict, override: dict) -> dict:
    result = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def load_tenant_profile(profiles_dir: Path, tenant_id: str) -> dict:
    base = yaml.safe_load((profiles_dir / "base.yaml").read_text(encoding="utf-8")) or {}
    tenant_path = profiles_dir / "clients" / f"{tenant_id}.yaml"
    if not tenant_path.exists():
        raise FileNotFoundError(f"Profile not found for tenant {tenant_id}")
    tenant = yaml.safe_load(tenant_path.read_text(encoding="utf-8")) or {}
    cfg = deep_merge(base.get("defaults", {}), tenant.get("overrides", {}))
    cfg["store"] = tenant.get("store", {})
    return cfg
