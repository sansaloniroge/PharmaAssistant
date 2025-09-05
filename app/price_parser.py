from __future__ import annotations
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import yaml

class PriceParser:
    def __init__(self, yaml_path: Path):
        self.yaml_path = yaml_path
        self._pattern = self._compile_pattern(self._load_yaml(yaml_path))

    @staticmethod
    def _load_yaml(path: Path) -> Dict:
        if not path.exists():
            raise FileNotFoundError(f"Price patterns YAML not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if "price_patterns" not in data:
            raise ValueError("price_patterns key missing in YAML")
        return data

    @staticmethod
    def _compile_pattern(spec: Dict) -> re.Pattern:
        tokens: List[str] = []
        for _, rules in spec["price_patterns"].items():
            under = "|".join(map(re.escape, rules.get("under", []))) or r"(?!x)x"  # never matches if empty
            between = "|".join(map(re.escape, rules.get("between", []))) or r"(?!x)x"
            currency = "|".join(map(re.escape, rules.get("currency", []))) or r"(?!x)x"
            tokens.append(
                rf"(?:"
                rf"(?:(?:{under})\s*(\d{{1,6}}))"                         # group1: under X
                rf"|(?:(\d{{1,6}})\s*(?:{between})\s*(\d{{1,6}}))"        # group2-3: X to Y
                rf"|(?:{currency}\s?(\d{{1,6}}))"                          # group4: € X / $ X
                rf")"
            )
        combined = "|".join(tokens)
        return re.compile(combined, re.I)

    def parse(self, text: str) -> Optional[Tuple[float, float]]:
        """
        Returns (lo, hi) price range or None if no price intent found.
        - 'under 20' -> (0, 20)
        - '10 to 20' / '10-20' / '10 a 20' -> (10, 20)
        - '€ 25' / '$ 25' -> (25, 25) (treat as exact budget)
        """
        m = self._pattern.search(text)
        if not m:
            return None
        g = [x for x in m.groups() if x]
        try:
            if len(g) == 1:               # under X  OR  single currency amount
                val = float(g[0])
                # disambiguate: if the match came from "under/below/menos de" or from currency form
                if re.search(r"under|below|menos de|<", text, re.I):
                    return (0.0, val)
                return (val, val)
            if len(g) >= 2:               # X to Y
                lo, hi = float(g[0]), float(g[1])
                if lo > hi: lo, hi = hi, lo
                return (lo, hi)
        except Exception:
            return None
        return None
