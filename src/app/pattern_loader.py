from pathlib import Path
import yaml
from typing import Dict, List, Optional
from unidecode import unidecode

def load_patterns(path: Path) -> Dict[str, List[str]]:
    """Load pattern mappings (categories, skin types, etc.) from YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Pattern file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Expect structure like { "categories": {...} } or { "skin_types": {...} }
    if not isinstance(data, dict) or not data:
        raise ValueError(f"Invalid pattern file format: {path}")
    # Take the first top-level key
    key = list(data.keys())[0]
    return data[key]

class CategoryParser:
    def __init__(self, path: Path):
        self.mapping = load_patterns(path)

    def parse(self, msg: str) -> List[str]:
        """Return list of matching categories from the message."""
        low = unidecode(msg).lower().strip()
        cats: List[str] = []
        for cat, keywords in self.mapping.items():
            if any(unidecode(k).lower() in low for k in keywords):
                cats.append(cat)
        # Deduplicate while preserving order
        return list(dict.fromkeys(cats))

class SkinTypeParser:
    def __init__(self, path: Path):
        self.mapping = load_patterns(path)

    def parse(self, msg: str) -> Optional[str]:
        """Return canonical skin type if found, else None."""
        low = unidecode(msg).lower().strip()
        for canonical, keywords in self.mapping.items():
            if any(unidecode(k).lower() in low for k in keywords):
                return canonical
        return None
