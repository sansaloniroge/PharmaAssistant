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
        Devuelve (lo, hi) a partir de expresiones del tipo:
          - "under 30", "below 30", "< 30"
          - "20 to 50", "50-20" (normaliza el orden)
          - "€30", "€ 30", "30 €", "budget € 30", "budget eur 30"
        Usa las listas de 'under', 'between' y 'currency' del YAML.
        """
        try:
            spec = self._load_yaml(self.yaml_path)
            # Unifica tokens definidos por idioma
            under_terms: List[str] = []
            between_terms: List[str] = []
            currency_terms: List[str] = []
            for _lang, d in (spec.get("price_patterns") or {}).items():
                under_terms.extend(d.get("under", []))
                between_terms.extend(d.get("between", []))
                currency_terms.extend(d.get("currency", []))

            # Construye regex dinámicos
            def _alts(xs: List[str]) -> str:
                return "|".join(re.escape(x) for x in xs if x)

            num = r"(\d+(?:[.,]\d+)?)"
            under_re = re.compile(rf"(?i)(?:{_alts(under_terms)})\s*(?:{_alts(currency_terms)})?\s*{num}")
            between_re = re.compile(rf"(?i){num}\s*(?:{_alts(between_terms)})\s*{num}")
            # moneda antes o después del número (con espacio opcional)
            currency_re = re.compile(rf"(?i)(?:{_alts(currency_terms)})\s*{num}|{num}\s*(?:{_alts(currency_terms)})")

            def to_float(s: str) -> float:
                return float(s.replace(",", "."))

            # 1) Rangos "X to Y"
            m = between_re.search(text)
            if m:
                lo, hi = to_float(m.group(1)), to_float(m.group(2))
                if lo > hi:
                    lo, hi = hi, lo
                return (lo, hi)

            # 2) "under/below/< N"
            m = under_re.search(text)
            if m:
                hi = to_float(m.group(1))
                return (0.0, hi)

            # 3) "€ 30" / "30 €" / "eur 30"
            m = currency_re.search(text)
            if m:
                # El número puede estar en group(1) o group(2) según el lado
                g = m.group(1) if m.group(1) is not None else m.group(2)
                val = to_float(g)
                return (val, val)

        except Exception:
            return None

        return None

