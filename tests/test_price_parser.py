from pathlib import Path
import yaml
import numpy as np
import pytest

from app.price_parser import PriceParser


def write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_yaml_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        PriceParser(tmp_path / "missing.yaml")


def test_yaml_missing_key_raises(tmp_path: Path):
    bad = {"not_price_patterns": {}}
    p = tmp_path / "price_patterns.yaml"
    write_yaml(p, bad)
    with pytest.raises(ValueError):
        PriceParser(p)


def test_parse_under_variants(tmp_path: Path):
    data = {
        "price_patterns": {
            "en": {"under": ["under", "below", "<"], "between": ["to", "-"], "currency": ["€", "$"]},
            "es": {"under": ["menos de"], "between": ["a", "-"], "currency": ["€"]},
        }
    }
    p = tmp_path / "price_patterns.yaml"
    write_yaml(p, data)
    parser = PriceParser(p)

    assert parser.parse("under 25") == (0.0, 25.0)
    assert parser.parse("below 9") == (0.0, 9.0)
    assert parser.parse("menos de 40") == (0.0, 40.0)
    assert parser.parse("< 15") == (0.0, 15.0)


def test_parse_between_variants(tmp_path: Path):
    data = {
        "price_patterns": {
            "en": {"under": ["under"], "between": ["to", "-"], "currency": ["€", "$"]},
            "es": {"under": ["menos de"], "between": ["a", "-"], "currency": ["€"]},
        }
    }
    p = tmp_path / "price_patterns.yaml"
    write_yaml(p, data)
    parser = PriceParser(p)

    assert parser.parse("10 to 20") == (10.0, 20.0)
    assert parser.parse("10-20") == (10.0, 20.0)
    assert parser.parse("10 a 20") == (10.0, 20.0)


def test_parse_currency_exact_budget(tmp_path: Path):
    data = {
        "price_patterns": {
            "en": {"under": ["under", "below", "<"], "between": ["to", "-"], "currency": ["€", "eur", "$"]},
        }
    }
    p = tmp_path / "price_patterns.yaml"
    write_yaml(p, data)
    parser = PriceParser(p)

    assert parser.parse("budget € 30") == (30.0, 30.0)
    assert parser.parse("around $ 15 is fine") == (15.0, 15.0)
    assert parser.parse("EUR 22 max") == (22.0, 22.0)


def test_parse_reversed_range_normalized(tmp_path: Path):
    data = {
        "price_patterns": {
            "en": {"under": ["under"], "between": ["to", "-"], "currency": ["€"]},
        }
    }
    p = tmp_path / "price_patterns.yaml"
    write_yaml(p, data)
    parser = PriceParser(p)

    # Should normalize 20 to 10 -> (10, 20)
    assert parser.parse("20 to 10") == (10.0, 20.0)


def test_no_match_returns_none(tmp_path: Path):
    data = {
        "price_patterns": {
            "en": {"under": ["under"], "between": ["to", "-"], "currency": ["€"]},
        }
    }
    p = tmp_path / "price_patterns.yaml"
    write_yaml(p, data)
    parser = PriceParser(p)

    assert parser.parse("I don't care about price") is None
