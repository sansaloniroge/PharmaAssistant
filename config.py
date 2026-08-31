from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

# Loads & deep-merges base + client profile
from app.profile_loader import load_tenant_profile  # expects profiles/base.yaml + profiles/clients/<TENANT_ID>.yaml

BASE = Path(__file__).parent.resolve()
PROFILES_DIR = BASE / "profiles"

# Choose tenant by env var (e.g., TENANT_ID=farmacia_carmen_sanjuan)
TENANT_ID = os.getenv("TENANT_ID", "farmacia_carmen_sanjuan")

@dataclass
class RuntimeConfig:
    # Store info
    STORE_NAME: str
    # Models / params
    EMBEDDING_MODEL: str
    CHAT_MODEL: str
    TOP_K: int
    TEMPERATURE: float
    # Paths (resolved to absolute Paths)
    DATA_PATH: Path
    SYSTEM_PROMPT_PATH: Path
    FEWSHOT_PATH: Path
    COMPOSE_PROMPT_PATH: Path
    GREETING_PROMPT_PATH: Path
    NO_MATCH_PROMPT_PATH: Path
    SCHEMA_MAP_PATH: Path
    PRICE_PATTERNS_PATH: Path
    CATEGORY_PATTERNS_PATH: Path
    SKIN_TYPES_PATH: Path
    MEDICAL_TERMS_PATH: Path
    # Storage per tenant (for FAISS, caches, etc.)
    INDEX_DIR: Path

    def validate_paths(self) -> None:
        """Ensure required files/folders exist; create storage dirs if missing."""
        required_files = [
            self.DATA_PATH,
            self.SYSTEM_PROMPT_PATH,
            self.FEWSHOT_PATH,
            self.COMPOSE_PROMPT_PATH,
            self.GREETING_PROMPT_PATH,
            self.SCHEMA_MAP_PATH,
            self.PRICE_PATTERNS_PATH,
            self.CATEGORY_PATTERNS_PATH,
            self.SKIN_TYPES_PATH,
            self.MEDICAL_TERMS_PATH,
        ]
        for p in required_files:
            if not p.exists():
                raise FileNotFoundError(f"Required file not found: {p}")
        self.INDEX_DIR.mkdir(parents=True, exist_ok=True)


def _R(rel: str) -> Path:
    """Resolve a repo-relative path to an absolute Path."""
    return (BASE / rel).resolve()


def load_runtime_config() -> RuntimeConfig:
    """
    Load base defaults + client overrides from profiles/,
    then resolve repo-relative paths into absolute Paths.
    """
    profile = load_tenant_profile(PROFILES_DIR, TENANT_ID)

    # Required path keys in base.yaml defaults (and possibly overridden per client)
    paths = profile["paths"]
    models = profile["models"]

    store_name = profile.get("store", {}).get("name", "Your Pharmacy")
    tenant_id = profile.get("store", {}).get("id", TENANT_ID)

    cfg = RuntimeConfig(
        STORE_NAME=store_name,
        EMBEDDING_MODEL=models["embedding"],
        CHAT_MODEL=models["chat"],
        TOP_K=int(profile.get("top_k", 5)),
        TEMPERATURE=float(profile.get("temperature", 0.6)),
        DATA_PATH=_R(paths["data_csv"]),
        SYSTEM_PROMPT_PATH=_R(paths["system_prompt"]),
        FEWSHOT_PATH=_R(paths.get("few_shot", "data/prompts/few_shot_prompt.yaml")),
        COMPOSE_PROMPT_PATH=_R(paths["compose_prompt"]),
        NO_MATCH_PROMPT_PATH=_R(paths["no_match_prompt"]),
        GREETING_PROMPT_PATH=_R(paths["greeting_prompt"]),
        SCHEMA_MAP_PATH=_R(paths["schema_map"]),
        PRICE_PATTERNS_PATH=_R(paths["price_patterns"]),
        CATEGORY_PATTERNS_PATH=_R(paths["category_patterns"]),
        SKIN_TYPES_PATH=_R(paths["skin_types"]),
        MEDICAL_TERMS_PATH=_R(paths["medical_terms"]),
        INDEX_DIR=(BASE / "storage" / "indexes" / tenant_id).resolve(),
    )

    return cfg

# Expose a CONFIG object (so the rest of your app keeps the same API)
CONFIG = load_runtime_config()
