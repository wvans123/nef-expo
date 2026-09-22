"""Cross-machine demo lookup: exact account names, scoped metadata, no credentials."""
from datetime import datetime
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import server
from skills import CAP_INDEX, Capability

URL = "/api/v1/integration/subscriptions"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "API_KEYS", {})
    monkeypatch.setattr(server, "ACCOUNT_KEYS", {})
    monkeypatch.setattr(server, "THIRD_PARTY", [])
    with TestClient(server.app) as client:
        yield client


def register(client, account="1", plan="free"):
    response = client.post("/api/v1/register", json={"account": account, "plan": plan})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["api_key"]}


def lookup(client, account="1"):
    response = client.get(URL, params={"account_id": account})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def test_numeric_identifier_is_exact_account_name_not_registration_order(client):
    register(client, "2")
    register(client, "1")
    register(client, "01")
    client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": ["target_detection"]})
    assert lookup(client)["direct_subscriptions"] == ["target_detection"]
    assert lookup(client, "2")["tools"] == []
    assert lookup(client, "01")["tools"] == []
    register(client, "team-a")
    assert lookup(client, "team-a")["account_id"] == "team-a"


def test_empty_account_is_distinct_from_unknown_and_get_never_registers(client):
    response = client.get(URL, params={"account_id": "1"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "account_not_found"
    assert not server.API_KEYS and not server.ACCOUNT_KEYS
    register(client)
    data = lookup(client)
    assert data["storage"] == "memory" and data["schema_version"] == "1.1"
    assert datetime.fromisoformat(data["generated_at"]).utcoffset().total_seconds() == 0
    for field in ("tools", "packages", "scene_services", "purchased_packages",
                  "direct_subscriptions", "entitled_capabilities"):
        assert data[field] == []


@pytest.mark.parametrize("params", [{}, {"account_id": ""}, {"account_id": " "},
                                   {"account_id": " 1"}, {"account_id": "1 "},
                                   {"account_id": "a" * 129}])
def test_invalid_identifier(client, params):
    assert client.get(URL, params=params).status_code == 422


def test_live_snapshot_schema_and_secret_exclusion(client):
    headers = register(client)
    assert lookup(client)["tools"] == []
    client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": ["target_detection"]})
    response = client.get(URL, params={"account_id": "1"})
    data = response.json()
    tool = data["tools"][0]
    assert tool["name"] == tool["capability_id"] == "target_detection"
    assert tool["grant_sources"] == ["direct"]
    assert tool["inputSchema"] == CAP_INDEX["target_detection"].mcp_tool()["inputSchema"]
    assert data["subscribed_capabilities"] == data["entitled_capabilities"] == ["target_detection"]
    assert headers["Authorization"].split()[1] not in response.text
    for secret_field in ("api_key", "scopes", "per_call_charges", "receiver_key", "authorization"):
        assert secret_field not in data
    # Reading the public metadata never gives the caller invocation permission.
    assert client.post("/api/v1/capabilities/target_detection/invoke", json={"area": "A"}).status_code == 401


def test_package_plan_sources_are_deduplicated_and_do_not_grant_scenes(client):
    headers = register(client, plan="pro")
    assert client.post("/api/v1/subscribe", json={
        "account": "1", "capability_ids": ["target_detection"], "package_ids": ["robot_patrol"],
    }).status_code == 200
    assert client.get("/api/v1/auth/info", headers=headers).json()["capability_grant_sources"][
        "target_detection"
    ] == ["direct", "package:robot_patrol"]
    data = lookup(client)
    tool = next(t for t in data["tools"] if t["capability_id"] == "target_detection")
    assert set(tool["grant_sources"]) == {"direct", "package:robot_patrol", "plan:pro"}
    assert len({t["name"] for t in data["tools"]}) == len(data["tools"])
    assert data["packages"][0]["id"] == "robot_patrol"
    assert data["scene_subscriptions"] == [] and data["scene_services"] == []


def test_scene_selected_components_are_standalone_grants_with_scene_sources(client):
    headers = register(client)
    assert client.post("/api/v1/services/robot_patrol/subscribe", headers=headers).status_code == 200
    data = lookup(client)
    assert data["scene_subscriptions"] == ["robot_patrol"]
    assert data["direct_subscriptions"] == []
    assert data["subscribed_capabilities"] == sorted(server._scene_capability_ids("robot_patrol"))
    assert all(t["grant_sources"] == ["scene:robot_patrol"] for t in data["tools"])
    scene = data["scene_services"][0]
    assert scene["tool"] is None and scene["modes"] == ["intent"]
    assert all(c["standalone_entitled"] for c in scene["components"])
    assert client.post("/api/v1/services/robot_patrol/intent",
                       headers={**headers, "X-NEF-Execution": "demo"}, json={"text": "patrol"}).status_code == 200
    assert client.post("/api/v1/capabilities/target_detection/invoke",
                       headers=headers, json={"area": "A"}).status_code == 200
    client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": ["target_detection"]})
    target = next(t for t in lookup(client)["tools"] if t["capability_id"] == "target_detection")
    assert target["grant_sources"] == ["direct", "scene:robot_patrol"]


def test_scene_tool_has_actual_mcp_schema_without_claiming_live_execution(client, monkeypatch):
    monkeypatch.delenv("NEF_BRIDGE_CONFIG", raising=False)
    headers = register(client)
    client.post("/api/v1/services/collaborative_tracking/subscribe", headers=headers)
    scene = lookup(client)["scene_services"][0]
    assert scene["tool"]["name"] == "scene_collaborative_tracking"
    assert scene["tool"]["inputSchema"]["required"] == ["device_id", "video_source", "target"]
    assert client.post("/api/v1/services/collaborative_tracking/intent",
                       headers={**headers, "X-NEF-Execution": "live"}, json={"text": "track"}).status_code == 503


def test_unsubscribed_pay_per_call_external_tools_are_not_subscription_grants(client):
    register(client)
    cap = Capability("external_test", "External", "Provider tool", "ecosystem", "basic",
                     source="third_party", unit_price="0.5/次")
    server.THIRD_PARTY.append(cap)
    assert lookup(client)["tools"] == []
    client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": [cap.id]})
    assert lookup(client)["tools"][0]["grant_sources"] == ["direct"]


def test_openapi_documents_response_and_required_query(client):
    spec = client.get("/openapi.json").json()
    operation = spec["paths"][URL]["get"]
    parameter = next(p for p in operation["parameters"] if p["name"] == "account_id")
    assert parameter["required"] and parameter["in"] == "query"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/SubscriptionSnapshot")
    assert client.post(URL, params={"account_id": "1"}).status_code == 405


def test_restart_does_not_silently_return_another_accounts_subscription(client):
    register(client)
    client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": ["target_detection"]})
    server.API_KEYS.clear()
    server.ACCOUNT_KEYS.clear()
    register(client, "2")
    assert client.get(URL, params={"account_id": "1"}).status_code == 404
    register(client)
    assert lookup(client)["tools"] == []


def test_handoff_document_example_matches_actual_response(client):
    register(client)
    client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": ["target_detection"]})
    doc = Path("docs/reference/subscription-query.md").read_text(encoding="utf-8")
    section = doc.split("## 6. ", 1)[1].split("## 7. ", 1)[0]
    example = json.loads(section.split("```json\n", 1)[1].split("```", 1)[0])
    actual = lookup(client)
    actual["generated_at"] = example["generated_at"]
    assert actual == example


def test_purchased_packages_combine_scene_and_bundle_without_same_id_collision(client):
    headers = register(client)
    client.post("/api/v1/services/robot_patrol/subscribe", headers=headers)
    client.post("/api/v1/subscribe", json={"account": "1", "package_ids": ["robot_patrol"]})
    rows = lookup(client)["purchased_packages"]
    assert [(r["kind"], r["id"]) for r in rows] == [
        ("scene", "robot_patrol"), ("capability_package", "robot_patrol"),
    ]
    assert rows[0]["description"] == server.SCENES["robot_patrol"]["description"]
    assert rows[0]["modes"] == ["intent"] and rows[0]["intent_example"]
    assert rows[0]["tool"] is None
    assert rows[1]["modes"] == [] and rows[1]["intent_example"] is None
    assert rows[1]["description"] == server.PKG_INDEX["robot_patrol"]["description"]
    assert all(c["standalone_entitled"] for c in rows[1]["components"])
    assert "api_key" not in json.dumps(rows)


def test_plan_atomic_and_unpurchased_catalog_are_not_purchased_packages(client):
    headers = register(client, plan="max")
    client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": ["target_detection"]})
    assert lookup(client)["purchased_packages"] == []
    client.post("/api/v1/services/collaborative_tracking/subscribe", headers=headers)
    rows = lookup(client)["purchased_packages"]
    assert len(rows) == 1 and rows[0]["id"] == "collaborative_tracking"
    assert rows[0]["tool"]["name"] == "scene_collaborative_tracking"
    register(client, "2")
    assert lookup(client, "2")["purchased_packages"] == []
