# Run: pip install -r requirements.txt
# Then: pytest -v

import pytest


@pytest.fixture(scope="session")
def base_url() -> str:
    """Base URL for the product-catalog service running on port 8083."""
    return "http://localhost:8083/api/v1"
