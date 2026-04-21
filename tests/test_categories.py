# Run: pip install -r requirements.txt
# Then: pytest -v

import httpx


def test_get_categories_returns_200_and_list(base_url: str) -> None:
    """GET /categories is public, returns HTTP 200 and a JSON array."""
    response = httpx.get(f"{base_url}/categories")

    assert response.status_code == 200, (
        f"Expected 200 but got {response.status_code}: {response.text}"
    )

    body = response.json()
    assert isinstance(body, list), (
        f"Expected a JSON array but got {type(body).__name__}: {body!r}"
    )
