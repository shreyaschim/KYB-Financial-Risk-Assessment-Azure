import os
from typing import Optional, Tuple

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings


def _blob_service_client() -> BlobServiceClient:
    account = os.environ["STORAGE_ACCOUNT"]
    account_url = f"https://{account}.blob.core.windows.net"
    cred = DefaultAzureCredential()
    return BlobServiceClient(account_url=account_url, credential=cred)


def upload_bytes(blob_path: str, data: bytes, content_type: str) -> str:
    """
    Uploads to container STORAGE_CONTAINER using Managed Identity (DefaultAzureCredential).
    Returns a blob URL.
    """
    container = os.environ["STORAGE_CONTAINER"]
    return upload_bytes_to(container=container, blob_path=blob_path, data=data, content_type=content_type)


def upload_bytes_to(container: str, blob_path: str, data: bytes, content_type: str) -> str:
    """
    Upload to a specific container by name (no new env vars).
    """
    bsc = _blob_service_client()
    blob_client = bsc.get_blob_client(container=container, blob=blob_path)
    blob_client.upload_blob(
        data,
        overwrite=True,
        content_settings=ContentSettings(content_type=content_type),
    )
    return blob_client.url


def download_bytes(blob_path: str) -> Tuple[bytes, Optional[str]]:
    """
    Downloads from container STORAGE_CONTAINER (raw-documents) using Managed Identity.
    Returns (bytes, content_type).
    """
    container = os.environ["STORAGE_CONTAINER"]
    return download_bytes_from(container=container, blob_path=blob_path)


def download_bytes_from(container: str, blob_path: str) -> Tuple[bytes, Optional[str]]:
    """
    Download from a specific container by name (no new env vars).
    Returns (bytes, content_type).
    """
    bsc = _blob_service_client()
    blob_client = bsc.get_blob_client(container=container, blob=blob_path)

    # Content type from blob properties (may be None if not set)
    content_type = None
    try:
        props = blob_client.get_blob_properties()
        cs = getattr(props, "content_settings", None)
        content_type = cs.content_type if cs else None
    except Exception:
        pass

    data = blob_client.download_blob().readall()
    return data, content_type
