import os
import sys
import types
from pathlib import Path

# Ensure the src/ layout is importable in tests
THIS_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(THIS_DIR, ".."))
SRC_DIR = os.path.join(ROOT_DIR, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Provide a dummy "config" module so "import config as user_config" works
if "config" not in sys.modules:
    config_mod = types.ModuleType("config")
    # Minimal CONFIG object with required attributes used by Settings.from_config
    CONFIG = types.SimpleNamespace(
        DATA_PATH=Path("tests/data"),
        INDEX_DIR=Path("tests/.index"),
        STORE_NAME="test-store",
        GREETING_PROMPT_PATH=Path("tests/prompts/greeting.txt"),
        SYSTEM_PROMPT_PATH=Path("tests/prompts/system.txt"),
        FEWSHOT_PATH=Path("tests/prompts/fewshot.jsonl"),
        COMPOSE_PROMPT_PATH=Path("tests/prompts/compose.txt"),
        NO_MATCH_PROMPT_PATH=Path("tests/prompts/no_match.txt"),
        PRICE_PATTERNS_PATH=Path("tests/patterns/price.yaml"),
        CATEGORY_PATTERNS_PATH=Path("tests/patterns/categories.yaml"),
        SKIN_TYPES_PATH=Path("tests/patterns/skin_types.yaml"),
        SCHEMA_MAP_PATH=Path("tests/patterns/schema_map.yaml"),
        MEDICAL_TERMS_PATH=Path("tests/patterns/medical_terms.txt"),
        # Optional defaults used in Settings
        EMBEDDING_MODEL="text-embedding-3-small",
        CHAT_MODEL="gpt-4o-mini",
        TOP_K=5,
        TEMPERATURE=0.6,
    )
    setattr(config_mod, "CONFIG", CONFIG)
    sys.modules["config"] = config_mod
