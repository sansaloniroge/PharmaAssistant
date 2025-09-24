import numpy as np
from pathlib import Path
import shutil
import tempfile

from app.index_cache import save_index_cache, load_index_cache, catalog_signature

def test_index_cache_per_tenant_roundtrip():
    tmp = Path(tempfile.mkdtemp(prefix="pa_cache_"))
    try:
        # firma distinta por dataset/modelo
        texts = ["a", "b", "c"]
        sig = catalog_signature(texts, "text-embedding-3-large", "retriever_v1")

        # tenant-specific dir
        index_dir = tmp / "storage" / "client_1" / "index"
        index_dir.mkdir(parents=True, exist_ok=True)

        embs = np.array([[1,0],[0,1],[0.7,0.7]], dtype=np.float32)
        # normalizados (simulamos que ya lo están)
        embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)

        save_index_cache(index_dir, sig, embs, "text-embedding-3-large", faiss_index=None)
        loaded = load_index_cache(index_dir, sig)
        assert loaded is not None
        loaded_embs, loaded_idx = loaded
        assert loaded_idx is None
        assert loaded_embs.shape == embs.shape
        np.testing.assert_allclose(loaded_embs, embs, rtol=1e-5, atol=1e-6)

        # cambiar firma → no debe cargar
        bad = load_index_cache(index_dir, "wrong_signature")
        assert bad is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
