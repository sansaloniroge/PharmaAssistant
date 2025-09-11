import json
from pathlib import Path

import numpy as np
import pytest

from app.index_cache import (
    _hash_bytes,
    catalog_signature,
    save_index_cache,
    load_index_cache,
)

# Try FAISS to branch tests; fine if unavailable
try:
    import faiss  # type: ignore
    HAS_FAISS = True
except Exception:
    HAS_FAISS = False


def test__hash_bytes_stable():
    a = _hash_bytes(b"hello")
    b = _hash_bytes(b"hello")
    c = _hash_bytes(b"world")
    assert a == b and a != c and len(a) == 64  # sha256 hex length


def test_catalog_signature_stability_and_invalidation():
    texts = ["a|b|c", "d|e|f"]
    sig1 = catalog_signature(texts, "text-embedding-3-large", "retriever_v1")
    # same inputs -> same signature
    sig1_again = catalog_signature(list(texts), "text-embedding-3-large", "retriever_v1")
    assert sig1 == sig1_again

    # change model -> different signature
    sig2 = catalog_signature(texts, "text-embedding-3-small", "retriever_v1")
    assert sig2 != sig1

    # change pipeline version -> different signature
    sig3 = catalog_signature(texts, "text-embedding-3-large", "retriever_v2")
    assert sig3 != sig1

    # change retrieval_texts -> different signature
    sig4 = catalog_signature(["x|y|z"], "text-embedding-3-large", "retriever_v1")
    assert sig4 != sig1


def test_save_then_load_cache_without_faiss(tmp_path: Path):
    # Build a small normalized matrix
    embs = np.random.randn(5, 8).astype("float32")
    embs /= np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12

    sig = catalog_signature(["t1", "t2"], "text-embedding-3-large", "retriever_v1")
    save_index_cache(tmp_path, sig, embs, "text-embedding-3-large", faiss_index=None)
    loaded = load_index_cache(tmp_path, sig)
    assert loaded is not None
    embs2, faiss_idx = loaded
    assert np.allclose(embs2, embs)
    assert faiss_idx is None

    # meta sanity
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["signature"] == sig
    assert meta["embedding_model"] == "text-embedding-3-large"
    assert meta["dim"] == embs.shape[1]
    assert meta["count"] == embs.shape[0]


@pytest.mark.skipif(not HAS_FAISS, reason="FAISS not installed")
def test_save_then_load_cache_with_faiss(tmp_path: Path):
    # Normalized matrix
    embs = np.random.randn(7, 16).astype("float32")
    embs /= np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12

    # Build FAISS index
    index = faiss.IndexFlatIP(embs.shape[1])
    index.add(embs)

    sig = catalog_signature(["a", "b", "c"], "text-embedding-3-large", "retriever_v1")
    save_index_cache(tmp_path, sig, embs, "text-embedding-3-large", faiss_index=index)

    loaded = load_index_cache(tmp_path, sig)
    assert loaded is not None
    embs2, faiss_idx = loaded
    assert np.allclose(embs2, embs)
    assert faiss_idx is not None

    # Quick search sanity
    q = embs[0:1]  # already normalized
    D, I = faiss_idx.search(q, 1)
    assert I.shape == (1, 1)
    assert I[0, 0] in range(embs.shape[0])


def test_signature_mismatch_returns_none(tmp_path: Path):
    embs = np.random.randn(3, 4).astype("float32")
    embs /= np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12

    sig_good = catalog_signature(["x"], "m", "v1")
    save_index_cache(tmp_path, sig_good, embs, "m", faiss_index=None)

    sig_bad = catalog_signature(["x"], "m", "v2")  # different version
    assert load_index_cache(tmp_path, sig_bad) is None


def test_dtype_enforcement(tmp_path: Path):
    embs64 = np.random.randn(2, 3).astype("float64")
    sig = catalog_signature(["x"], "m", "v1")
    with pytest.raises(TypeError):
        save_index_cache(tmp_path, sig, embs64, "m", faiss_index=None)

    embs32 = embs64.astype("float32")
    # Should not raise
    save_index_cache(tmp_path, sig, embs32, "m", faiss_index=None)


@pytest.mark.skipif(HAS_FAISS, reason="Only meaningful when FAISS absent")
def test_no_faiss_branch_does_not_write_faiss_file(tmp_path: Path):
    embs = np.random.randn(2, 4).astype("float32")
    embs /= np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12
    sig = catalog_signature(["t"], "m", "v1")
    save_index_cache(tmp_path, sig, embs, "m", faiss_index=None)
    assert not (tmp_path / "faiss.index").exists()


def test_corrupt_faiss_file_is_ignored(tmp_path: Path):
    # Save a valid cache first
    embs = np.random.randn(4, 6).astype("float32")
    embs /= np.linalg.norm(embs, axis=1, keepdims=True) + 1e-12
    sig = catalog_signature(["a"], "m", "v1")
    save_index_cache(tmp_path, sig, embs, "m", faiss_index=None)

    # Write garbage to faiss.index; loader should ignore and still return embeddings
    (tmp_path / "faiss.index").write_bytes(b"not a faiss index")
    loaded = load_index_cache(tmp_path, sig)
    assert loaded is not None
    embs2, faiss_idx = loaded
    assert np.allclose(embs2, embs)
    # If FAISS present, file is corrupt → loader returns None for index
    assert faiss_idx is None
