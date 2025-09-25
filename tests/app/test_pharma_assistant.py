import sys
import types
import unicodedata
import numpy as np
import pytest
from app.pharma_assistant import _norm, Settings, VectorIndex, PharmaAssistant

# Provide a minimal stub for the 'openai' package required at import time
class _DummyClient:
    def __init__(self, *args, **kwargs): pass

class _DummyOpenAI:
    def __init__(self, *args, **kwargs): pass

OpenAI = _DummyOpenAI

stub_mod = types.ModuleType("openai")
setattr(stub_mod, "OpenAI", OpenAI)
sys.modules.setdefault("openai", stub_mod)

# Stub de 'unidecode'
ud_mod = types.ModuleType("unidecode")
def _ascii_unidecode(s):
    if s is None:
        return ""
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")

setattr(ud_mod, "unidecode", _ascii_unidecode)
sys.modules.setdefault("unidecode", ud_mod)

def test_norm_handles_none_nan_and_accents():
    assert _norm(None) == ""
    assert _norm(float('nan')) == ""
    # accents removed, trimmed
    assert _norm("  Crème  ") == "Creme"

def test_vectorindex_search_returns_topk():
    # Build simple embedding matrix: 3 vectors in 2D
    embs = np.array([
        [1.0, 0.0],   # v0
        [0.0, 1.0],   # v1
        [0.9, 0.1],   # v2 (close to v0)
    ], dtype=np.float32)
    index = VectorIndex(embs)
    # Query near v0
    q = np.array([[1.0, 0.0]], dtype=np.float32)
    idxs, sims = index.search(q, k=2)
    # Ensure two unique indices from top-2
    assert len(set(idxs[:2])) == 2
    # Ensure sims are descending and within [0,1]
    assert 1.0 >= sims[0] >= sims[1] >= 0.0

def test_settings_from_config_missing_fields_raise():
    # Provide an object missing a required field (e.g., DATA_PATH)
    import types
    cfg = types.SimpleNamespace(
        INDEX_DIR="/tmp",
        STORE_NAME="store",
        GREETING_PROMPT_PATH="/tmp/greet.txt",
        SYSTEM_PROMPT_PATH="/tmp/system.txt",
        FEWSHOT_PATH="/tmp/few.yaml",
        COMPOSE_PROMPT_PATH="/tmp/compose.txt",
        NO_MATCH_PROMPT_PATH="/tmp/nomatch.txt",
        PRICE_PATTERNS_PATH="/tmp/price.yaml",
        CATEGORY_PATTERNS_PATH="/tmp/cat.yaml",
        SKIN_TYPES_PATH="/tmp/skin.txt",
        SCHEMA_MAP_PATH="/tmp/schema.yaml",
        MEDICAL_TERMS_PATH="/tmp/med.txt",
    )
    with pytest.raises(AttributeError):
        Settings.from_config.__func__(cfg)  # call as unbound to pass cfg

def test_pharmaassistant_parse_methods_delegate():
    # Instantiate without running __init__
    pa = PharmaAssistant.__new__(PharmaAssistant)

    # Stubs
    class Stub:
        def __init__(self, ret):
            self._ret = ret
        def parse(self, msg):
            # verify message is passed through
            assert isinstance(msg, str)
            return self._ret

    pa.price_parser = Stub((10.0, 20.0))
    pa.category_parser = Stub(["serum", "retinol"])
    pa.skin_type_parser = Stub("oily")

    assert pa.parse_price("between 10 and 20€") == (10.0, 20.0)
    assert pa.parse_category_hints("quiero un serum con retinol") == ["serum", "retinol"]
    assert pa.parse_skin_type("piel grasa") == "oily"
