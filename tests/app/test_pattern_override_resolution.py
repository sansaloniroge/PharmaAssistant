from pathlib import Path
import tempfile
import shutil
import yaml
from app.profile_resolver import resolve_paths

def test_client_pattern_overrides_take_precedence(tmp_path: Path = None):
    tmp = Path(tempfile.mkdtemp(prefix="pa_patterns_"))
    try:
        # perfiles
        (tmp/"profiles"/"clients").mkdir(parents=True)
        (tmp/"profiles"/"base.yaml").write_text(
            yaml.safe_dump({
                "version": 1,
                "defaults": {
                    "paths": {
                        "category_patterns": "data/patterns/category_patterns.yaml",
                        "price_patterns": "data/patterns/price_patterns.yaml",
                        "schema_map": "data/patterns/schema_map.yaml",
                        "skin_types": "data/patterns/skin_types.yaml",
                        "medical_terms": "data/patterns/medical_terms.yaml",
                        "system_prompt": "data/general_prompts/system_prompt.txt",
                        "compose_prompt": "data/general_prompts/compose_prompt.txt",
                        "greeting_prompt": "data/general_prompts/greeting_prompt.txt",
                        "no_match_prompt": "data/general_prompts/no_match_prompt.txt",
                        "few_shot_prompt": "data/general_prompts/few_shot_prompt.txt",
                        "data_csv": "data/clients/client_1/products_catalog.csv",
                    }
                }
            }),
            encoding="utf-8"
        )
        (tmp/"profiles"/"clients"/"client_1.yaml").write_text(
            yaml.safe_dump({"store":{"id":"c1","name":"Client 1"}}), encoding="utf-8"
        )

        # data global
        (tmp/"data"/"patterns").mkdir(parents=True)
        for f in ["category_patterns.yaml","price_patterns.yaml","schema_map.yaml","skin_types.yaml","medical_terms.yaml"]:
            (tmp/"data"/"patterns"/f).write_text("k:v\n", encoding="utf-8")
        (tmp/"data"/"general_prompts").mkdir(parents=True)
        for f in ["system_prompt.txt","compose_prompt.txt","greeting_prompt.txt","no_match_prompt.txt","few_shot_prompt.txt"]:
            (tmp/"data"/"general_prompts"/f).write_text("p", encoding="utf-8")

        # cliente: CSV + override sólo de category_patterns
        (tmp/"data"/"clients"/"client_1"/"patterns").mkdir(parents=True)
        (tmp/"data"/"clients"/"client_1"/"patterns"/"category_patterns.yaml").write_text("client_specific: 1\n", encoding="utf-8")
        (tmp/"data"/"clients"/"client_1"/"products_catalog.csv").write_text("name,price\nA,10\n", encoding="utf-8")

        paths = resolve_paths("client_1", repo_root=tmp, data_root=tmp/"data", profiles_root=tmp/"profiles")
        # category_patterns debe ir al override del cliente
        assert str(paths["CATEGORY_PATTERNS_PATH"]).endswith("data/clients/client_1/patterns/category_patterns.yaml")
        # schema_map (sin override) debe ir al global
        assert str(paths["SCHEMA_MAP_PATH"]).endswith("data/patterns/schema_map.yaml")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
