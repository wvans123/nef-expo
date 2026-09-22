import json
import uuid

import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "API_KEYS", {})
    monkeypatch.setattr(server, "ACCOUNT_KEYS", {})
    monkeypatch.setattr(server, "PER_CALL_BILLS", {})
    with TestClient(server.app) as test_client:
        yield test_client


def register(client, plan="free"):
    account = "scene-grant-" + uuid.uuid4().hex
    response = client.post("/api/v1/register", json={"account": account, "plan": plan})
    assert response.status_code == 200
    key = response.json()["api_key"]
    return account, key, {"Authorization": "Bearer " + key}


def subscribe_scene(client, headers, service_id, selected=None):
    kwargs = {"headers": headers}
    if selected is not None:
        kwargs["json"] = {"network_capability_ids": selected}
    response = client.post(f"/api/v1/services/{service_id}/subscribe", **kwargs)
    assert response.status_code == 200, response.text


def auth_info(client, headers):
    response = client.get("/api/v1/auth/info", headers=headers)
    assert response.status_code == 200
    return response.json()


def mcp_call(client, headers, capability_id, arguments):
    response = client.post("/api/v1/mcp/tools/call", headers=headers, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": capability_id, "arguments": arguments},
    })
    assert response.status_code == 200
    return response.json()


def test_partial_scene_selection_grants_rest_and_mcp_only_to_selected_account(client):
    account, _, headers = register(client)
    subscribe_scene(client, headers, "robot_patrol", ["target_detection"])

    info = auth_info(client, headers)
    assert info["direct_subscriptions"] == []
    assert info["subscribed_capabilities"] == ["target_detection"]
    assert info["capability_grant_sources"] == {
        "target_detection": ["scene:robot_patrol"],
    }

    assert client.post(
        "/api/v1/capabilities/target_detection/invoke",
        headers=headers,
        json={"area": "A"},
    ).status_code == 200
    selected_mcp = mcp_call(client, headers, "target_detection", {"area": "A"})
    assert "payment_required" not in selected_mcp["result"]
    assert json.loads(selected_mcp["result"]["content"][0]["text"])["data_source"] == "mock"

    assert client.post(
        "/api/v1/capabilities/sensing_fusion/invoke",
        headers=headers,
        json={"area": "A"},
    ).status_code == 402
    assert mcp_call(
        client, headers, "sensing_fusion", {"area": "A"}
    )["result"]["payment_required"]
    assert client.post(
        "/api/v1/services/traffic_flow_detection/intent",
        headers={**headers, "X-NEF-Execution": "demo"},
        json={"text": "检测"},
    ).status_code == 403

    other_account, _, other_headers = register(client)
    assert auth_info(client, other_headers)["capability_grant_sources"] == {}
    assert client.post(
        "/api/v1/capabilities/target_detection/invoke",
        headers=other_headers,
        json={"area": "A"},
    ).status_code == 402
    assert client.get(
        "/api/v1/integration/subscriptions", params={"account_id": other_account}
    ).json()["tools"] == []
    assert client.get(
        "/api/v1/integration/subscriptions", params={"account_id": account}
    ).json()["tools"][0]["grant_sources"] == ["scene:robot_patrol"]


def test_full_legacy_default_and_explicit_empty_selection_do_not_expand_each_other(client):
    _, key, headers = register(client)
    subscribe_scene(client, headers, "robot_patrol")
    expected = server._scene_capability_ids("robot_patrol")
    assert auth_info(client, headers)["subscribed_capabilities"] == sorted(expected)

    record = server.API_KEYS[key]
    record["scene_subscription_capabilities"].pop("robot_patrol")
    legacy = auth_info(client, headers)
    assert legacy["subscribed_capabilities"] == sorted(expected)
    assert all(
        sources == ["scene:robot_patrol"]
        for sources in legacy["capability_grant_sources"].values()
    )

    subscribe_scene(client, headers, "robot_patrol", [])
    empty = auth_info(client, headers)
    assert empty["scene_subscriptions"] == ["robot_patrol"]
    assert empty["subscribed_capabilities"] == []
    assert empty["capability_grant_sources"] == {}
    assert client.post(
        "/api/v1/capabilities/target_detection/invoke",
        headers=headers,
        json={"area": "A"},
    ).status_code == 402
    snapshot = client.get(
        "/api/v1/integration/subscriptions",
        params={"account_id": empty["account"]},
    ).json()
    assert snapshot["tools"] == []
    assert not any(
        component["standalone_entitled"]
        for component in snapshot["scene_services"][0]["components"]
    )


def test_overlapping_scene_sources_withdraw_independently_and_preserve_direct_and_plan(client):
    account, _, headers = register(client, plan="pro")
    assert client.post("/api/v1/subscribe", json={
        "account": account,
        "capability_ids": ["target_detection"],
    }).status_code == 200
    subscribe_scene(client, headers, "robot_patrol", ["target_detection"])
    subscribe_scene(client, headers, "collaborative_tracking", ["target_detection"])

    assert set(auth_info(client, headers)["capability_grant_sources"]["target_detection"]) == {
        "direct",
        "scene:robot_patrol",
        "scene:collaborative_tracking",
    }
    assert client.delete(
        "/api/v1/services/robot_patrol/subscribe", headers=headers
    ).status_code == 200
    assert set(auth_info(client, headers)["capability_grant_sources"]["target_detection"]) == {
        "direct",
        "scene:collaborative_tracking",
    }
    assert client.delete(
        "/api/v1/services/collaborative_tracking/subscribe", headers=headers
    ).status_code == 200
    assert auth_info(client, headers)["capability_grant_sources"]["target_detection"] == [
        "direct",
    ]

    query = client.get(
        "/api/v1/integration/subscriptions", params={"account_id": account}
    ).json()
    target = next(t for t in query["tools"] if t["capability_id"] == "target_detection")
    assert set(target["grant_sources"]) == {"direct", "plan:pro"}
    assert client.post(
        "/api/v1/capabilities/target_detection/invoke",
        headers=headers,
        json={"area": "A"},
    ).status_code == 200
