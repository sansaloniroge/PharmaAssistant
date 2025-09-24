import sys
from pathlib import Path
from typing import List
from scripts.build_index import build_index


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "clients"
STORAGE = ROOT / "storage"

def main():
    if not DATA.exists():
        print(f"Directorio no encontrado: {DATA}", file=sys.stderr)
        sys.exit(1)

    clients: List[Path] = [p for p in DATA.iterdir() if p.is_dir()]
    if not clients:
        print("No hay clientes en data/clients", file=sys.stderr)
        sys.exit(2)

    for cdir in clients:
        cid = cdir.name
        catalog = cdir / "products_catalog.csv"
        if not catalog.exists():
            print(f"[skip] {cid}: no products_catalog.csv", file=sys.stderr)
            continue
        out = STORAGE / cid
        print(f"[build] {cid}: {catalog} → {out}")
        build_index(catalog=catalog, out_dir=out, backend="auto", model="text-embedding-3-small")

if __name__ == "__main__":
    main()
