"""
pharma_assistant.py
---------------------------------
Human-like pharmacy skincare assistant with:
- Modular prompt loading (system + few-shot)
- Robust CSV parsing & retrieval text construction
- Hybrid retrieval: metadata prefilters + semantic ranking
- Safety note for medical conditions
- Never invents products; only uses provided product cards
"""
from __future__ import annotations

import json  # For serializing product cards
import os  # For environment variables
import re  # For regex parsing of messages
from dataclasses import dataclass  # For configuration class
from pathlib import Path  # For file path handling
from typing import List, Dict, Any, Optional, Tuple, cast # For type hints
from datetime import datetime # For greeting based on time of day

import numpy as np  # For numeric arrays and vector operations
import pandas as pd  # For CSV parsing
import yaml  # For loading few-shot examples
from dotenv import load_dotenv  # For loading .env files
# --- OpenAI client ---
from openai import OpenAI  # requires: pip install openai
from openai.types.chat import ChatCompletionMessageParam
from unidecode import unidecode  # For text normalization
from app.loader_schema import load_schema_map, apply_schema_map
from app.price_parser import PriceParser
from app.pattern_loader import CategoryParser, SkinTypeParser
from app.index_cache import catalog_signature, load_index_cache, save_index_cache

# Try importing FAISS for vector search; fallback if not available
try:
    import faiss  # type: ignore
    _HAS_FAISS = True # FAISS is available for faster vector search
except Exception:
    _HAS_FAISS = False # FAISS not available; will use numpy for search

# Require config.py and a CONFIG object
import config as user_config
if not hasattr(user_config, "CONFIG"):
    raise RuntimeError("config.py must define a CONFIG object (e.g., DevConstants()/ProdConstants()).")

# Dataclass to hold settings
@dataclass
class Settings:
    """Configuration settings for the assistant."""
    STORE_NAME: str
    DATA_PATH: Path  # Path to CSV data file
    INDEX_DIR: Path # Directory to store/load index cache
    GREETING_PROMPT_PATH: Path  # Path to greeting prompt file
    SYSTEM_PROMPT_PATH: Path  # Path to system prompt file
    FEWSHOT_PATH: Path  # Path to few-shot examples file
    COMPOSE_PROMPT_PATH: Path #Path to compose prompt file
    NO_MATCH_PROMPT_PATH: Path #Path to no-match prompt file
    PRICE_PATTERNS_PATH: Path #Path to price patterns file
    CATEGORY_PATTERNS_PATH: Path #Path to category patterns file
    SKIN_TYPES_PATH: Path #Path to skin types patterns file
    SCHEMA_MAP_PATH: Path #Path to schema-map file
    MEDICAL_TERMS_PATH: Path #Path to medical terms file
    EMBEDDING_MODEL: str = "text-embedding-3-large"  # Embedding model name
    CHAT_MODEL: str = "gpt-4o-mini"  # Chat model name
    TOP_K: int = 5  # Number of retrieved products to use in answer
    TEMPERATURE: float = 0.6  # Sampling temperature for chat model responses

    @staticmethod
    def from_config(cfg: Optional[Any] = None) -> "Settings":
        """Load settings from provided cfg or default user_config.CONFIG"""
        # ⬇⬇⬇ antes: cfg = user_config.CONFIG
        cfg = cfg or user_config.CONFIG

        required = [
            ("DATA_PATH", getattr(cfg, "DATA_PATH", None)),
            ("INDEX_DIR", getattr(cfg, "INDEX_DIR", None)),
            ("STORE_NAME", getattr(cfg, "STORE_NAME", None)),
            ("GREETING_PROMPT_PATH", getattr(cfg, "GREETING_PROMPT_PATH", None)),
            ("SYSTEM_PROMPT_PATH", getattr(cfg, "SYSTEM_PROMPT_PATH", None)),
            ("FEWSHOT_PATH", getattr(cfg, "FEWSHOT_PATH", None)),
            ("COMPOSE_PROMPT_PATH", getattr(cfg, "COMPOSE_PROMPT_PATH", None)),
            ("NO_MATCH_PROMPT_PATH", getattr(cfg, "NO_MATCH_PROMPT_PATH", None)),
            ("PRICE_PATTERNS_PATH", getattr(cfg, "PRICE_PATTERNS_PATH", None)),
            ("CATEGORY_PATTERNS_PATH", getattr(cfg, "CATEGORY_PATTERNS_PATH", None)),
            ("SKIN_TYPES_PATH", getattr(cfg, "SKIN_TYPES_PATH", None)),
            ("SCHEMA_MAP_PATH", getattr(cfg, "SCHEMA_MAP_PATH", None)),
            ("MEDICAL_TERMS_PATH", getattr(cfg, "MEDICAL_TERMS_PATH", None)),
        ]
        for name, val in required:
            if val is None:
                raise AttributeError(f"CONFIG.{name} is required but not set in config.py")

        return Settings(
            DATA_PATH=Path(cfg.DATA_PATH),
            INDEX_DIR=Path(cfg.INDEX_DIR),
            STORE_NAME=str(cfg.STORE_NAME),
            GREETING_PROMPT_PATH=Path(cfg.GREETING_PROMPT_PATH),
            SYSTEM_PROMPT_PATH=Path(cfg.SYSTEM_PROMPT_PATH),
            FEWSHOT_PATH=Path(cfg.FEWSHOT_PATH),
            COMPOSE_PROMPT_PATH=Path(cfg.COMPOSE_PROMPT_PATH),
            NO_MATCH_PROMPT_PATH=Path(cfg.NO_MATCH_PROMPT_PATH),
            PRICE_PATTERNS_PATH=Path(cfg.PRICE_PATTERNS_PATH),
            CATEGORY_PATTERNS_PATH=Path(cfg.CATEGORY_PATTERNS_PATH),
            SKIN_TYPES_PATH=Path(cfg.SKIN_TYPES_PATH),
            SCHEMA_MAP_PATH=Path(cfg.SCHEMA_MAP_PATH),
            MEDICAL_TERMS_PATH=Path(cfg.MEDICAL_TERMS_PATH),
            EMBEDDING_MODEL=getattr(cfg, "EMBEDDING_MODEL", "text-embedding-3-large"),
            CHAT_MODEL=getattr(cfg, "CHAT_MODEL", "gpt-4o-mini"),
            TOP_K=int(getattr(cfg, "TOP_K", 5)),
            TEMPERATURE=float(getattr(cfg, "TEMPERATURE", 0.6)),
        )

def _norm(s: Any) -> str:
    """Normalize string: unidecode + strip. None/NaN -> empty string."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return "" # Handle None or NaN as empty string
    return unidecode(str(s)).strip()

def _load_text(path: Path) -> str:
    """Load text file content."""
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}") # Ensure file exists before reading
    return path.read_text(encoding="utf-8").strip() # Read and return file content

def _load_yaml_list(path: Path) -> List[Dict[str, str]]:
    """Load few-shot examples from YAML file."""
    if not path.exists():
        return [] # Few-shot is optional; return empty if file missing
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or [] # Load YAML content as list of dicts
    out: List[Dict[str, str]] = [] # Validate structure and normalize strings
    for item in data:
        u = _norm(item.get("user", "")) # Normalize user input and assistant response
        a = item.get("assistant", "").strip() # Keep assistant response formatting intact
        if u and a:
            out.append({"user": item["user"], "assistant": a}) # Only include valid pairs in output
    return out

class Embedder:
    """Embedder using OpenAI embeddings API."""
    def __init__(self, client: OpenAI, model: str):
        """Initialize with OpenAI client and model name."""
        self.client = client # OpenAI client instance
        self.model = model # Embedding model name

    def encode(self, texts: List[str]) -> np.ndarray:
        """Get embeddings for a list of texts."""
        resp = self.client.embeddings.create(model=self.model, input=texts) # Call OpenAI embeddings API
        vecs = [np.array(d.embedding, dtype="float32") for d in resp.data] # Extract embeddings from response
        return np.vstack(vecs) # Stack into 2D numpy array (shape: num_texts x embedding_dim)

class VectorIndex:
    """Vector index for efficient similarity search."""
    def __init__(self, embeddings: np.ndarray):
        """Initialize with precomputed embeddings."""
        self.mat = embeddings.astype("float32") # Ensure float32 for FAISS compatibility
        norms = np.linalg.norm(self.mat, axis=1, keepdims=True) + 1e-12 # Avoid division by zero in normalization
        self.mat = self.mat / norms # Normalize embeddings to unit length for cosine similarity
        self.faiss_index = None # FAISS index instance (if available) or None
        if _HAS_FAISS:
            dim = self.mat.shape[1] # Embedding dimension for FAISS index creation
            index = faiss.IndexFlatIP(dim)  # Inner Product index for cosine similarity
            index.add(self.mat) # Add normalized vectors to FAISS index
            self.faiss_index = index # Store FAISS index for later use

    def search(self, query_vec: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        """Search for top-k similar vectors to the query vector. Returns (indexes, sims)."""
        q = query_vec.astype("float32")
        q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12)

        if self.faiss_index is not None:
            # faiss returns (distances, indexes); distances here are cosine sims (we normalized)
            distances, indexes = self.faiss_index.search(q, k)
            return indexes[0], distances[0]

        sims = self.mat @ q[0]              # cosine similarities
        idx = np.argsort(-sims)[:k]
        return idx, sims[idx]


def _load_medical_terms(path: Path) -> re.Pattern:
    """Load medical terms from YAML and compile into regex pattern."""
    if not path.exists():
        raise FileNotFoundError(f"Medical terms file not found: {path}") # Ensure file exists before reading
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {} # Load YAML content
    terms = data.get("medical_terms", []) # Expecting a list of terms under 'medical_terms' key
    escaped = [re.escape(t) for t in terms] # Escape terms for regex safety
    pattern = r"\b(" + "|".join(escaped) + r")\b" # Word boundary to match whole words only
    return re.compile(pattern, re.I) # Case-insensitive matching for medical terms

class PharmaAssistant:
    """Pharmacy skincare assistant using retrieval-augmented generation."""
    def __init__(self, settings: Settings):
        """Initialize assistant with settings, load data, build index, and prepare parsers."""
        self.settings = settings # Store settings
        load_dotenv() # Load environment variables from .env file
        api_key = os.getenv("OPENAI_API_KEY") # Read API key from environment
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required in environment") # Fail if API key is missing
        self.client = cast(Any, OpenAI(api_key=api_key)) # Initialize OpenAI client
        self.embedder = Embedder(self.client, settings.EMBEDDING_MODEL) # Initialize embedder

        # Load prompts
        self.greeting_tpl = _load_text(settings.GREETING_PROMPT_PATH) # Load greeting prompt template
        self.system_prompt = _load_text(settings.SYSTEM_PROMPT_PATH) # Load system prompt text
        self.few_shot = _load_yaml_list(settings.FEWSHOT_PATH) # Load few-shot examples
        self.compose_tpl = _load_text(settings.COMPOSE_PROMPT_PATH) # Load compose prompt template
        for ph in ("{CARDS_JSON}", "{USER_MESSAGE}", "{EXTRA_SAFETY}"):
            if ph not in self.compose_tpl:
                raise ValueError(f"compose template missing placeholder {ph}")
        self.no_match_prompt = _load_text(settings.NO_MATCH_PROMPT_PATH) # Load no-match prompt text

        # Ensure index dir exists before cache ops
        self.settings.INDEX_DIR.mkdir(parents=True, exist_ok=True)

        # Load catalog and build index
        self.df = self._load_catalog(settings.DATA_PATH) # Load product catalog from CSV
        if self.df.empty:
            raise ValueError(f"Catalog is empty at {self.settings.DATA_PATH}")
        self.cards, self.index = self._build_or_load_index(self.df) # Build product cards and vector index

        # Load additional parsers
        self.price_parser = PriceParser(self.settings.PRICE_PATTERNS_PATH)
        self.category_parser = CategoryParser(self.settings.CATEGORY_PATTERNS_PATH)
        self.skin_type_parser = SkinTypeParser(self.settings.SKIN_TYPES_PATH)

        # Load medical terms for safety note
        self.medical_pattern = _load_medical_terms(settings.MEDICAL_TERMS_PATH)

    def _time_of_day(self) -> str:
        h = datetime.now().hour
        if 5 <= h < 12:
            return "morning"
        if 12 <= h < 18:
            return "afternoon"
        if 18 <= h < 23:
            return "evening"
        return "late"

    def _load_catalog(self, csv_path: Path) -> pd.DataFrame:
        # 1) Load CSV
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}") # Ensure CSV file exists
        df = pd.read_csv(csv_path) # Load CSV into DataFrame

        # 2) Apply canonical schema mapping (always defined in config)
        canonical_map = load_schema_map(self.settings.SCHEMA_MAP_PATH) # Load schema mapping from YAML file
        df = apply_schema_map(df, canonical_map) # Rename columns based on schema mapping

        # 3) Normalize strings
        for col in [
            "product_name", "category", "skin_types", "benefits", "features",
            "key_ingredients", "recommended_for", "brand", "size",
            "contraindications", "short_description", "tags"
        ]:
            if col in df.columns:
                df[col] = df[col].map(_norm) # Normalize text columns to lowercase, stripped, unaccented

        # 4) Convert price to float
        if "price_eur" in df.columns:
            df["price_eur"] = pd.to_numeric(df["price_eur"], errors="coerce") # Convert price to numeric, invalid parsing will be set as NaN
        else:
            df["price_eur"] = np.nan # Add price column if missing, filled with NaN

        # 5) Build retrieval text per row
        def build_retrieval_text(r):
            parts = [
                r.get("product_name", ""),
                r.get("brand", ""),
                r.get("category", ""),
                r.get("short_description", ""),
                r.get("benefits", ""),
                r.get("features", ""),
                r.get("key_ingredients", ""),
                r.get("skin_types", ""),
                r.get("recommended_for", ""),
                r.get("tags", ""),
                (f"price {r['price_eur']:.2f}€" if pd.notna(r.get("price_eur")) else "")
            ] # Collect relevant fields for retrieval text
            return " | ".join([p for p in parts if p]) # Join non-empty parts with separator

        df["retrieval_text"] = df.apply(lambda r: build_retrieval_text(r), axis=1) # Create retrieval text column by applying function to each row

        # 6) Validate required canonical fields
        required = ["product_name"] # Minimum required fields for the assistant to function
        missing = [c for c in required if c not in df.columns] # Check for missing required fields
        if missing:
            raise ValueError(f"Missing required canonical fields after schema mapping: {missing}") # Fail if required fields are missing

        return df

    def _build_or_load_index(self, df: pd.DataFrame) -> Tuple[List[Dict[str, Any]], VectorIndex]:
        texts = df["retrieval_text"].tolist()
        sig = catalog_signature(texts, self.settings.EMBEDDING_MODEL, "retriever_v1")

        # Try cache first
        loaded = load_index_cache(self.settings.INDEX_DIR, sig)
        if loaded is not None:
            embs, faiss_idx = loaded
            index = VectorIndex(embs)
            if faiss_idx is not None:
                index.faiss_index = faiss_idx
            # (re)build cards from the latest df (cheap)
            cards: List[Dict[str, Any]] = []
            for _, r in df.iterrows():
                cards.append({
                    "product_name": r.get("product_name", ""),
                    "brand": r.get("brand", ""),
                    "category": r.get("category", ""),
                    "benefits": r.get("benefits", "") or r.get("features", ""),
                    "key_ingredients": r.get("key_ingredients", ""),
                    "skin_types": r.get("skin_types", ""),
                    "price_eur": float(r["price_eur"]) if pd.notna(r.get("price_eur")) else None,
                    "short_description": r.get("short_description", ""),
                    "contraindications": r.get("contraindications", ""),
                })
            return cards, index

        # Build fresh (embed → index → save)
        raw_embs = self.embedder.encode(texts)  # (N, D), float32
        index = VectorIndex(raw_embs)  # normalizes internally → index.mat
        try:
            save_index_cache(
                index_dir=self.settings.INDEX_DIR,
                signature=sig,
                embeddings_norm_f32=index.mat,  # normalized matrix
                embedding_model=self.settings.EMBEDDING_MODEL,
                faiss_index=index.faiss_index,  # may be None
            )
        except Exception:
            # Cache errors are non-fatal; continue with live index
            pass

        # Build cards as usual
        cards = []
        for _, r in df.iterrows():
            cards.append({
                "product_name": r.get("product_name", ""),
                "brand": r.get("brand", ""),
                "category": r.get("category", ""),
                "benefits": r.get("benefits", "") or r.get("features", ""),
                "key_ingredients": r.get("key_ingredients", ""),
                "skin_types": r.get("skin_types", ""),
                "price_eur": float(r["price_eur"]) if pd.notna(r.get("price_eur")) else None,
                "short_description": r.get("short_description", ""),
                "contraindications": r.get("contraindications", ""),
            })
        return cards, index

    def parse_price(self, msg: str) -> Optional[Tuple[float, float]]:
        """Parse price range from user message."""
        return self.price_parser.parse(msg) # Use PriceParser to extract price range

    def parse_category_hints(self, msg: str) -> List[str]:
        """Parse category hints from user message."""
        return self.category_parser.parse(msg)

    def parse_skin_type(self, msg: str) -> Optional[str]:
        """Parse skin type from user message."""
        return self.skin_type_parser.parse(msg)

    def _metadata_prefilter(self, msg: str) -> np.ndarray:
        df = self.df
        keep = np.ones(len(df), dtype=bool)
        pr = self.parse_price(msg)
        if pr is not None:
            lo, hi = pr
            keep &= df["price_eur"].fillna(np.inf).between(lo, hi).values
        cats = self.parse_category_hints(msg)
        if cats and "category" in df.columns:
            keep &= df["category"].isin(cats).values
        return np.where(keep)[0]

    def retrieve(self, message: str, top_k: Optional[int] = None) -> List[int]:
        if top_k is None:
            top_k = self.settings.TOP_K
        cand_idx = self._metadata_prefilter(message)
        if len(cand_idx) == 0:
            cand_idx = np.arange(len(self.df))
        qv = self.embedder.encode([message])
        all_idx, _ = self.index.search(qv, k=min(len(self.df), max(top_k*6, 24)))
        mask = set(cand_idx.tolist())
        filtered = [i for i in all_idx.tolist() if i in mask]
        return filtered[:top_k]

    def _compose_cards_json(self, idxs: List[int]) -> str:
        subset = []
        for i in idxs:
            card = dict(self.cards[i])
            # keep payload lean
            card["key_ingredients"] = (card.get("key_ingredients", "")[:200] + "…") \
                if len(card.get("key_ingredients", "")) > 200 else card.get("key_ingredients", "")
            card["short_description"] = (card.get("short_description", "")[:280] + "…") if len(
                card.get("short_description", "")) > 280 else card.get("short_description", "")
            card["benefits"] = (card.get("benefits", "")[:280] + "…") if len(
                card.get("benefits", "")) > 280 else card.get("benefits", "")
            subset.append(card)
        return json.dumps(subset, ensure_ascii=False)

    def _fewshot_as_text(self) -> str:
        if not self.few_shot:
            return ""
        parts = []
        for ex in self.few_shot:
            parts.append(f"User: {ex['user']}\nAssistant: {ex['assistant'].strip()}\n")
        return "\n".join(parts) + "\n"

    def _chat(self, messages: List[ChatCompletionMessageParam]) -> str:
        for _ in range(2):  # 1 retry
            try:
                resp = self.client.chat.completions.create(
                    model=self.settings.CHAT_MODEL,
                    messages=messages,  # ✅ tipado correcto
                    temperature=self.settings.TEMPERATURE,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception:
                pass
        return ""

    def greet(self) -> str:
        """Generate a natural opening message using the greeting template."""
        seed = self.greeting_tpl.format(
            STORE_NAME=self.settings.STORE_NAME,
            TIME_OF_DAY=self._time_of_day(),
        )
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": seed},
        ]
        text = self._chat(messages)

        # Use the shared retrying chat helper
        text = self._chat(messages)
        if text:
            return text

        # Fallback if API failed or returned empty
        tod = self._time_of_day()
        return (
            f"Hi! Good {tod}. I’m your skincare specialist at {self.settings.STORE_NAME}. "
            "Tell me about your skin (e.g., dry, oily, sensitive) and if you have a budget, "
            "and I’ll suggest the best options."
        )

    def answer(self, user_message: str) -> Dict[str, Any]:
        # 1) Retrieve candidates and serialize cards
        idxs = self.retrieve(user_message)
        if not idxs:
            return {"answer": self.no_match_prompt, "sources": []}

        cards_json = self._compose_cards_json(idxs)

        # 2) Build extra safety note if medical terms are detected
        add_derm_note = bool(self.medical_pattern.search(user_message))
        extra = (
            "- Since a medical condition was mentioned, add a gentle note to consult a dermatologist before using products.\n"
            if add_derm_note else ""
        )

        # 3) Load & render external compose template (strict: must include placeholders)
        tpl = self.compose_tpl

        compose = tpl.format(
            CARDS_JSON=cards_json,
            USER_MESSAGE=user_message,
            EXTRA_SAFETY=extra
        )

        # 4) Build messages (system is preloaded at init for performance)
        few = self._fewshot_as_text()
        if few:
            compose = few + compose
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": compose},
        ]
        text = self._chat(messages)

        # Use the shared retrying chat helper
        text = self._chat(messages)
        sources = [self.cards[i].get("product_name") or f"row {i}" for i in idxs]
        if text:
            return {"answer": text, "sources": sources}
        else:
            return {
                "answer": (
                    "Sorry, I couldn’t generate a reply just now. "
                    "Could you share a bit more about your skin type and any budget? "
                    "I’ll try again right away."
                ),
                "sources": sources,
            }


# CLI for testing
if __name__ == "__main__":
    settings = Settings.from_config()
    assistant = PharmaAssistant(settings)
    print("Loaded products:", len(assistant.df))
    print()
    print("Assistant:\n" + assistant.greet() + "\n")  # <-- new
    print("Type your reply (Ctrl+C to exit)\n")
    try:
        while True:
            msg = input("You: ").strip()
            if not msg:
                continue
            out = assistant.answer(msg)
            print("\nAssistant:\n", out["answer"], "\n", sep="")
            print("Sources:", ", ".join(out["sources"]))
            print()
    except KeyboardInterrupt:
        print("\nBye!")
