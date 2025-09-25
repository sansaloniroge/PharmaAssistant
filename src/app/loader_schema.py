from pathlib import Path
import yaml
from typing import Mapping, Sequence
import pandas as pd

def load_schema_map(path: Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("canonical_fields", {})

def apply_schema_map(
    df: pd.DataFrame, canonical_map: Mapping[str, Sequence[str]]
) -> pd.DataFrame:
    rename_dict: dict[str, str] = {}
    for canonical, candidates in canonical_map.items():
        for c in candidates:
            if c in df.columns and canonical not in df.columns:
                rename_dict[c] = canonical
                break
    return df.rename(columns=rename_dict)
