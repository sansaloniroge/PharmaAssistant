"""
Tests for service/index_loader.py -- previously had zero coverage. Verifies
it reads the *real* cache app/index_cache.py builds for the live
PharmaAssistant class (storage/<tenant>/index/{embeddings.npy, meta.json}),
not a separate, disconnected convention.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from service import index_loader


@pytest.fixture(autouse=True)
def _isolated_storage_base(tmp_path, monkeypatch):
    monkeypatch.setattr(index_loader, "STORAGE_BASE", tmp_path)
    index_loader.load_index.cache_clear()
    yield
    index_loader.load_index.cache_clear()


def _write_real_cache(base: Path, tenant_id: str, count: int = 3, dim: int = 4) -> None:
    """Writes exactly the shape app/index_cache.py's save_index_cache() produces."""
    index_dir = base / tenant_id / "index"
    index_dir.mkdir(parents=True)
    embeds = np.random.rand(count, dim).astype("float32")
    np.save(index_dir / "embeddings.npy", embeds)
    meta = {
        "signature": "abc123",
        "embedding_model": "text-embedding-3-large",
        "dim": dim,
        "count": count,
        "has_faiss": False,
    }
    (index_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_load_index_reads_the_real_pharma_assistant_cache(tmp_path):
    _write_real_cache(tmp_path, "acme", count=5, dim=8)
    embeds, meta = index_loader.load_index("acme")
    assert embeds.shape == (5, 8)
    assert meta["signature"] == "abc123"
    assert meta["embedding_model"] == "text-embedding-3-large"


def test_load_index_raises_index_not_found_when_missing(tmp_path):
    with pytest.raises(index_loader.IndexNotFound):
        index_loader.load_index("nope")


def test_load_index_raises_on_count_dim_mismatch(tmp_path):
    _write_real_cache(tmp_path, "acme", count=5, dim=8)
    # Corrupt the meta to no longer match the embeddings shape.
    meta_path = tmp_path / "acme" / "index" / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta["count"] = 999
    meta_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(ValueError):
        index_loader.load_index("acme")


def test_index_status_reports_exists_true_for_a_real_cache(tmp_path):
    _write_real_cache(tmp_path, "acme", count=5, dim=8)
    status = index_loader.index_status("acme")
    assert status["exists"] is True
    assert status["count"] == 5
    assert status["dim"] == 8
    assert status["embedding_model"] == "text-embedding-3-large"


def test_index_status_reports_exists_false_when_missing(tmp_path):
    status = index_loader.index_status("nope")
    assert status["exists"] is False
    assert "error" in status
