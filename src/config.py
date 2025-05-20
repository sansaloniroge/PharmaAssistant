from pathlib import Path
from typing import Final, ClassVar
import os
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv



class BaseConstants:
    """Immutable core configuration with type hints"""
    _PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent
    EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"
    LLM_MODEL: Final[str] = "gpt-3.5-turbo"
    load_dotenv()

    @classmethod
    def validate_paths(cls) -> None:
        """Ensure critical paths exist"""
        cls.DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not cls.DATA_PATH.exists():
            raise FileNotFoundError(f"Missing data file at {cls.DATA_PATH}")


class DevConstants(BaseConstants):
    """Development configuration (local files)"""
    DATA_PATH: Final[Path] = BaseConstants._PROJECT_ROOT / "data" / "skincare_products_data.csv"
    FAISS_INDEX_DIR: ClassVar[Path] = BaseConstants._PROJECT_ROOT / "storage" / "faiss_index"

    @property
    def OPENAI_API_KEY(self) -> str:
        """Load key from .env file"""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("Missing OPENAI_API_KEY in .env")
        return key


class ProdConstants(BaseConstants):
    """Production configuration (cloud-integrated)"""
    DATA_PATH: Final[Path] = Path("/mnt/clinical-data/latest.csv")
    FAISS_INDEX_DIR: ClassVar[Path] = Path("/mnt/vector-storage/faiss_index")

    def __init__(self):
        self._kv_client = SecretClient(
            vault_url="https://your-key-vault.vault.azure.net",
            credential=DefaultAzureCredential()
        )

    @property
    def OPENAI_API_KEY(self) -> str:
        """Fetch from Azure Key Vault"""
        return self._kv_client.get_secret("pharma-openai-key").value


# Environment auto-detection
CONFIG = ProdConstants() if os.getenv("IS_PROD") else DevConstants()