from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Tuple

# Permite redirigir la base por entorno (útil en tests/CI)
QUOTA_BASE_DIR = Path(os.getenv("QUOTA_BASE_DIR", "."))

def _today() -> str:
    # ISO date UTC (YYYY-MM-DD)
    return datetime.now(timezone.utc).date().isoformat()

def _quota_file_for(tenant_id: str) -> Path:
    # Guardamos en storage/{tenant}/quota.json
    return QUOTA_BASE_DIR / "storage" / tenant_id / "quota.json"

def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

def load_quota(tenant_id: str) -> dict:
    f = _quota_file_for(tenant_id)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8")) or {}
    except Exception:
        # Si está corrupto, reseteamos
        return {}

def save_quota(tenant_id: str, data: dict) -> None:
    f = _quota_file_for(tenant_id)
    _ensure_parent(f)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)

def get_usage_today(tenant_id: str) -> int:
    data = load_quota(tenant_id)
    return int(data.get(_today(), 0))

def can_consume(tenant_id: str, daily_limit: int) -> Tuple[bool, int]:
    used = get_usage_today(tenant_id)
    remaining = max(daily_limit - used, 0)
    return (remaining > 0), remaining

def consume(tenant_id: str, daily_limit: int) -> Tuple[int, int]:
    """
    Incrementa el uso de hoy en 1 si hay crédito.
    Devuelve (used, remaining) tras consumir.
    Lanza ValueError si no queda crédito.
    """
    data = load_quota(tenant_id)
    today = _today()
    used = int(data.get(today, 0))
    if used >= daily_limit:
        raise ValueError("quota exceeded")
    used += 1
    data[today] = used
    save_quota(tenant_id, data)
    remaining = max(daily_limit - used, 0)
    return used, remaining
