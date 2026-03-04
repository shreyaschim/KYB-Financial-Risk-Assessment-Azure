import os
import pytest

@pytest.fixture(scope="session")
def base_url():
    url = os.getenv("BASE_URL")
    if not url:
        raise RuntimeError("Set BASE_URL env var, e.g. export BASE_URL=https://<your-app-url>")
    return url.rstrip("/")