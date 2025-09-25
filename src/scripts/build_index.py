#!/usr/bin/env python3
# scripts/build_index.py
import argparse
import json
import os
import sys
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Any

import numpy as np
import pandas as pd


# ---------- Embeddings ----------

def _hash_embed(text: str, dim: int = 384) -> np.ndarray:
    """
    Embedding determinista por hash (fallback cuando no hay OPENAI_API_KEY).
    No es semántico, pero sirve para pruebas/local.
    """
    h = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    # estira el hash a 'dim' con repetición
    rep = (dim + len(h) - 1) // len(h)
    vec = (h * rep)[:dim]
    arr = np.frombuffer(vec, dtype=np.uint8).astype("float32")
    arr = (arr - 127.5) / 127.5  # centra
    # normaliza
    norm = np.linalg.norm(arr)
    return (arr / norm) if norm > 0 else arr


def _embed_openai(texts: List[str], model: str, batch_size: int = 100) -> np.ndarray:
    from openai import OpenAI
    client = OpenAI()
    out: List[List[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = client.embeddings.create(model=model, input=batch)
        # Cada embedding es Sequence[float] → convertir explícitamente a list[float]
        out.extend([list(d.embedding) for d in resp.data])
    return np.array(out, dtype="float32")



def embed_texts(texts: List[str], backend: str = "auto", model: str = "text-embedding-3-small") -> np.ndarray:
    """
    backend:
      - "auto": usa OpenAI si OPENAI_API_KEY está presente; si no, hash
      - "openai": fuerza OpenAI (fallará si no hay API key)
      - "hash": fuerza embedding determinista por hash
    """
    if backend == "hash":
        return np.stack([_hash_embed(t) for t in texts])
    if backend == "openai":
        return _embed_openai(texts, model=model)
    # auto
    if os.getenv("OPENAI_API_KEY"):
        return _embed_openai(texts, model=model)
    return np.stack([_hash_embed(t) for t in texts])


# ---------- Utilidades ----------

TEXT_CANDIDATES = {"product", "name", "title", "description", "benefits", "brand", "category", "tags"}

def infer_text_columns(df: pd.DataFrame) -> List[str]:
    cols = []
    lower_map = {c.lower(): c for c in df.columns}
    for c in TEXT_CANDIDATES:
        if c in lower_map:
            cols.append(lower_map[c])
    if cols:
        return cols
    # Fallback: todas las columnas string-like
    return [c for c in df.columns if df[c].dtype == "object"]


def make_corpus(df: pd.DataFrame, text_cols: List[str]) -> List[str]:
    return (df[text_cols].fillna("").astype(str).agg(" - ".join, axis=1)).tolist()


def save_index(out_dir: Path, embeddings: np.ndarray, meta_rows: List[Dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    np.save(out_dir / "embeddings.npy", embeddings)
    (out_dir / "meta.json").write_text(json.dumps(meta_rows, ensure_ascii=False), encoding="utf-8")
    (out_dir / "index_info.json").write_text(
        json.dumps(
            {
                "count": int(embeddings.shape[0]),
                "dim": int(embeddings.shape[1]),
                "bytes": int(embeddings.nbytes),
                "version": "v1",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def build_index(
    catalog: Path,
    out_dir: Path,
    model: str = "text-embedding-3-small",
    backend: str = "auto",
    text_cols: Optional[List[str]] = None,
) -> None:
    df = pd.read_csv(catalog)
    if df.empty:
        print(f"ERROR: catálogo vacío: {catalog}", file=sys.stderr)
        sys.exit(2)
    if text_cols is None:
        text_cols = infer_text_columns(df)
    if not text_cols:
        print("ERROR: no se detectaron columnas de texto; usa --text-cols", file=sys.stderr)
        sys.exit(3)

    corpus = make_corpus(df, text_cols)
    embeds = embed_texts(corpus, backend=backend, model=model)

    if embeds.shape[0] != len(df):
        print("ERROR: mismatch entre embeddings y filas del catálogo", file=sys.stderr)
        sys.exit(4)

    # Meta: conserva todas las columnas tal cual
    rows = df.to_dict(orient="records")
    save_index(out_dir, embeds, rows)
    print(f"OK: {len(df)} productos → {out_dir} (dim={embeds.shape[1]})")


def main():
    ap = argparse.ArgumentParser(description="Construye embeddings e índice para el catálogo de productos.")
    ap.add_argument("--client-id", help="ID del cliente (busca data/clients/<id>/products_catalog.csv y guarda en storage/<id>)")
    ap.add_argument("--catalog", help="Ruta explícita a products_catalog.csv")
    ap.add_argument("--out-dir", help="Directorio de salida (por defecto storage/<client_id>)")
    ap.add_argument("--model", default="text-embedding-3-small", help="Modelo de embeddings (OpenAI)")
    ap.add_argument("--backend", default="auto", choices=["auto", "openai", "hash"], help="Proveedor de embeddings")
    ap.add_argument("--text-cols", help="Lista separada por comas de columnas de texto a usar")
    args = ap.parse_args()

    if not args.client_id and not args.catalog:
        ap.error("Proporciona --client-id o --catalog")

    if args.client_id:
        catalog = Path(f"data/clients/{args.client_id}/products_catalog.csv")
        out_dir = Path(args.out_dir or f"storage/{args.client_id}")
    else:
        catalog = Path(args.catalog)
        if not args.out_dir:
            ap.error("--out-dir es obligatorio cuando usas --catalog")
        out_dir = Path(args.out_dir)

    if not catalog.exists():
        print(f"ERROR: catálogo no encontrado: {catalog}", file=sys.stderr)
        sys.exit(1)

    text_cols = [c.strip() for c in (args.text_cols or "").split(",") if c.strip()] or None
    build_index(catalog=catalog, out_dir=out_dir, model=args.model, backend=args.backend, text_cols=text_cols)


if __name__ == "__main__":
    main()
