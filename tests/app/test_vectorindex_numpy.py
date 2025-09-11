import numpy as np
import types
import importlib
import sys

# Forzamos que no exista faiss para este test
sys.modules.pop("faiss", None)

from app.pharma_assistant import VectorIndex

def test_vectorindex_numpy_search_cosine():
    embs = np.array([[1,0],[0,1],[1,1]], dtype=np.float32)
    embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)
    idx = VectorIndex(embs)

    q = np.array([[1,0]], dtype=np.float32)
    I, S = idx.search(q, k=2)
    assert list(I) == [0, 2] or list(I) == [0, 2]  # 0 (1,0) más cercano, 2 (1,1) siguiente
    assert S[0] >= S[1] >= 0
