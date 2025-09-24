import argparse
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
PATTERNS_DIR = ROOT / "data" / "patterns"

# Variantes de nombres de columnas esperadas
COL_ALIASES: Dict[str, List[str]] = {
    "product": ["product", "name", "title", "producto", "nombre"],
    "price": ["price", "price (€)", "precio", "precio (€)", "pvp"],
    "category": ["category", "categoría", "category_name"],
    "description": ["description", "descripción", "details"],
}

REQUIRED_LOGICAL = ["product", "price", "category"]  # "description" recomendado, no obligatorio
MIN_DESC_LEN = 10
MAX_NULL_RATIO_REQUIRED = 0.05  # 5% faltantes máximo en columnas requeridas

PRICE_RE = re.compile(r"([0-9]+(?:[.,][0-9]{1,2})?)")

def load_yaml(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def map_columns(df: pd.DataFrame) -> Dict[str, str]:
    lower_map = {c.lower().strip(): c for c in df.columns}
    mapping: Dict[str, str] = {}
    for logical, aliases in COL_ALIASES.items():
        for a in aliases:
            if a.lower() in lower_map:
                mapping[logical] = lower_map[a.lower()]
                break
    return mapping

def parse_price_to_float(x) -> Optional[float]:
    if pd.isna(x):
        return None
    s = str(x)
    m = PRICE_RE.search(s.replace(" ", ""))
    if not m:
        return None
    val = m.group(1).replace(",", ".")
    try:
        f = float(val)
        return round(f, 2)
    except Exception:
        return None

def validate_categories(col: pd.Series) -> Tuple[List[str], List[str]]:
    """Devuelve (categorías_desconocidas, categorias_validas)."""
    cats_yaml = load_yaml(PATTERNS_DIR / "category_patterns.yaml") or {}
    valid = set((cats_yaml.get("categories") or {}).keys())
    if not valid:
        return ([], [])  # no hay referencia → no validar
    unknown = sorted(set(col.dropna().astype(str)) - valid)
    return (unknown, sorted(valid))

def main():
    ap = argparse.ArgumentParser(description="Valida un catálogo CSV de productos.")
    ap.add_argument("--client-id", help="ID del cliente (usa data/clients/<id>/products_catalog.csv)")
    ap.add_argument("--catalog", help="Ruta explícita al CSV")
    args = ap.parse_args()

    if not args.client_id and not args.catalog:
        ap.error("Proporciona --client-id o --catalog")

    if args.client_id:
        catalog = ROOT / "data" / "clients" / args.client_id / "products_catalog.csv"
    else:
        catalog = Path(args.catalog)

    if not catalog.exists():
        print(f"ERROR: no existe el catálogo: {catalog}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(catalog)
    if df.empty:
        print("ERROR: catálogo vacío", file=sys.stderr)
        sys.exit(2)

    # Mapeo de columnas a lógicas
    colmap = map_columns(df)
    missing_logical = [k for k in REQUIRED_LOGICAL if k not in colmap]
    if missing_logical:
        print(f"ERROR: faltan columnas requeridas (alias aceptados {COL_ALIASES}): {missing_logical}", file=sys.stderr)
        print(f"  Columnas presentes: {list(df.columns)}", file=sys.stderr)
        sys.exit(3)

    # Normalización de precios
    price_col = colmap["price"]
    df["_price_norm"] = df[price_col].map(parse_price_to_float)

    # Chequeos básicos
    errors: List[str] = []
    warnings: List[str] = []

    # Faltantes en requeridas
    for logical in REQUIRED_LOGICAL:
        col = colmap[logical]
        null_ratio = df[col].isna().mean()
        if null_ratio > MAX_NULL_RATIO_REQUIRED:
            errors.append(f"Columna '{col}' tiene {null_ratio:.1%} valores nulos (> {MAX_NULL_RATIO_REQUIRED:.0%})")

    # Precios inválidos / negativos / cero
    bad_price = df["_price_norm"].isna().sum()
    neg_price = (df["_price_norm"] < 0).sum()
    zero_price = (df["_price_norm"] == 0).sum()
    if bad_price > 0:
        errors.append(f"{bad_price} filas con precio inválido")
    if neg_price > 0:
        errors.append(f"{neg_price} filas con precio negativo")
    if zero_price > 0:
        warnings.append(f"{zero_price} filas con precio 0.00")

    # Duplicados por producto
    prod_col = colmap["product"]
    dup = df[prod_col].duplicated(keep=False)
    dup_count = int(dup.sum())
    if dup_count > 0:
        sample = df.loc[dup, prod_col].head(10).tolist()
        errors.append(f"{dup_count} productos duplicados (ejemplos: {sample})")

    # Categorías válidas (si hay referencia)
    cat_col = colmap["category"]
    unknown_cats, valid_cats = validate_categories(df[cat_col])
    if valid_cats:
        if unknown_cats:
            warnings.append(f"categorías desconocidas: {unknown_cats}")
    else:
        warnings.append("No se validaron categorías (falta data/patterns/category_patterns.yaml o 'categories')")

    # Descripciones muy cortas (si existe)
    desc_logical = "description"
    if desc_logical in colmap:
        desc_col = colmap[desc_logical]
        too_short = (df[desc_col].fillna("").astype(str).str.len() < MIN_DESC_LEN).sum()
        if too_short > 0:
            warnings.append(f"{too_short} descripciones con menos de {MIN_DESC_LEN} caracteres")

    # Reporte
    summary = {
        "catalog": str(catalog),
        "rows": int(len(df)),
        "columns": list(map(str, df.columns)),
        "mapped_columns": colmap,
        "price_ok": int(len(df) - bad_price),
        "price_bad": int(bad_price),
        "price_neg": int(neg_price),
        "price_zero": int(zero_price),
        "duplicates": int(dup_count),
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Exit codes
    if errors:
        sys.exit(10)
    # Warnings no fallan el proceso
    sys.exit(0)

if __name__ == "__main__":
    main()
