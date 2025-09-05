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
from typing import List, Dict, Any, Optional, Tuple  # For type hints

import numpy as np  # For numeric arrays and vector operations
import pandas as pd  # For CSV parsing
import yaml  # For loading few-shot examples
# --- OpenAI client ---
from openai import OpenAI  # requires: pip install openai
from unidecode import unidecode  # For text normalization
from loader_schema import load_schema_map, apply_schema_map
from app.price_parser import PriceParser

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

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable or default."""
    v = os.getenv(name, default) # Fetch from environment or use default
    return v

# Dataclass to hold settings
@dataclass
class Settings:
    """Configuration settings for the assistant."""
    DATA_PATH: Path  # Path to CSV data file
    SYSTEM_PROMPT_PATH: Path  # Path to system prompt file
    FEWSHOT_PATH: Path  # Path to few-shot examples file
    SCHEMA_MAP_PATH: Path #Path to schema-map file
    PRICE_PATTERNS_PATH: Path #Path to price patterns file
    EMBEDDING_MODEL: str = "text-embedding-3-large"  # Embedding model name
    CHAT_MODEL: str = "gpt-4o-mini"  # Chat model name
    TOP_K: int = 5  # Number of retrieved products to use in answer
    TEMPERATURE: float = 0.6  # Sampling temperature for chat model responses

    @staticmethod
    def from_env() -> "Settings":
        """Load settings from environment variables."""
        cfg = user_config.CONFIG
        # Fail if paths are missing
        required = [
            ("DATA_PATH", getattr(cfg, "DATA_PATH", None)),
            ("SYSTEM_PROMPT_PATH", getattr(cfg, "SYSTEM_PROMPT_PATH", None)),
            ("FEWSHOT_PATH", getattr(cfg, "FEWSHOT_PATH", None)),
            ("SCHEMA_MAP_PATH", getattr(cfg, "SCHEMA_MAP_PATH", None)),
        ]
        for name, val in required:
            if val is None:
                raise AttributeError(f"CONFIG.{name} is required but not set in config.py")
        # Build settings (models/params can have sensible defaults if not provided)
        return Settings(
            DATA_PATH=Path(cfg.DATA_PATH),
            SYSTEM_PROMPT_PATH=Path(cfg.SYSTEM_PROMPT_PATH),
            FEWSHOT_PATH=Path(cfg.FEWSHOT_PATH),
            EMBEDDING_MODEL=getattr(cfg, "EMBEDDING_MODEL", "text-embedding-3-large"),
            CHAT_MODEL=getattr(cfg, "CHAT_MODEL", "gpt-4o-mini"),
            TOP_K=int(getattr(cfg, "TOP_K", 5)),
            TEMPERATURE=float(getattr(cfg, "TEMPERATURE", 0.6)),
        )

def _norm(s: Any) -> str:
    """Normalize string: unidecode, strip, lowercase. None/NaN -> empty string."""
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
        """Search for top-k similar vectors to the query vector."""
        q = query_vec.astype("float32") # Ensure float32 for FAISS compatibility
        q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-12) # Normalize query vector to unit length for cosine similarity
        if self.faiss_index is not None:
            D, I = self.faiss_index.search(q, k) # Use FAISS for fast search if available
            return I[0], D[0] # Return indices and distances of top-k results
        sims = self.mat @ q[0]  # Compute cosine similarities via dot product
        idx = np.argsort(-sims)[:k] # Get indices of top-k highest similarities
        return idx, sims[idx] # Return indices and similarity scores

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
        # Regex pattern to detect medical conditions
        self.medical_pattern = _load_medical_terms(
            getattr(user_config.CONFIG, "MEDICAL_TERMS_PATH",
                    Path("data/medical_terms.yaml")) # Default path if not set in config
        )

        self.settings = settings # Store settings
        api_key = os.getenv("OPENAI_API_KEY") # Read API key from environment
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required in environment") # Fail if API key is missing
        self.client = OpenAI(api_key=api_key) # Initialize OpenAI client
        self.embedder = Embedder(self.client, settings.EMBEDDING_MODEL) # Initialize embedder

        # Load prompts
        self.system_prompt = _load_text(settings.SYSTEM_PROMPT_PATH) # Load system prompt text
        self.few_shot = _load_yaml_list(settings.FEWSHOT_PATH) # Load few-shot examples

        # Load catalog and build index
        self.df = self._load_catalog(settings.DATA_PATH) # Load product catalog from CSV
        self.cards, self.index = self._build_index(self.df) # Build product cards and vector index

        #
        self.price_parser = PriceParser(self.settings.PRICE_PATTERNS_PATH)

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

    def _build_index(self, df: pd.DataFrame):
        texts = df["retrieval_text"].tolist() # Get retrieval texts for embedding
        embs = self.embedder.encode(texts)  # Compute embeddings for all product texts
        index = VectorIndex(embs) # Build vector index from embeddings
        cards: List[Dict[str, Any]] = [] # Prepare product cards for JSON output
        for _, r in df.iterrows(): # Iterate over DataFrame rows to build product cards
            cards.append({"product_name": r.get("product_name",""), "brand": r.get("brand",""), "category": r.get("category",""),
                          "benefits": r.get("benefits","") or r.get("features",""), "key_ingredients": r.get("key_ingredients",""),
                          "skin_types": r.get("skin_types",""), "price_eur": float(r["price_eur"]) if pd.notna(r.get("price_eur")) else None,
                          "short_description": r.get("short_description",""), "contraindications": r.get("contraindications","")})
        return cards, index # Return product cards and vector index

    # Regex for price detection
    PRICE_RANGE = re.compile(r"(?:(?:under|below|menos de|<)\s*(\d{1,4}))|(?:(\d{1,4})\s*(?:-|to|a)\s*(\d{1,4}))|(?:€\s?(\d{1,4}))", re.I)

    @staticmethod
    def parse_price(msg: str) -> Optional[Tuple[float, float]]:
        m = PharmaAssistant.PRICE_RANGE.search(msg)
        if not m:
            return None
        g = [x for x in m.groups() if x]
        try:
            if len(g) == 1:
                hi = float(g[0])
                return (0.0, hi)
            if len(g) >= 2:
                lo = float(g[0]); hi = float(g[1])
                if lo > hi: lo, hi = hi, lo
                return (lo, hi)
        except Exception:
            return None
        return None

    @staticmethod
    def parse_category_hints(msg: str) -> List[str]:
        low = msg.lower()
        mapping = {"cleanser": ["cleanser","wash","gel"], "serum": ["serum","ampoule"],
                   "moisturizer": ["moisturizer","cream","lotion"], "sunscreen": ["sunscreen","spf","sun block","sunblock"],
                   "toner": ["toner","essence"], "exfoliant": ["exfoliant","aha","bha","salicylic","glycolic"]}
        cats = []
        for cat, keys in mapping.items():
            if any(k in low for k in keys):
                cats.append(cat)
        return cats

    @staticmethod
    def parse_skin_type(msg: str) -> Optional[str]:
        low = msg.lower()
        for t in ["dry","oily","combination","combo","sensitive","normal","acne-prone"]:
            if t in low:
                return "combination" if t == "combo" else t
        return None

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
        all_idx, all_scores = self.index.search(qv, k=min(len(self.df), max(top_k*6, 24)))
        mask = set(cand_idx.tolist())
        filtered = [i for i in all_idx.tolist() if i in mask]
        return filtered[:top_k]

    def _compose_cards_json(self, idxs: List[int]) -> str:
        subset = [self.cards[i] for i in idxs]
        return json.dumps(subset, ensure_ascii=False)

    def _fewshot_as_text(self) -> str:
        if not self.few_shot:
            return ""
        parts = []
        for ex in self.few_shot:
            parts.append(f"User: {ex['user']}\nAssistant: {ex['assistant'].strip()}\n")
        return "\n".join(parts) + "\n"

    def answer(self, user_message: str) -> Dict[str, Any]:
        idxs = self.retrieve(user_message)
        cards_json = self._compose_cards_json(idxs)
        few = self._fewshot_as_text()
        add_derm_note = bool(self.MEDICAL_PATTERN.search(user_message))
        compose_prompt = ("Compose a warm, human, skincare-specialist reply to the customer using ONLY these product cards (don't invent products or benefits):\n\n"
                          f"{cards_json}\n\nCustomer message:\n\"{user_message}\"\n\nGuidance:\n"
                          "- Explain why the product(s) fit (benefits, key ingredients) in plain language.\n"
                          "- Mention price only if asked or clearly relevant (e.g., a budget was provided).\n"
                          "- If a routine is requested, propose a simple step order with brief reasoning.\n"
                          "- Keep it warm, clear, and concise.\n"
                          "- If no product clearly fits, say so politely and offer the closest alternatives.\n")
        if add_derm_note:
            compose_prompt += "- Since a medical condition was mentioned, add a gentle note to consult a dermatologist before using products.\n"
        messages = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": compose_prompt}]
        resp = self.client.chat.completions.create(model=self.settings.CHAT_MODEL, messages=messages, temperature=self.settings.TEMPERATURE)
        text = resp.choices[0].message.content.strip()
        sources = [self.cards[i]["product_name"] or f"row {i}" for i in idxs]
        return {"answer": text, "sources": sources}

# CLI for testing
if __name__ == "__main__":
    settings = Settings.from_env_or_defaults()
    assistant = PharmaAssistant(settings)
    print("Loaded products:", len(assistant.df))
    print("Type your question (Ctrl+C to exit)\n")
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
