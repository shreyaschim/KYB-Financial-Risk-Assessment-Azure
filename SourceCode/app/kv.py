import os
from functools import lru_cache
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


@lru_cache(maxsize=1)
def _client() -> SecretClient:
    vault_url = os.environ["KEY_VAULT_URL"]
    cred = DefaultAzureCredential()
    return SecretClient(vault_url=vault_url, credential=cred)


def get_secret(name: str) -> str:
    return _client().get_secret(name).value