#!/usr/bin/env python3
# scripts/validate_patterns.py
import sys, yaml
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
FILES: List[Path] = [
    ROOT / "data" / "patterns" / "schema_map.yaml",
    ROOT / "data" / "patterns" / "price_patterns.yaml",
    ROOT / "data" / "patterns" / "category_patterns.yaml",
    ROOT / "data" / "patterns" / "skin_types.yaml",
    ROOT / "data" / "patterns" / "medical_terms.yaml",
]

def load(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    errors = []
    for p in FILES:
        if not p.exists():
            errors.append(f"Falta {p}")
            continue
        try:
            doc = load(p)
        except Exception as e:
            errors.append(f"YAML inválido {p}: {e}")
            continue
        if not isinstance(doc, dict) or not doc:
            errors.append(f"{p} vacío o no es un mapa YAML")

        if "category_patterns.yaml" in str(p):
            cats = (doc or {}).get("categories")
            if cats is not None and (not isinstance(cats, dict) or not cats):
                errors.append(f"{p} → 'categories' debe ser dict no vacío")

    if errors:
        print("ERRORS:", *errors, sep="\n- ", file=sys.stderr)
        sys.exit(2)
    print("OK: YAML de patrones válidos")
    sys.exit(0)

if __name__ == "__main__":
    main()
