import sys
import yaml
from pathlib import Path
from typing import List, Dict

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles" / "clients"
CLIENTS_DIR = ROOT / "data" / "clients"

REQUIRED_PROMPTS = [
    "compose_prompt.txt",
    "few_shot_prompt.txt",
    "greeting_prompt.txt",
    "no_match_prompt.txt",
    "system_prompt.txt",
]

def load_yaml(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main():
    errors: List[str] = []
    if not PROFILES_DIR.exists():
        print(f"No existe {PROFILES_DIR}", file=sys.stderr)
        sys.exit(2)

    for yml in sorted(PROFILES_DIR.glob("*.yaml")):
        client_id = yml.stem
        prof = load_yaml(yml)

        # Claves básicas recomendadas
        for key in ("id", "name", "locale"):
            if key not in prof:
                errors.append(f"{yml}: falta clave '{key}'")

        # CSV
        csv = CLIENTS_DIR / client_id / "products_catalog.csv"
        if not csv.exists():
            errors.append(f"{client_id}: falta {csv}")

        # Prompts
        prompts_dir = CLIENTS_DIR / client_id / "prompts"
        if not prompts_dir.exists():
            errors.append(f"{client_id}: falta carpeta {prompts_dir}")
        else:
            for f in REQUIRED_PROMPTS:
                if not (prompts_dir / f).exists():
                    errors.append(f"{client_id}: falta prompt {prompts_dir / f}")

        # Overrides opcionales de patterns
        patt_dir = CLIENTS_DIR / client_id / "patterns"
        if patt_dir.exists():
            for fname in ("category_patterns.yaml", "price_patterns.yaml", "schema_map.yaml"):
                if not (patt_dir / fname).exists():
                    errors.append(f"{client_id}: carpeta patterns/ existe pero falta {fname}")

    if errors:
        print("ERRORS:", *errors, sep="\n- ", file=sys.stderr)
        sys.exit(3)
    print("OK: perfiles y assets por cliente coherentes")
    sys.exit(0)

if __name__ == "__main__":
    main()
