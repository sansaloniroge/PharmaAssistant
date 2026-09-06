from __future__ import annotations
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Tuple
import numpy as np

# Same default convention as app/profile_resolver.py's INDEX_DIR
# (repo_root/storage/<tenant_id>/index) -- this reads the real cache
# app/index_cache.py builds for the live PharmaAssistant class, so /readyz
# and /tenants/{id}/index/status reflect what /greet and /answer are
# actually using, not a separate, disconnected index.
STORAGE_BASE = Path(os.getenv("STORAGE_BASE", "storage"))

class IndexNotFound(Exception):
    pass

@lru_cache(maxsize=64)
def load_index(tenant_id: str) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Carga embeddings.npy y meta.json del índice real de un tenant.
    Devuelve (embeddings [N, D], meta {signature, embedding_model, dim, count, has_faiss}).
    """
    tdir = STORAGE_BASE / tenant_id / "index"
    emb = tdir / "embeddings.npy"
    meta_path = tdir / "meta.json"

    if not emb.exists() or not meta_path.exists():
        raise IndexNotFound(f"Index files not found for tenant {tenant_id} in {tdir}")

    embeds = np.load(emb)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("count") != embeds.shape[0] or meta.get("dim") != embeds.shape[1]:
        raise ValueError(
            f"Mismatch for tenant {tenant_id}: embeddings shape {embeds.shape} "
            f"vs meta count={meta.get('count')} dim={meta.get('dim')}"
        )

    return embeds, meta

def index_status(tenant_id: str) -> Dict[str, Any]:
    try:
        embeds, meta = load_index(tenant_id)
        return {
            "tenant_id": tenant_id,
            "exists": True,
            "count": int(embeds.shape[0]),
            "dim": int(embeds.shape[1]),
            "bytes": int(embeds.nbytes),
            "embedding_model": meta.get("embedding_model"),
            "path": str((STORAGE_BASE / tenant_id / "index").resolve()),
        }
    except Exception as e:
        return {
            "tenant_id": tenant_id,
            "exists": False,
            "error": str(e),
            "path": str((STORAGE_BASE / tenant_id / "index").resolve()),
        }
