from pathlib import Path
from typing import Final
import os
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class BaseConstants:
    _PROJECT_ROOT: Final[Path] = Path(__file__).parent.parent
    EMBEDDING_MODEL: Final[str] = "text-embedding-3-small"
    LLM_MODEL: Final[str] = "gpt-3.5-turbo"

    @classmethod
    def validate_paths(cls) -> None:
        """Make sure the required paths and files exist"""
        data_path = getattr(cls, "DATA_PATH", None)
        if data_path is None:
            raise AttributeError(f"{cls.__name__} should define DATA_PATH")
        data_path.parent.mkdir(parents=True, exist_ok=True)
        if not data_path.exists():
            raise FileNotFoundError(f"Data source file {data_path} is missing")

class DevConstants(BaseConstants):
    """Development configuration (local files)"""
    DATA_PATH: Final[Path] = BaseConstants._PROJECT_ROOT / "data" / "skincare_products_data.csv"
    FAISS_INDEX_DIR: Final[Path] = BaseConstants._PROJECT_ROOT / "storage" / "faiss_index"

    @property
    def OPENAI_API_KEY(self) -> str:
        """Load the API Key from .env"""
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY missing in .env")
        return key

class ProdConstants(BaseConstants):
    """Production configuration (cloud integration)"""
    DATA_PATH: Final[Path] = Path("/mnt/clinical-data/latest.csv")
    FAISS_INDEX_DIR: Final[Path] = Path("/mnt/vector-storage/faiss_index")

    def __init__(self):
        self._kv_client = SecretClient(
            vault_url="https://your-key-vault.vault.azure.net",
            credential=DefaultAzureCredential()
        )

    @property
    def OPENAI_API_KEY(self) -> str:
        """Get the key from Azure Key Vault"""
        return self._kv_client.get_secret("pharma-openai-key").value

# Detección automática de entorno
CONFIG = ProdConstants() if os.getenv("IS_PROD") else DevConstants()