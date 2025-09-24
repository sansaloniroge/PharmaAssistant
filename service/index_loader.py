# service/index_loader.py
from __future__ import annotations
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Tuple, List, Dict, Any
import numpy as np

STORAGE_BASE = Path(os.getenv("STORAGE_BASE", "storage"))  # opcional: exporta STORAGE_BASE

class IndexNotFound(Exception):
    pass

@lru_cache(maxsize=64)
def load_index(tenant_id: str) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    Carga embeddings.npy y meta.json para un tenant.
    Devuelve (embeddings [N, D], meta [N dicts]).
    """
    tdir = STORAGE_BASE / tenant_id
    emb = tdir / "embeddings.npy"
    meta = tdir / "meta.json"

    if not emb.exists() or not meta.exists():
        raise IndexNotFound(f"Index files not found for tenant {tenant_id} in {tdir}")

    embeds = np.load(emb)
    meta_rows = json.loads(meta.read_text(encoding="utf-8"))
    if embeds.shape[0] != len(meta_rows):
        raise ValueError(f"Mismatch: {embeds.shape[0]} embeddings vs {len(meta_rows)} meta rows")

    return embeds, meta_rows

def index_status(tenant_id: str) -> Dict[str, Any]:
    try:
        embeds, _ = load_index(tenant_id)
        return {
            "tenant_id": tenant_id,
            "exists": True,
            "count": int(embeds.shape[0]),
            "dim": int(embeds.shape[1]),
            "bytes": int(embeds.nbytes),
            "path": str((STORAGE_BASE / tenant_id).resolve()),
        }
    except Exception as e:
        return {
            "tenant_id": tenant_id,
            "exists": False,
            "error": str(e),
            "path": str((STORAGE_BASE / tenant_id).resolve()),
        }
