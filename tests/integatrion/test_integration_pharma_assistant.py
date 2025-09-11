import sys, types, json, re
import numpy as np
import pytest

# Stubs for external modules
class _DummyOpenAI:
    def __init__(self, *args, **kwargs): pass
openai_mod = types.ModuleType("openai")
openai_mod.OpenAI = _DummyOpenAI
sys.modules.setdefault("openai", openai_mod)

unidecode_mod = types.ModuleType("unidecode")
unidecode_mod.unidecode = lambda s: s
sys.modules.setdefault("unidecode", unidecode_mod)

# Now import the target
from app.pharma_assistant import PharmaAssistant, VectorIndex

class StubEmbedder:
    def __init__(self): self.calls = []
    def encode(self, texts):
        self.calls.append(list(texts))
        # Return 1x2 vector for the query
        return np.array([[0.6, 0.8]], dtype=np.float32)

class StubIndex(VectorIndex):
    def __init__(self, embs):
        super().__init__(embs)
        self._preset = None
    def set_results(self, idxs, sims=None):
        self._preset = (
            np.array(idxs, dtype=np.int64),
            np.ones(len(idxs), dtype=np.float32) if sims is None else np.array(sims, dtype=np.float32)
        )
    def search(self, query_vec, k):
        # Ignore real search and return preset (top-k sliced)
        I, S = self._preset
        return I[:k], S[:k]

def build_min_assistant(top_k=2):
    # Create instance without running __init__
    pa = PharmaAssistant.__new__(PharmaAssistant)
    # Minimal settings
    pa.settings = types.SimpleNamespace(TOP_K=top_k, STORE_NAME="Farmacia Demo")
    # Dataframe & cards
    import pandas as pd
    pa.df = pd.DataFrame([
        {"retrieval_text": "serum con retinol para piel grasa", "product_name": "Serum A", "brand": "MarcaA", "category": "Serum", "benefits": "Antiarrugas", "short_description":"Desc A", "price_eur": 19.9, "skin_types":"oily", "contraindications":""},
        {"retrieval_text": "hidratante ligera para piel sensible", "product_name": "Crema B", "brand": "MarcaB", "category": "Crema", "benefits": "Hidratación", "short_description":"Desc B", "price_eur": 14.5, "skin_types":"sensitive", "contraindications":""},
        {"retrieval_text": "limpiador suave sin fragancia", "product_name": "Cleanser C", "brand": "MarcaC", "category": "Limpieza", "benefits": "Suave", "short_description":"Desc C", "price_eur": 9.5, "skin_types":"all", "contraindications":""},
    ])
    pa.cards = [
        {"product_name":"Serum A","brand":"MarcaA","category":"Serum","benefits":"Antiarrugas","short_description":"Desc A","price_eur":19.9,"skin_types":"oily","contraindications":""},
        {"product_name":"Crema B","brand":"MarcaB","category":"Crema","benefits":"Hidratación","short_description":"Desc B","price_eur":14.5,"skin_types":"sensitive","contraindications":""},
        {"product_name":"Cleanser C","brand":"MarcaC","category":"Limpieza","benefits":"Suave","short_description":"Desc C","price_eur":9.5,"skin_types":"all","contraindications":""},
    ]
    # Embedder + Index
    pa.embedder = StubEmbedder()
    embs = np.array([[1.0,0.0],[0.0,1.0],[0.7,0.7]], dtype=np.float32)
    pa.index = StubIndex(embs)
    pa.index.set_results([0,2,1])  # pretend search ranking

    # Parsers (stubs)
    class Stub:
        def __init__(self, ret): self._ret = ret
        def parse(self, msg): return self._ret
    pa.price_parser = Stub((10.0, 20.0))
    pa.category_parser = Stub(["serum"])
    pa.skin_type_parser = Stub("oily")

    # Medical terms to trigger safety note
    pa.medical_pattern = re.compile(r"(dermatitis|eczema|acne)", re.I)

    # Prompts & templates
    pa.greeting_tpl = "Eres el asistente de {STORE_NAME}. Buenos {TIME_OF_DAY}."
    pa.system_prompt = "Eres un bot de dermo."
    pa.few_shot = [{"user":"Hola","assistant":"¡Hola!"}]
    pa.compose_tpl = (
        "Dados estos productos:\n{CARDS_JSON}\n"
        "Usuario: {USER_MESSAGE}\n"
        "{EXTRA_SAFETY}"
        "Responde en 3 frases."
    )
    pa.no_match_prompt = "No encontré productos."
    # Provide helper methods used inside greet/answer
    def _time_of_day(self): return "días"
    pa._time_of_day = types.MethodType(_time_of_day, pa)

    # Stub chat to return deterministic text (also capture the last messages)
    pa._last_messages = None
    def _chat(self, messages):
        pa._last_messages = messages
        # Simple echo logic for test determinism
        last_user = [m for m in messages if m["role"]=="user"][-1]["content"]
        if last_user.startswith("Eres el asistente"):  # greeting seed
            return "¡Bienvenido/a a Farmacia Demo! ¿En qué puedo ayudarte?"
        return "Recomendación: Serum A y Cleanser C."
    pa._chat = types.MethodType(_chat, pa)

    # Simple metadata prefilter: keep all
    def _metadata_prefilter(self, msg):
        import numpy as np
        return np.arange(len(pa.df))
    pa._metadata_prefilter = types.MethodType(_metadata_prefilter, pa)

    return pa

def test_greet_integration():
    pa = build_min_assistant()
    out = pa.greet()
    assert "Farmacia Demo" in out
    assert "¿En qué puedo ayudarte?" in out
    # ensure system prompt present in messages sent to chat
    assert any(m["role"]=="system" and "dermo" in m["content"] for m in pa._last_messages)

def test_answer_integration_with_sources_and_safety_note():
    pa = build_min_assistant(top_k=2)
    user = "Busco algo para mi dermatitis y piel grasa"
    result = pa.answer(user)
    assert "Recomendación" in result["answer"]
    # top_k=2 -> expect two sources
    assert result["sources"] == ["Serum A", "Cleanser C"]
    # ensure compose template filled with cards JSON that includes product names
    assert any("Serum A" in m["content"] for m in pa._last_messages if m["role"]=="user")
    # since 'dermatitis' mentioned, EXTRA_SAFETY placeholder should have been included
    assert any("consult a dermatologist" in m["content"] for m in pa._last_messages if m["role"]=="user")

def test_answer_no_match_path():
    pa = build_min_assistant()
    # Force retrieve to return empty
    pa.index.set_results([])
    result = pa.answer("Nada específico")
    assert result["answer"] == "No encontré productos."
    assert result["sources"] == []
