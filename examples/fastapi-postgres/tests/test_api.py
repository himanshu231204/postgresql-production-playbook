from uuid import uuid4

from fastapi.testclient import TestClient


def _new_customer(client: TestClient) -> dict:
    response = client.post(
        "/customers", json={"email": f"{uuid4().hex}@example.test", "name": "Test"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_live_and_ready(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}


def test_create_and_get_customer(client: TestClient) -> None:
    created = _new_customer(client)
    fetched = client.get(f"/customers/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == created["email"]


def test_duplicate_email_is_409(client: TestClient) -> None:
    created = _new_customer(client)
    response = client.post(
        "/customers", json={"email": created["email"], "name": "Again"}
    )
    assert response.status_code == 409


def test_unknown_customer_is_404(client: TestClient) -> None:
    assert client.get("/customers/999999999").status_code == 404
    response = client.post("/customers/999999999/orders", json={"total_cents": 1})
    assert response.status_code == 404


def test_validation_rejects_negative_total(client: TestClient) -> None:
    created = _new_customer(client)
    response = client.post(
        f"/customers/{created['id']}/orders", json={"total_cents": -1}
    )
    assert response.status_code == 422


def test_orders_and_selectinload(client: TestClient) -> None:
    created = _new_customer(client)
    for total in (1000, 2500):
        response = client.post(
            f"/customers/{created['id']}/orders", json={"total_cents": total}
        )
        assert response.status_code == 201
    orders = client.get(f"/customers/{created['id']}/orders").json()
    assert [o["total_cents"] for o in orders] == [1000, 2500]

    page = client.get(
        "/customers/with-orders", params={"after_id": created["id"] - 1, "limit": 1}
    ).json()
    assert page[0]["id"] == created["id"]
    assert len(page[0]["orders"]) == 2
