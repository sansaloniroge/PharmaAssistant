"""
index_cache.py
--------------
Tiny utilities to persist and load embedding indexes per tenant.

What it stores (under INDEX_DIR):
- meta.json       : signature, dims, counts, model, flags
- embeddings.npy  : normalized float32 matrix (N, D)
- faiss.index     : optional; only if FAISS is available

This module is intentionally independent of your PharmaAssistant classes to avoid circular imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
import hashlib
import json

import numpy as np

# Try importing FAISS; optional
try:
    import faiss  # type: ignore
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False


# ---------- Hashing & signatures ----------

def _hash_bytes(b: bytes) -> str:
    """SHA-256 helper."""
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()


def catalog_signature(
    retrieval_texts: np.ndarray | list[str],
    embedding_model: str,
    pipeline_version: str = "retriever_v1",
) -> str:
    """
    Build a stable signature for the current catalog+pipeline.
    Use retrieval_texts (after schema mapping + normalization) so changes invalidate the cache.
    Also include the embedding model name and a pipeline version you can bump when logic changes.
    """
    if not isinstance(retrieval_texts, (list, tuple, np.ndarray)):
        raise TypeError("retrieval_texts must be a list/array of strings")
    joined = "\n".join(map(str, retrieval_texts)).encode("utf-8")
    base = _hash_bytes(joined)
    meta = f"{base}|{embedding_model}|{pipeline_version}".encode("utf-8")
    return _hash_bytes(meta)


# ---------- Paths ----------

def _paths(index_dir: Path) -> Dict[str, Path]:
    """Return canonical file paths for a given index directory."""
    return {
        "meta": index_dir / "meta.json",
        "embs": index_dir / "embeddings.npy",
        "faiss": index_dir / "faiss.index",
    }


# ---------- Save / Load ----------

def save_index_cache(
    index_dir: Path,
    signature: str,
    embeddings_norm_f32: np.ndarray,
    embedding_model: str,
    faiss_index: "faiss.Index" | None = None,
) -> None:
    """
    Persist the normalized embeddings and FAISS index (if available).
    - embeddings_norm_f32 must be float32 and L2-normalized row-wise.
    """
    index_dir.mkdir(parents=True, exist_ok=True)
    p = _paths(index_dir)

    # Save embeddings (float32, normalized)
    if not isinstance(embeddings_norm_f32, np.ndarray):
        raise TypeError("embeddings_norm_f32 must be a numpy array")
    if embeddings_norm_f32.dtype != np.float32:
        raise TypeError("embeddings_norm_f32 must be float32")
    np.save(p["embs"], embeddings_norm_f32)

    # Save metadata
    meta = {
        "signature": signature,
        "embedding_model": embedding_model,
        "dim": int(embeddings_norm_f32.shape[1]),
        "count": int(embeddings_norm_f32.shape[0]),
        "has_faiss": bool(_HAS_FAISS and faiss_index is not None),
    }
    p["meta"].write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Save FAISS index if provided and FAISS available
    if _HAS_FAISS and faiss_index is not None:
        faiss.write_index(faiss_index, str(p["faiss"]))


def load_index_cache(
    index_dir: Path,
    signature: str,
) -> Optional[Tuple[np.ndarray, "faiss.Index" | None]]:
    """
    Load cached embeddings (and FAISS index if present) if the signature matches.
    Returns (embeddings_norm_f32, faiss_index_or_none) or None if unavailable/mismatch.
    """
    p = _paths(index_dir)
    if not p["meta"].exists() or not p["embs"].exists():
        return None

    try:
        meta = json.loads(p["meta"].read_text(encoding="utf-8"))
        if meta.get("signature") != signature:
            return None

        embs = np.load(p["embs"])
        faiss_index = None
        if _HAS_FAISS and p["faiss"].exists():
            try:
                faiss_index = faiss.read_index(str(p["faiss"]))
            except Exception:
                # Corrupt / incompatible FAISS file → just skip (NumPy path still works)
                faiss_index = None

        return embs, faiss_index
    except Exception:
        return None
