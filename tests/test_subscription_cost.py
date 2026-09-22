import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "API_KEYS", {})
    monkeypatch.setattr(server, "ACCOUNT_KEYS", {})
    with TestClient(server.app) as test_client:
        yield test_client


def register(client, account="cost-test", plan="free"):
    response = client.post("/api/v1/register", json={"account": account, "plan": plan})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["api_key"]}


def configure_discount(monkeypatch, discount):
    config = {"discount": discount}
    monkeypatch.setattr(server.subscription_notifications, "_settings", lambda: (config, None))
    return config


def auth_info(client, headers):
    response = client.get("/api/v1/auth/info", headers=headers)
    assert response.status_code == 200
    return response.json()


def test_scene_cost_uses_selected_capabilities_and_is_frozen_after_purchase(
        client, monkeypatch):
    config = configure_discount(monkeypatch, 0.8)
    headers = register(client)

    response = client.post(
        "/api/v1/services/robot_patrol/subscribe",
        headers=headers,
        json={"network_capability_ids": ["target_detection"]},
    )
    assert response.status_code == 200
    assert response.json()["notification"]["price"] is None
    assert auth_info(client, headers)["estimated_monthly_cost"] == 15.92

    config["discount"] = 0.5
    assert auth_info(client, headers)["estimated_monthly_cost"] == 15.92

    assert client.delete("/api/v1/services/robot_patrol/subscribe", headers=headers).status_code == 200
    assert auth_info(client, headers)["estimated_monthly_cost"] == 0.0


def test_plan_and_package_entitlements_do_not_double_charge_direct_capabilities(
        client, monkeypatch):
    configure_discount(monkeypatch, 0.8)
    headers = register(client, plan="pro")

    response = client.post("/api/v1/subscribe", json={
        "account": "cost-test",
        "capability_ids": ["target_detection"],
        "package_ids": ["robot_patrol"],
    })
    assert response.status_code == 200
    assert auth_info(client, headers)["estimated_monthly_cost"] == 188.0

    scene = client.post(
        "/api/v1/services/robot_patrol/subscribe",
        headers=headers,
        json={"network_capability_ids": ["target_detection"]},
    )
    assert scene.status_code == 200
    assert auth_info(client, headers)["estimated_monthly_cost"] == 203.92


def test_scene_grant_suppresses_direct_charge_until_last_overlapping_scene_is_cancelled(
        client, monkeypatch):
    configure_discount(monkeypatch, 0.8)
    headers = register(client)
    assert client.post("/api/v1/subscribe", json={
        "account": "cost-test", "capability_ids": ["target_detection"],
    }).status_code == 200
    assert auth_info(client, headers)["estimated_monthly_cost"] == 19.9

    for service_id in ("robot_patrol", "collaborative_tracking"):
        assert client.post(
            f"/api/v1/services/{service_id}/subscribe",
            headers=headers,
            json={"network_capability_ids": ["target_detection"]},
        ).status_code == 200
    assert auth_info(client, headers)["estimated_monthly_cost"] == 31.84

    assert client.delete(
        "/api/v1/services/robot_patrol/subscribe", headers=headers
    ).status_code == 200
    assert auth_info(client, headers)["estimated_monthly_cost"] == 15.92

    assert client.delete(
        "/api/v1/services/collaborative_tracking/subscribe", headers=headers
    ).status_code == 200
    assert auth_info(client, headers)["estimated_monthly_cost"] == 19.9
