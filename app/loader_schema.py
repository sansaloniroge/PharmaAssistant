from pathlib import Path
import yaml

def load_schema_map(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("canonical_fields", {})

def apply_schema_map(df, canonical_map: dict):
    rename_dict = {}
    for canonical, candidates in canonical_map.items():
        for c in candidates:
            if c in df.columns and canonical not in df.columns:
                rename_dict[c] = canonical
                break
    return df.rename(columns=rename_dict)
