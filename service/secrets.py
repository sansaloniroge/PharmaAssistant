import os
from typing import Optional

# Fallback dev (.env)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

def get_openai_api_key() -> str:
    kv_url = os.getenv("AZURE_KEY_VAULT_URL")
    if kv_url:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.keyvault.secrets import SecretClient
            cred = DefaultAzureCredential()
            client = SecretClient(vault_url=kv_url, credential=cred)
            name = os.getenv("OPENAI_API_KEY_SECRET_NAME", "OPENAI-API-KEY")
            return client.get_secret(name).value
        except Exception as e:
            print(f"[WARN] Key Vault lookup failed: {e}")
    # Fallback local
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY no disponible (Key Vault/ENV).")
    return key