from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional
import yaml

from app.profile_loader import deep_merge  # ya lo tienes

# Keys de prompts y patterns esperadas
PROMPT_KEYS = [
    "system_prompt",
    "compose_prompt",
    "greeting_prompt",
    "no_match_prompt",
    "few_shot_prompt",
]
PATTERN_KEYS = [
    "category_patterns",
    "price_patterns",
    "schema_map",
    # se mantienen globales por defecto, pero soportamos override si lo pones
    "skin_types",
    "medical_terms",
]


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"YAML not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_profile(profiles_dir: Path, tenant_id: str) -> dict:
    """
    Carga base.yaml + clients/{tenant}.yaml y hace deep-merge:
    result = deep_merge(base.defaults, client.overrides) + client.store
    """
    base = _read_yaml(profiles_dir / "base.yaml")
    client_path = profiles_dir / "clients" / f"{tenant_id}.yaml"
    client = _read_yaml(client_path)

    defaults = (base or {}).get("defaults", {})
    overrides = (client or {}).get("overrides", {})
    store = (client or {}).get("store", {})

    merged = deep_merge(defaults, overrides)
    merged["store"] = store
    merged["version"] = (base or {}).get("version", 1)
    return merged


def _resolve_file(preferred: Path, fallback: Path) -> Path:
    """Si existe el archivo preferido, úsalo; si no, usa el fallback."""
    return preferred if preferred.exists() else fallback


def resolve_paths(
    tenant_id: str,
    repo_root: Path = Path(""),
    data_root: Optional[Path] = None,
    profiles_root: Optional[Path] = None,
) -> Dict[str, Path]:
    """
    Resuelve todas las rutas necesarias aplicando el fallback:
      - prompts: client → general_prompts
      - patterns: client → data/patterns
      - data_csv: client override → clients/{tenant}/products_catalog.csv
    Devuelve un dict con rutas absolutas (Path).
    """
    data_root = data_root or (repo_root / "data")
    profiles_root = profiles_root or (repo_root / "profiles")

    # Lee perfil ya mergeado (defaults + overrides)
    prof = load_profile(profiles_root, tenant_id)
    paths = prof.get("paths", {})  # puede venir de defaults/overrides

    # --- Prompts ---
    client_prompts = data_root / "clients" / tenant_id / "prompts"
    general_prompts = data_root / "general_prompts"

    prompt_paths = {}
    for key in PROMPT_KEYS:
        # de overrides (si existe ruta absoluta/relativa) → si no, estructura estándar
        override = paths.get(key)
        prefer = Path(override) if override else (client_prompts / prompt_filename_for(key))
        fallback = general_prompts / prompt_filename_for(key)
        prompt_paths[key] = _resolve_file(prefer, fallback)

    # --- Patterns ---
    client_patterns = data_root / "clients" / tenant_id / "patterns"
    global_patterns = data_root / "patterns"

    pattern_paths = {}
    for key in PATTERN_KEYS:
        override = paths.get(key)
        prefer = Path(override) if override else (client_patterns / pattern_filename_for(key))
        fallback = global_patterns / pattern_filename_for(key)
        # skin_types y medical_terms típicamente globales, pero permitimos override
        pattern_paths[key] = _resolve_file(prefer, fallback)

    # --- CSV de catálogo ---
    # 1) client override en profile
    # 2) por convención: data/clients/{tenant}/products_catalog.csv
    csv_override = paths.get("data_csv")
    preferred_csv = Path(csv_override) if csv_override else (data_root / "clients" / tenant_id / "products_catalog.csv")
    if not preferred_csv.exists():
        raise FileNotFoundError(
            f"Products catalog not found for tenant '{tenant_id}': {preferred_csv} "
            f"(Set profiles/clients/{tenant_id}.yaml -> overrides.paths.data_csv)"
        )

    # --- INDEX DIR ---
    # Puedes almacenar por cliente para evitar colisiones de caché
    index_dir = Path(paths.get("index_dir") or (repo_root / "storage" / tenant_id / "index"))

    return {
        "DATA_PATH": preferred_csv,
        "INDEX_DIR": index_dir,

        # prompts
        "SYSTEM_PROMPT_PATH": prompt_paths["system_prompt"],
        "COMPOSE_PROMPT_PATH": prompt_paths["compose_prompt"],
        "GREETING_PROMPT_PATH": prompt_paths["greeting_prompt"],
        "NO_MATCH_PROMPT_PATH": prompt_paths["no_match_prompt"],
        "FEWSHOT_PATH": prompt_paths["few_shot_prompt"],

        # patterns / schema
        "SCHEMA_MAP_PATH": pattern_paths["schema_map"],
        "PRICE_PATTERNS_PATH": pattern_paths["price_patterns"],
        "CATEGORY_PATTERNS_PATH": pattern_paths["category_patterns"],
        "SKIN_TYPES_PATH": pattern_paths["skin_types"],
        "MEDICAL_TERMS_PATH": pattern_paths["medical_terms"],
    }


def prompt_filename_for(key: str) -> str:
    mapping = {
        "system_prompt": "system_prompt.txt",
        "compose_prompt": "compose_prompt.txt",
        "greeting_prompt": "greeting_prompt.txt",
        "no_match_prompt": "no_match_prompt.txt",
        "few_shot_prompt": "few_shot_prompt.txt",
    }
    return mapping[key]


def pattern_filename_for(key: str) -> str:
    mapping = {
        "category_patterns": "category_patterns.yaml",
        "price_patterns": "price_patterns.yaml",
        "schema_map": "schema_map.yaml",
        "skin_types": "skin_types.yaml",
        "medical_terms": "medical_terms.yaml",
    }
    return mapping[key]


def resolve_config_namespace(
    tenant_id: str,
    repo_root: Path = Path(""),
    data_root: Optional[Path] = None,
    profiles_root: Optional[Path] = None,
    # overrides “operativos” (modelos, top_k, temp) → toman del perfil
) -> SimpleNamespace:
    """
    Devuelve un SimpleNamespace con todos los campos que Settings.from_config espera.
    Lee top_k, temperature y models.* del perfil (base + cliente).
    """
    # Rutas resueltas
    paths = resolve_paths(tenant_id, repo_root=repo_root, data_root=data_root, profiles_root=profiles_root)

    # Perfil para hiperparámetros
    prof = load_profile(profiles_root or (repo_root / "profiles"), tenant_id)
    models = prof.get("models", {}) or {}
    top_k = int(prof.get("top_k", 5))
    temperature = float(prof.get("temperature", 0.6))

    return SimpleNamespace(
        # rutas
        DATA_PATH=str(paths["DATA_PATH"]),
        INDEX_DIR=str(paths["INDEX_DIR"]),
        GREETING_PROMPT_PATH=str(paths["GREETING_PROMPT_PATH"]),
        SYSTEM_PROMPT_PATH=str(paths["SYSTEM_PROMPT_PATH"]),
        FEWSHOT_PATH=str(paths["FEWSHOT_PATH"]),
        COMPOSE_PROMPT_PATH=str(paths["COMPOSE_PROMPT_PATH"]),
        NO_MATCH_PROMPT_PATH=str(paths["NO_MATCH_PROMPT_PATH"]),
        PRICE_PATTERNS_PATH=str(paths["PRICE_PATTERNS_PATH"]),
        CATEGORY_PATTERNS_PATH=str(paths["CATEGORY_PATTERNS_PATH"]),
        SKIN_TYPES_PATH=str(paths["SKIN_TYPES_PATH"]),
        SCHEMA_MAP_PATH=str(paths["SCHEMA_MAP_PATH"]),
        MEDICAL_TERMS_PATH=str(paths["MEDICAL_TERMS_PATH"]),

        # hiperparámetros
        TOP_K=top_k,
        TEMPERATURE=temperature,

        # modelos (con defaults razonables si faltan)
        EMBEDDING_MODEL=models.get("embedding", "text-embedding-3-large"),
        CHAT_MODEL=models.get("chat", "gpt-4o-mini"),

        # branding básico para prompts (si quieres exponerlo)
        STORE_NAME=prof.get("store", {}).get("name", "Pharmacy"),
    )
