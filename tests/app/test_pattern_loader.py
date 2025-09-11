from pathlib import Path
import yaml
import pytest

from app.pattern_loader import load_patterns, CategoryParser, SkinTypeParser


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

# ---------- load_patterns ----------

def test_load_patterns_happy_path_categories(tmp_path: Path):
    data = {
        "categories": {
            "moisturizer": ["cream", "loción", "lotion"],
            "cleanser": ["cleanser", "wash", "gel"],
        }
    }
    p = tmp_path / "category_patterns.yaml"
    write_yaml(p, data)

    mapping = load_patterns(p)
    assert isinstance(mapping, dict)
    assert set(mapping.keys()) == {"moisturizer", "cleanser"}
    assert "loción" in mapping["moisturizer"]


def test_load_patterns_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_patterns(tmp_path / "missing.yaml")


def test_load_patterns_invalid_format_raises(tmp_path: Path):
    # Not a dict or empty dict should raise
    p1 = tmp_path / "empty.yaml"
    write_yaml(p1, {})  # empty
    with pytest.raises(ValueError):
        load_patterns(p1)

    p2 = tmp_path / "nondict.yaml"
    p2.write_text(yaml.safe_dump(["not", "a", "dict"]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_patterns(p2)


def test_load_patterns_first_top_level_key_is_used(tmp_path: Path):
    # The loader takes the *first* top-level key
    data = {
        "categories": {"a": ["x"]},
        "skin_types": {"oily": ["oily"]},
    }
    p = tmp_path / "mixed.yaml"
    write_yaml(p, data)
    mapping = load_patterns(p)
    assert mapping == {"a": ["x"]}  # first key ("categories") wins


# ---------- CategoryParser ----------

def test_category_parser_matches_accent_and_case_insensitive(tmp_path: Path):
    data = {
        "categories": {
            "moisturizer": ["cream", "loción", "lotion"],
            "cleanser": ["Cleanser", "WASH", "gel"],  # varied casing
        }
    }
    p = tmp_path / "category_patterns.yaml"
    write_yaml(p, data)

    parser = CategoryParser(p)
    msg = "I need a Locion or maybe a GEL for double cleansing."
    # "Locion" (without accent) should match "loción", and "GEL" should match "gel"
    out = parser.parse(msg)
    # Order follows mapping order, not message order
    assert out == ["moisturizer", "cleanser"]


def test_category_parser_deduplicates_preserving_order(tmp_path: Path):
    data = {
        "categories": {
            "moisturizer": ["cream", "lotion"],
        }
    }
    p = tmp_path / "category_patterns.yaml"
    write_yaml(p, data)
    parser = CategoryParser(p)

    msg = "cream, Lotion, CREAM again!"
    out = parser.parse(msg)
    # Only one "moisturizer"
    assert out == ["moisturizer"]


def test_category_parser_no_match_returns_empty_list(tmp_path: Path):
    data = {"categories": {"sunscreen": ["spf", "sunblock"]}}
    p = tmp_path / "category_patterns.yaml"
    write_yaml(p, data)
    parser = CategoryParser(p)

    assert parser.parse("looking for a serum") == []


def test_category_parser_multiple_hits_order_by_mapping(tmp_path: Path):
    data = {
        "categories": {
            "cleanser": ["wash"],
            "serum": ["serum"],
            "moisturizer": ["cream"],
        }
    }
    p = tmp_path / "category_patterns.yaml"
    write_yaml(p, data)
    parser = CategoryParser(p)

    # Message contains all three; result should follow mapping order
    out = parser.parse("serum first, then wash, then cream")
    assert out == ["cleanser", "serum", "moisturizer"]


# ---------- SkinTypeParser ----------

def test_skin_type_parser_returns_canonical(tmp_path: Path):
    data = {
        "skin_types": {
            "oily": ["grasa", "oily"],
            "combination": ["mixta", "combo"],
            "dry": ["seca", "dry"],
        }
    }
    p = tmp_path / "skin_types.yaml"
    write_yaml(p, data)
    parser = SkinTypeParser(p)

    assert parser.parse("tengo la piel GRASA") == "oily"
    assert parser.parse("piel mixta, a veces combo") == "combination"
    assert parser.parse("muy seca en invierno") == "dry"


def test_skin_type_parser_no_match_returns_none(tmp_path: Path):
    data = {"skin_types": {"sensitive": ["sensible", "sensitive"]}}
    p = tmp_path / "skin_types.yaml"
    write_yaml(p, data)
    parser = SkinTypeParser(p)

    assert parser.parse("normal") is None
