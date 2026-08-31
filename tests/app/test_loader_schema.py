from pathlib import Path
import pandas as pd
import yaml

from app.loader_schema import load_schema_map, apply_schema_map


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")


def test_load_schema_map_happy_path(tmp_path: Path):
    schema = {
        "canonical_fields": {
            "product_name": ["Product", "Name"],
            "price_eur": ["Price (€)", "Price", "Cost"],
            "brand": ["Brand"],
        }
    }
    p = tmp_path / "schema_map.yaml"
    write_yaml(p, schema)

    result = load_schema_map(p)
    assert result == schema["canonical_fields"]


def test_load_schema_map_missing_key_returns_empty(tmp_path: Path):
    # No "canonical_fields" key present → should return {}
    schema = {"something_else": {"foo": ["bar"]}}
    p = tmp_path / "schema_map.yaml"
    write_yaml(p, schema)

    result = load_schema_map(p)
    assert result == {}


def test_apply_schema_map_basic_rename(tmp_path: Path):
    # Map "Product" -> product_name, "Price (€)" -> price_eur, "Brand" -> brand
    schema = {
        "canonical_fields": {
            "product_name": ["Product", "Name"],
            "price_eur": ["Price (€)", "Price"],
            "brand": ["Brand"],
        }
    }
    p = tmp_path / "schema_map.yaml"
    write_yaml(p, schema)
    canonical_map = load_schema_map(p)

    df = pd.DataFrame(
        {
            "Product": ["A", "B"],
            "Price (€)": [10.0, 20.5],
            "Brand": ["Acme", "Noble"],
        }
    )
    df2 = apply_schema_map(df, canonical_map)

    assert "product_name" in df2.columns
    assert "price_eur" in df2.columns
    assert "brand" in df2.columns
    # Original names should be gone
    assert "Product" not in df2.columns
    assert "Price (€)" not in df2.columns


def test_apply_schema_map_does_not_overwrite_existing_canonical(tmp_path: Path):
    # If canonical already exists, do not rename another candidate into it
    schema = {
        "canonical_fields": {
            "product_name": ["Product", "Name"],
        }
    }
    p = tmp_path / "schema_map.yaml"
    write_yaml(p, schema)
    canonical_map = load_schema_map(p)

    df = pd.DataFrame(
        {
            "product_name": ["Kept"],  # canonical already present
            "Product": ["Ignored"],    # candidate should NOT be renamed now
        }
    )
    df2 = apply_schema_map(df, canonical_map)

    assert "product_name" in df2.columns
    assert "Product" in df2.columns  # remains as-is
    # Value stays under the canonical column
    assert df2.loc[0, "product_name"] == "Kept"


def test_apply_schema_map_partial_rename(tmp_path: Path):
    # Only some columns exist; only those should be renamed
    schema = {
        "canonical_fields": {
            "product_name": ["Product", "Name"],
            "price_eur": ["Price (€)", "Price"],
            "brand": ["Brand"],
            "category": ["Category"],  # not present in DF
        }
    }
    p = tmp_path / "schema_map.yaml"
    write_yaml(p, schema)
    canonical_map = load_schema_map(p)

    df = pd.DataFrame(
        {
            "Name": ["X"],
            "Price": [12.5],
            # "Category" missing on purpose
        }
    )
    df2 = apply_schema_map(df, canonical_map)

    assert set(df2.columns) == {"product_name", "price_eur"}  # only the present ones renamed
    assert df2.loc[0, "product_name"] == "X"
    assert df2.loc[0, "price_eur"] == 12.5


def test_apply_schema_map_idempotent(tmp_path: Path):
    schema = {
        "canonical_fields": {
            "product_name": ["Product"],
            "brand": ["Brand"],
        }
    }
    p = tmp_path / "schema_map.yaml"
    write_yaml(p, schema)
    canonical_map = load_schema_map(p)

    df = pd.DataFrame({"Product": ["A"], "Brand": ["Acme"]})
    df2 = apply_schema_map(df, canonical_map)
    df3 = apply_schema_map(df2, canonical_map)  # run again

    # No further changes after first application
    assert list(df2.columns) == list(df3.columns) == ["product_name", "brand"]
    assert df3.loc[0, "product_name"] == "A"
    assert df3.loc[0, "brand"] == "Acme"
