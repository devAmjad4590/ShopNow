"""
Product Catalog API Tests
=========================
All requests target the API Gateway (http://localhost:8080) which routes:
  /products/**   -> http://localhost:8083/api/v1/products/**
  /categories/** -> http://localhost:8083/api/v1/categories/**

Gateway auth behaviour (JWTAuthenticationFilter):
  - /auth/** is public (no token required)
  - Everything else: a valid Bearer token is mandatory → 401 if missing/invalid
  - The gateway injects X-User-Id and X-User-Role headers downstream once the
    token is validated.

Product-catalog auth behaviour (HeaderArgumentResolver):
  - Routes that inject @AuthRole require the X-User-Role header (set by gateway)
  - If X-User-Role != "ADMIN" → 403 Forbidden
  - Unauthenticated (no gateway token) → 401 before the service is even reached

Public routes (no token needed):
  GET /products
  GET /products/{id}
  GET /categories

Protected — any authenticated user:
  (none in current implementation; reads only need the gateway token, not admin)

Protected — ADMIN role only:
  POST   /categories
  PUT    /categories/{id}
  DELETE /categories/{id}
  POST   /products
  PUT    /products/{id}
  DELETE /products/{id}

Internal route NOT exposed via gateway:
  GET /internal/products/{id}  → gateway has no matching route → 404

Run:
  pytest tests/test_product.py -v
"""

import uuid

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_headers(access_token: str) -> dict:
    """Build an Authorization header dict from a bearer token."""
    return {"Authorization": f"Bearer {access_token}"}


def unique_category_name() -> str:
    return f"Test Category {uuid.uuid4().hex[:6]}"


def unique_product_name() -> str:
    return f"Test Product {uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Fixtures — seeded data used across multiple tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def admin_token(gateway_url: str) -> str:
    """
    Returns a valid Bearer token for an ADMIN user.

    IMPORTANT: The auth service registers all users with role USER by default.
    There is no self-service way to obtain an ADMIN token via the public API.
    To run admin-only tests against a real stack, either:
      a) Set the ADMIN_TOKEN environment variable to an existing admin JWT, or
      b) Manually UPDATE the user's role in the database and re-login.

    If ADMIN_TOKEN is not set, admin tests are skipped with a clear message.
    """
    import os
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        pytest.skip(
            "ADMIN_TOKEN env var is not set. "
            "Set it to a valid JWT for an ADMIN-role user to run admin tests."
        )
    return token


@pytest.fixture(scope="module")
def seeded_category(gateway_url: str, admin_token: str) -> dict:
    """Create a category via the API and return its response body dict.

    Scoped to module so all product tests can reference one stable category.
    Cleaned up (deleted) after the module finishes.
    """
    payload = {"name": unique_category_name(), "description": "Seeded by test suite"}
    response = httpx.post(
        f"{gateway_url}/categories",
        json=payload,
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 201, (
        f"Failed to seed category ({response.status_code}): {response.text}"
    )
    category = response.json()
    yield category

    # Teardown: delete the seeded category (best effort)
    httpx.delete(
        f"{gateway_url}/categories/{category['id']}",
        headers=auth_headers(admin_token),
    )


@pytest.fixture(scope="module")
def seeded_product(gateway_url: str, admin_token: str, seeded_category: dict) -> dict:
    """Create a product via the API and return its response body dict.

    Cleaned up after the module finishes.
    """
    payload = {
        "name": unique_product_name(),
        "description": "Seeded product for test suite",
        "price": "49.99",
        "imageUrl": "https://cdn.shopnow.test/product.jpg",
        "categoryId": seeded_category["id"],
        "stock": 100,
    }
    response = httpx.post(
        f"{gateway_url}/products",
        json=payload,
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 201, (
        f"Failed to seed product ({response.status_code}): {response.text}"
    )
    product = response.json()
    yield product

    # Teardown: delete the seeded product (best effort)
    httpx.delete(
        f"{gateway_url}/products/{product['id']}",
        headers=auth_headers(admin_token),
    )


# ===========================================================================
# CATEGORY TESTS (via API Gateway)
# ===========================================================================

class TestGetCategories:
    """GET /categories — public, no token required."""

    def test_returns_200_and_list(self, gateway_url: str) -> None:
        """Happy path: unauthenticated request returns 200 and a JSON array."""
        response = httpx.get(f"{gateway_url}/categories")

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert isinstance(body, list), (
            f"Expected JSON array, got {type(body).__name__}: {body!r}"
        )

    def test_returns_200_with_valid_token(self, gateway_url: str, auth_tokens: dict) -> None:
        """Authenticated user can also list categories (token is optional here)."""
        response = httpx.get(
            f"{gateway_url}/categories",
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 200

    def test_each_category_has_expected_fields(self, gateway_url: str, seeded_category: dict) -> None:
        """Response items contain id, name, description, createdAt fields."""
        response = httpx.get(f"{gateway_url}/categories")
        assert response.status_code == 200
        body = response.json()
        # Find our seeded category in the list
        ids = [c["id"] for c in body]
        assert seeded_category["id"] in ids, (
            f"Seeded category id {seeded_category['id']} not found in list: {ids}"
        )
        # Validate shape of a single entry
        entry = next(c for c in body if c["id"] == seeded_category["id"])
        for field in ("id", "name", "description", "createdAt"):
            assert field in entry, f"Field '{field}' missing from category response"


class TestCreateCategory:
    """POST /categories — requires ADMIN token."""

    def test_happy_path_returns_201_with_category(
        self, gateway_url: str, admin_token: str
    ) -> None:
        """Admin creates a category → 201 with the new category body."""
        name = unique_category_name()
        response = httpx.post(
            f"{gateway_url}/categories",
            json={"name": name, "description": "Integration test category"},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["name"] == name
        assert body["description"] == "Integration test category"
        assert isinstance(body["id"], int)
        assert "createdAt" in body

        # Cleanup
        httpx.delete(
            f"{gateway_url}/categories/{body['id']}",
            headers=auth_headers(admin_token),
        )

    def test_missing_name_returns_400(self, gateway_url: str, admin_token: str) -> None:
        """name is @NotBlank — omitting it returns 400 VALIDATION_ERROR."""
        response = httpx.post(
            f"{gateway_url}/categories",
            json={"description": "No name provided"},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400, (
            f"Expected 400 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("error") == "VALIDATION_ERROR"

    def test_blank_name_returns_400(self, gateway_url: str, admin_token: str) -> None:
        """An empty string for name violates @NotBlank and returns 400."""
        response = httpx.post(
            f"{gateway_url}/categories",
            json={"name": "   ", "description": "Blank name"},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400, (
            f"Expected 400 but got {response.status_code}: {response.text}"
        )

    def test_without_token_returns_401(self, gateway_url: str) -> None:
        """No Bearer token → gateway rejects with 401 before reaching the service."""
        response = httpx.post(
            f"{gateway_url}/categories",
            json={"name": unique_category_name()},
        )
        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}: {response.text}"
        )

    def test_with_invalid_token_returns_401(self, gateway_url: str) -> None:
        """Malformed/expired JWT → gateway rejects with 401."""
        response = httpx.post(
            f"{gateway_url}/categories",
            json={"name": unique_category_name()},
            headers={"Authorization": "Bearer this.is.not.a.real.jwt"},
        )
        assert response.status_code == 401, (
            f"Expected 401 but got {response.status_code}: {response.text}"
        )

    def test_with_user_role_returns_403(
        self, gateway_url: str, auth_tokens: dict
    ) -> None:
        """A USER-role token is valid but lacks ADMIN privilege → 403."""
        response = httpx.post(
            f"{gateway_url}/categories",
            json={"name": unique_category_name()},
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 403, (
            f"Expected 403 but got {response.status_code}: {response.text}"
        )


class TestUpdateCategory:
    """PUT /categories/{id} — requires ADMIN token."""

    def test_happy_path_returns_200_with_updated_category(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """Admin updates an existing category → 200 with updated fields."""
        new_name = unique_category_name()
        response = httpx.put(
            f"{gateway_url}/categories/{seeded_category['id']}",
            json={"name": new_name, "description": "Updated description"},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["id"] == seeded_category["id"]
        assert body["name"] == new_name
        assert body["description"] == "Updated description"

    def test_nonexistent_id_returns_404(
        self, gateway_url: str, admin_token: str
    ) -> None:
        """Updating a category that does not exist → 404 NOT_FOUND."""
        response = httpx.put(
            f"{gateway_url}/categories/999999",
            json={"name": unique_category_name()},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 404, (
            f"Expected 404 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("error") == "NOT_FOUND"

    def test_missing_name_returns_400(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """name is required; omitting it triggers validation → 400."""
        response = httpx.put(
            f"{gateway_url}/categories/{seeded_category['id']}",
            json={"description": "Update without name"},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400

    def test_without_token_returns_401(
        self, gateway_url: str, seeded_category: dict
    ) -> None:
        """No token → 401 from gateway."""
        response = httpx.put(
            f"{gateway_url}/categories/{seeded_category['id']}",
            json={"name": unique_category_name()},
        )
        assert response.status_code == 401

    def test_with_user_role_returns_403(
        self, gateway_url: str, auth_tokens: dict, seeded_category: dict
    ) -> None:
        """USER role is not ADMIN → 403."""
        response = httpx.put(
            f"{gateway_url}/categories/{seeded_category['id']}",
            json={"name": unique_category_name()},
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 403


class TestDeleteCategory:
    """DELETE /categories/{id} — requires ADMIN token."""

    def test_happy_path_returns_204(
        self, gateway_url: str, admin_token: str
    ) -> None:
        """Admin deletes an empty (no products) category → 204 No Content."""
        # Create a throw-away category
        create_response = httpx.post(
            f"{gateway_url}/categories",
            json={"name": unique_category_name(), "description": "To be deleted"},
            headers=auth_headers(admin_token),
        )
        assert create_response.status_code == 201
        category_id = create_response.json()["id"]

        delete_response = httpx.delete(
            f"{gateway_url}/categories/{category_id}",
            headers=auth_headers(admin_token),
        )
        assert delete_response.status_code == 204, (
            f"Expected 204 but got {delete_response.status_code}: {delete_response.text}"
        )

    def test_nonexistent_id_returns_404(
        self, gateway_url: str, admin_token: str
    ) -> None:
        """Deleting a category that does not exist → 404 NOT_FOUND."""
        response = httpx.delete(
            f"{gateway_url}/categories/999999",
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 404
        body = response.json()
        assert body.get("error") == "NOT_FOUND"

    def test_category_with_products_returns_409(
        self, gateway_url: str, admin_token: str, seeded_category: dict, seeded_product: dict
    ) -> None:
        """Deleting a category that still has products returns 409 CONFLICT.

        The seeded_product fixture creates a product in seeded_category, so
        attempting to delete seeded_category should be blocked.
        """
        response = httpx.delete(
            f"{gateway_url}/categories/{seeded_category['id']}",
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 409, (
            f"Expected 409 CONFLICT but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("error") == "CONFLICT"

    def test_without_token_returns_401(
        self, gateway_url: str, seeded_category: dict
    ) -> None:
        """No token → 401 from gateway."""
        response = httpx.delete(f"{gateway_url}/categories/{seeded_category['id']}")
        assert response.status_code == 401

    def test_with_user_role_returns_403(
        self, gateway_url: str, auth_tokens: dict, seeded_category: dict
    ) -> None:
        """USER role → 403."""
        response = httpx.delete(
            f"{gateway_url}/categories/{seeded_category['id']}",
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 403


# ===========================================================================
# PRODUCT TESTS (via API Gateway)
# ===========================================================================

class TestListProducts:
    """GET /products — public, no token required."""

    def test_returns_200_and_page_structure(self, gateway_url: str) -> None:
        """Happy path: unauthenticated request returns 200 and a Spring Page object."""
        response = httpx.get(f"{gateway_url}/products")

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        # Spring Page wraps results in a 'content' array with pagination metadata
        assert "content" in body, f"Expected 'content' key in page response: {body}"
        assert isinstance(body["content"], list)
        assert "totalElements" in body
        assert "totalPages" in body

    def test_filter_by_category_id(
        self, gateway_url: str, seeded_category: dict, seeded_product: dict
    ) -> None:
        """GET /products?categoryId=<id> returns only products in that category."""
        response = httpx.get(
            f"{gateway_url}/products",
            params={"categoryId": seeded_category["id"]},
        )
        assert response.status_code == 200
        body = response.json()
        for item in body["content"]:
            assert item["categoryId"] == seeded_category["id"], (
                f"Product {item['id']} has categoryId {item['categoryId']}, "
                f"expected {seeded_category['id']}"
            )

    def test_pagination_page_and_size(self, gateway_url: str) -> None:
        """Query params page and size are accepted and reflected in the response."""
        response = httpx.get(
            f"{gateway_url}/products",
            params={"page": 0, "size": 5},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["size"] == 5
        assert body["number"] == 0

    def test_filter_by_nonexistent_category_returns_empty_content(
        self, gateway_url: str
    ) -> None:
        """Filtering by a category ID that has no products returns an empty page."""
        response = httpx.get(
            f"{gateway_url}/products",
            params={"categoryId": 999999},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["content"] == []

    def test_seeded_product_appears_in_list(
        self, gateway_url: str, seeded_product: dict
    ) -> None:
        """The product created by the seeded_product fixture is visible in the list."""
        response = httpx.get(f"{gateway_url}/products")
        assert response.status_code == 200
        body = response.json()
        ids = [p["id"] for p in body["content"]]
        assert seeded_product["id"] in ids, (
            f"Seeded product id {seeded_product['id']} not found in list: {ids}"
        )


class TestGetProductById:
    """GET /products/{id} — public, no token required."""

    def test_returns_200_and_product_fields(
        self, gateway_url: str, seeded_product: dict
    ) -> None:
        """Happy path: fetching a known product returns 200 and the expected shape."""
        response = httpx.get(f"{gateway_url}/products/{seeded_product['id']}")

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["id"] == seeded_product["id"]
        for field in (
            "id", "name", "description", "price",
            "categoryId", "categoryName", "stock", "createdAt", "updatedAt",
        ):
            assert field in body, f"Field '{field}' missing from product response"

    def test_nonexistent_id_returns_404(self, gateway_url: str) -> None:
        """A product ID that does not exist → 404 NOT_FOUND."""
        response = httpx.get(f"{gateway_url}/products/999999")

        assert response.status_code == 404, (
            f"Expected 404 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("error") == "NOT_FOUND"

    def test_without_token_still_returns_200(
        self, gateway_url: str, seeded_product: dict
    ) -> None:
        """GET /products/{id} is public — no token should still work fine."""
        response = httpx.get(f"{gateway_url}/products/{seeded_product['id']}")
        assert response.status_code == 200


class TestCreateProduct:
    """POST /products — requires ADMIN token."""

    def test_happy_path_returns_201_with_product(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """Admin creates a product → 201 with the full ProductResponse body."""
        name = unique_product_name()
        payload = {
            "name": name,
            "description": "A brand new product",
            "price": "29.99",
            "imageUrl": "https://cdn.shopnow.test/img.jpg",
            "categoryId": seeded_category["id"],
            "stock": 50,
        }
        response = httpx.post(
            f"{gateway_url}/products",
            json=payload,
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["name"] == name
        assert body["categoryId"] == seeded_category["id"]
        assert body["stock"] == 50
        assert isinstance(body["id"], int)

        # Cleanup
        httpx.delete(
            f"{gateway_url}/products/{body['id']}",
            headers=auth_headers(admin_token),
        )

    def test_missing_name_returns_400(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """name is @NotBlank — omitting it returns 400 VALIDATION_ERROR."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={"price": "9.99", "categoryId": seeded_category["id"]},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400
        body = response.json()
        assert body.get("error") == "VALIDATION_ERROR"

    def test_missing_price_returns_400(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """price is @NotNull — omitting it returns 400 VALIDATION_ERROR."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={"name": unique_product_name(), "categoryId": seeded_category["id"]},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400
        body = response.json()
        assert body.get("error") == "VALIDATION_ERROR"

    def test_missing_category_id_returns_400(
        self, gateway_url: str, admin_token: str
    ) -> None:
        """categoryId is @NotNull — omitting it returns 400 VALIDATION_ERROR."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={"name": unique_product_name(), "price": "9.99"},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400
        body = response.json()
        assert body.get("error") == "VALIDATION_ERROR"

    def test_negative_price_returns_400(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """price has @DecimalMin("0.0") — a negative value returns 400."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "-5.00",
                "categoryId": seeded_category["id"],
            },
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400

    def test_negative_stock_returns_400(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """stock has @Min(0) — a negative stock value returns 400."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": seeded_category["id"],
                "stock": -1,
            },
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400

    def test_nonexistent_category_id_returns_404(
        self, gateway_url: str, admin_token: str
    ) -> None:
        """Creating a product with a category that does not exist → 404 NOT_FOUND."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": 999999,
            },
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 404

    def test_without_token_returns_401(
        self, gateway_url: str, seeded_category: dict
    ) -> None:
        """No Bearer token → gateway rejects with 401."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": seeded_category["id"],
            },
        )
        assert response.status_code == 401

    def test_with_invalid_token_returns_401(
        self, gateway_url: str, seeded_category: dict
    ) -> None:
        """Malformed JWT → 401 from gateway."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": seeded_category["id"],
            },
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )
        assert response.status_code == 401

    def test_with_user_role_returns_403(
        self, gateway_url: str, auth_tokens: dict, seeded_category: dict
    ) -> None:
        """USER-role token is valid but not ADMIN → 403 Forbidden."""
        response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": seeded_category["id"],
            },
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 403


class TestUpdateProduct:
    """PUT /products/{id} — requires ADMIN token."""

    def test_happy_path_returns_200_with_updated_product(
        self, gateway_url: str, admin_token: str, seeded_product: dict, seeded_category: dict
    ) -> None:
        """Admin updates all fields → 200 with updated ProductResponse."""
        new_name = unique_product_name()
        payload = {
            "name": new_name,
            "description": "Updated description",
            "price": "99.99",
            "imageUrl": "https://cdn.shopnow.test/updated.jpg",
            "categoryId": seeded_category["id"],
            "stock": 200,
        }
        response = httpx.put(
            f"{gateway_url}/products/{seeded_product['id']}",
            json=payload,
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["id"] == seeded_product["id"]
        assert body["name"] == new_name
        assert body["stock"] == 200

    def test_nonexistent_id_returns_404(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """Updating a product that does not exist → 404 NOT_FOUND."""
        response = httpx.put(
            f"{gateway_url}/products/999999",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": seeded_category["id"],
            },
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 404
        body = response.json()
        assert body.get("error") == "NOT_FOUND"

    def test_missing_required_fields_returns_400(
        self, gateway_url: str, admin_token: str, seeded_product: dict
    ) -> None:
        """Missing required fields on update → 400 VALIDATION_ERROR."""
        response = httpx.put(
            f"{gateway_url}/products/{seeded_product['id']}",
            json={"description": "Only description, missing name/price/categoryId"},
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 400

    def test_without_token_returns_401(
        self, gateway_url: str, seeded_product: dict, seeded_category: dict
    ) -> None:
        """No token → 401 from gateway."""
        response = httpx.put(
            f"{gateway_url}/products/{seeded_product['id']}",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": seeded_category["id"],
            },
        )
        assert response.status_code == 401

    def test_with_user_role_returns_403(
        self, gateway_url: str, auth_tokens: dict, seeded_product: dict, seeded_category: dict
    ) -> None:
        """USER role → 403."""
        response = httpx.put(
            f"{gateway_url}/products/{seeded_product['id']}",
            json={
                "name": unique_product_name(),
                "price": "9.99",
                "categoryId": seeded_category["id"],
            },
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 403


class TestDeleteProduct:
    """DELETE /products/{id} — requires ADMIN token."""

    def test_happy_path_returns_204(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """Admin deletes an existing product → 204 No Content."""
        # Create a throw-away product
        create_response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "1.00",
                "categoryId": seeded_category["id"],
                "stock": 0,
            },
            headers=auth_headers(admin_token),
        )
        assert create_response.status_code == 201
        product_id = create_response.json()["id"]

        delete_response = httpx.delete(
            f"{gateway_url}/products/{product_id}",
            headers=auth_headers(admin_token),
        )
        assert delete_response.status_code == 204, (
            f"Expected 204 but got {delete_response.status_code}: {delete_response.text}"
        )

    def test_deleted_product_is_no_longer_retrievable(
        self, gateway_url: str, admin_token: str, seeded_category: dict
    ) -> None:
        """After deletion, GET /products/{id} returns 404."""
        create_response = httpx.post(
            f"{gateway_url}/products",
            json={
                "name": unique_product_name(),
                "price": "1.00",
                "categoryId": seeded_category["id"],
                "stock": 0,
            },
            headers=auth_headers(admin_token),
        )
        assert create_response.status_code == 201
        product_id = create_response.json()["id"]

        httpx.delete(
            f"{gateway_url}/products/{product_id}",
            headers=auth_headers(admin_token),
        )

        get_response = httpx.get(f"{gateway_url}/products/{product_id}")
        assert get_response.status_code == 404

    def test_nonexistent_id_returns_404(
        self, gateway_url: str, admin_token: str
    ) -> None:
        """Deleting a product that does not exist → 404 NOT_FOUND."""
        response = httpx.delete(
            f"{gateway_url}/products/999999",
            headers=auth_headers(admin_token),
        )
        assert response.status_code == 404
        body = response.json()
        assert body.get("error") == "NOT_FOUND"

    def test_without_token_returns_401(
        self, gateway_url: str, seeded_product: dict
    ) -> None:
        """No token → 401 from gateway."""
        response = httpx.delete(f"{gateway_url}/products/{seeded_product['id']}")
        assert response.status_code == 401

    def test_with_user_role_returns_403(
        self, gateway_url: str, auth_tokens: dict, seeded_product: dict
    ) -> None:
        """USER role → 403."""
        response = httpx.delete(
            f"{gateway_url}/products/{seeded_product['id']}",
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 403


# ===========================================================================
# INTERNAL ENDPOINT (gateway routing behaviour)
# ===========================================================================

class TestInternalProductEndpoint:
    """GET /internal/products/{id}

    The api-gateway application.yml only maps /products/** and /categories/**
    for the product-catalog route. /internal/** has no gateway route, so the
    gateway itself returns 404 — the product-catalog service is never reached.
    """

    def test_internal_route_not_exposed_via_gateway_returns_404(
        self, gateway_url: str, seeded_product: dict, auth_tokens: dict
    ) -> None:
        """The /internal/products/{id} path has no gateway route → 404.

        This test documents that the internal endpoint is intentionally not
        reachable via the public gateway, even with a valid token.
        """
        response = httpx.get(
            f"{gateway_url}/internal/products/{seeded_product['id']}",
            headers=auth_headers(auth_tokens["access_token"]),
        )
        assert response.status_code == 404, (
            f"Expected 404 (no gateway route) but got {response.status_code}: {response.text}"
        )

    def test_internal_route_without_token_also_returns_404(
        self, gateway_url: str, seeded_product: dict
    ) -> None:
        """Even without a token the gateway returns 404 because the route doesn't exist.

        NOTE: If the gateway routes /internal/** in the future this will fail with
        401, which is the correct updated behaviour to implement.
        """
        response = httpx.get(
            f"{gateway_url}/internal/products/{seeded_product['id']}"
        )
        # Gateway has no route for /internal/** → Spring Cloud Gateway 404
        # If this starts returning 401, it means a route was added but left unprotected
        assert response.status_code == 404, (
            f"Expected 404 (no gateway route) but got {response.status_code}: {response.text}"
        )
