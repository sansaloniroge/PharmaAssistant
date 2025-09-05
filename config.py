from pathlib import Path
from typing import Final, Optional
import os
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv

# -------------------------------------------------------------------
# Load environment variables from .env (only needed in DEV typically)
# -------------------------------------------------------------------
load_dotenv()

class BaseConstants:
    """
    Base config shared by Dev and Prod.
    The new pharma_assistant.py reads these attributes if present.
    """
    _PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent

    # Strong defaults (can be overridden per environment)
    EMBEDDING_MODEL: Final[str] = "text-embedding-3-large"
    CHAT_MODEL: Final[str] = "gpt-4o-mini"
    # Backward-compat alias (in case other code reads LLM_MODEL)
    LLM_MODEL: Final[str] = CHAT_MODEL

    # Prompt files (the refined assistant will also fall back to files next to the script)
    SYSTEM_PROMPT_PATH: Final[Path] = _PROJECT_ROOT / "data" / "prompts" / "system_prompt.txt"
    FEWSHOT_PATH: Final[Path] = _PROJECT_ROOT / "data" / "prompts" / "few_shot_prompt.yaml"

    # Retrieval settings
    TOP_K: Final[int] = 5
    TEMPERATURE: Final[float] = 0.6

    # Medical terms file (used by the refined assistant)
    MEDICAL_TERMS_PATH: Final[Path] = _PROJECT_ROOT / "data" / "medical_terms.yaml"

    # Schema mapping file (used by the loader)
    SCHEMA_MAP_PATH: Final[Path] = _PROJECT_ROOT / "data" / "schema_map.yaml"

    # Price patterns file (used by the refined assistant)
    PRICE_PATTERNS_PATH: Final[Path] = _PROJECT_ROOT / "data" / "price_patterns.yaml"

    @classmethod
    def validate_paths(cls) -> None:
        """
        Ensure required files exist. This raises early, which is helpful in CI/CD.
        """
        # DATA_PATH must be defined in child classes
        data_path = getattr(cls, "DATA_PATH", None)
        if data_path is None:
            raise AttributeError(f"{cls.__name__} should define DATA_PATH")
        data_path.parent.mkdir(parents=True, exist_ok=True)
        if not data_path.exists():
            raise FileNotFoundError(f"Data source file {data_path} is missing")

        # Prompt files are recommended (the app can still run without few-shot)
        cls.SYSTEM_PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not cls.SYSTEM_PROMPT_PATH.exists():
            raise FileNotFoundError(f"System prompt file {cls.SYSTEM_PROMPT_PATH} is missing")
        # Few-shot is optional; if you want to enforce it, uncomment below:
        # if not cls.FEWSHOT_PATH.exists():
        #     raise FileNotFoundError(f"Few-shot file {cls.FEWSHOT_PATH} is missing")

    # --- API key accessors (optional use: pharma_assistant reads OPENAI_API_KEY from env) ---
    @staticmethod
    def _read_env_openai_key() -> str:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is missing. Set it in your environment or .env")
        return key


class DevConstants(BaseConstants):
    """
    Development configuration (local machine).
    Uses .env for the OpenAI API key and local files for data/prompts.
    """
    DATA_PATH: Final[Path] = BaseConstants._PROJECT_ROOT / "data" / "skincare_products_data.csv"
    # Optional local path where you could persist FAISS if you add that later
    FAISS_INDEX_DIR: Final[Path] = BaseConstants._PROJECT_ROOT / "storage" / "faiss_index"

    @property
    def OPENAI_API_KEY(self) -> str:
        # Load from .env / environment
        return self._read_env_openai_key()


class ProdConstants(BaseConstants):
    """
    Production configuration (cloud).
    Reads the OpenAI key from Azure Key Vault using Managed Identity.
    """
    DATA_PATH: Final[Path] = Path("/mnt/clinical-data/skincare_products_data.csv")
    FAISS_INDEX_DIR: Final[Path] = Path("/mnt/vector-storage/faiss_index")

    # Allow overriding via environment variables
    KEY_VAULT_URL: Final[str] = os.getenv("KEY_VAULT_URL", "https://your-key-vault.vault.azure.net")
    OPENAI_SECRET_NAME: Final[str] = os.getenv("OPENAI_SECRET_NAME", "pharma-openai-key")

    def __init__(self):
        # Initialize Key Vault client with Managed Identity
        self._kv_client = SecretClient(
            vault_url=self.KEY_VAULT_URL,
            credential=DefaultAzureCredential()
        )

    @property
    def OPENAI_API_KEY(self) -> str:
        # Fetch the OpenAI key from Key Vault
        secret = self._kv_client.get_secret(self.OPENAI_SECRET_NAME)
        if not secret or not secret.value:
            raise ValueError(f"Secret '{self.OPENAI_SECRET_NAME}' not found or empty in Key Vault.")
        return secret.value


# -------------------------------------------------------------------
# Environment autodetection
# Set IS_PROD=1 in your environment for production
# -------------------------------------------------------------------
CONFIG = ProdConstants() if os.getenv("IS_PROD") else DevConstants()

# Optional: validate paths early (uncomment to enforce strict checks at import time)
# CONFIG.validate_paths()
