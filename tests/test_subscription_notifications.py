import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import server
from test_network_registry import LocalHTTPFixture, json_response


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "API_KEYS", {})
    monkeypatch.setattr(server, "ACCOUNT_KEYS", {})
    with TestClient(server.app) as client:
        yield client


def account(client, name="1"):
    data = client.post("/api/v1/register", json={"account": name}).json()
    return {"Authorization": "Bearer " + data["api_key"]}


def configure(monkeypatch, tmp_path, peer, **extra):
    path = tmp_path / "callback.json"
    path.write_text(json.dumps({
        "callback_url": peer.url("/business/v1/service-plans"),
        "account_ids": ["1", "2"], "token_env": "TEST_PLAN_CALLBACK_KEY",
        "plan_prices": {"scene:robot_patrol": 19.9, "capability_package:robot_patrol": 39.9}, **extra,
    }), encoding="utf-8")
    monkeypatch.setenv("NEF_SUBSCRIPTION_CONFIG", str(path))
    monkeypatch.setenv("TEST_PLAN_CALLBACK_KEY", "synthetic-callback-secret")
    return path


@pytest.fixture
def peer():
    peer = LocalHTTPFixture()
    peer.add("POST", "/business/v1/service-plans", lambda r: (201, {}, b"{}"))
    try:
        yield peer
    finally:
        peer.close()


def test_purchase_posts_exact_partner_fields_and_stable_uuid(client, peer, monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, peer)
    headers = account(client)
    response = client.post("/api/v1/services/robot_patrol/subscribe", headers=headers)
    assert response.status_code == 200 and response.json()["notification"]["status"] == "delivered"
    request = peer.requests[0]
    body = json.loads(request["body"])
    assert set(body) == {"subscriberId", "servicePlan"}
    assert body["subscriberId"] == "subscriber-001"
    assert response.json()["notification"]["account_id"] == "1"
    plan = body["servicePlan"]
    assert set(plan) == {"planId", "showName", "description", "price", "networkCapabilities"}
    assert [cap["capabilityName"] for cap in plan["networkCapabilities"]] == [
        item["capability_id"] for item in server.SCENES["robot_patrol"]["provenance"]["components"]
    ]
    assert UUID(plan["planId"]).version == 5
    assert plan["showName"] == server.SCENES["robot_patrol"]["name"]
    assert plan["price"] == 19.9 and isinstance(plan["price"], float)
    assert request["headers"]["authorization"] == "Bearer synthetic-callback-secret"
    assert "synthetic-callback-secret" not in response.text
    assert "nef_" not in request["body"].decode()
    assert "account_id" not in body
    second_response = client.post("/api/v1/services/robot_patrol/subscribe", headers=account(client, "2"))
    assert second_response.json()["notification"]["account_id"] == "2"
    second = json.loads(peer.requests[1]["body"])
    assert second["subscriberId"] == "subscriber-001"
    assert second["servicePlan"]["planId"] == plan["planId"]
    client.post("/api/v1/subscribe", json={"account": "1", "package_ids": ["robot_patrol"]})
    assert json.loads(peer.requests[2]["body"])["subscriberId"] == "subscriber-001"
    assert json.loads(peer.requests[2]["body"])["servicePlan"]["planId"] != plan["planId"]
    assert json.loads(peer.requests[2]["body"])["servicePlan"]["price"] == 39.9


def test_failure_keeps_entitlement_and_retry_uses_same_event_and_payload(client, peer, monkeypatch, tmp_path):
    path = configure(monkeypatch, tmp_path, peer)
    headers = account(client)
    peer.add("POST", "/business/v1/service-plans", lambda r: (503, {}, b"synthetic-callback-secret"))
    result = client.post("/api/v1/services/robot_patrol/subscribe", headers=headers,
                         json={"network_capability_ids": ["target_detection"]}).json()
    event = result["notification"]
    assert result["subscribed"] and event["status"] == "failed" and event["attempts"] == 1
    assert client.get("/api/v1/integration/subscriptions?account_id=1").json()["scene_subscriptions"] == ["robot_patrol"]
    retry = "/api/v1/integration/notifications/" + event["event_id"] + "/retry"
    assert client.post(retry, headers=account(client, "2")).status_code == 404
    assert client.post(retry).status_code == 401
    config = json.loads(path.read_text())
    config["plan_prices"]["scene:robot_patrol"] = 500
    path.write_text(json.dumps(config))
    peer.add("POST", "/business/v1/service-plans", lambda r: json_response({"received": True}))
    assert client.post(retry, headers=headers).json()["status"] == "delivered"
    assert peer.requests[0]["body"] == peer.requests[1]["body"]
    assert json.loads(peer.requests[1]["body"])["subscriberId"] == "subscriber-001"
    assert peer.requests[0]["headers"]["idempotency-key"] == peer.requests[1]["headers"]["idempotency-key"]
    assert client.post(retry, headers=headers).json()["status"] == "delivered"
    assert len(peer.requests) == 2
    listing = client.get("/api/v1/integration/notifications", headers=headers)
    assert listing.headers["cache-control"] == "no-store"
    assert "synthetic-callback-secret" not in listing.text and peer.base_url not in listing.text


@pytest.mark.parametrize("price", [None, -1, "19.9", True, float("inf"), 10**400])
def test_price_must_be_explicit_finite_nonnegative_number(client, peer, monkeypatch, tmp_path, price):
    configure(monkeypatch, tmp_path, peer, plan_prices={"scene:robot_patrol": price})
    result = client.post("/api/v1/services/robot_patrol/subscribe", headers=account(client)).json()
    assert result["subscribed"] and result["notification"]["code"] == "price_not_configured"
    assert peer.requests == []


def test_missing_callback_can_be_configured_then_retried(client, peer, monkeypatch, tmp_path):
    headers = account(client)
    event = client.post("/api/v1/services/robot_patrol/subscribe", headers=headers).json()["notification"]
    assert event["status"] == "not_configured"
    configure(monkeypatch, tmp_path, peer)
    result = client.post("/api/v1/integration/notifications/" + event["event_id"] + "/retry", headers=headers)
    assert result.json()["status"] == "delivered"
    assert json.loads(peer.requests[0]["body"])["subscriberId"] == "subscriber-001"


def test_unapproved_account_no_callback_and_atomic_subscription_not_a_plan(client, peer, monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, peer)
    result = client.post("/api/v1/services/robot_patrol/subscribe", headers=account(client, "3")).json()
    assert result["notification"]["code"] == "account_not_enabled"
    atomic = client.post("/api/v1/subscribe", json={"account": "1", "capability_ids": ["target_detection"]})
    assert atomic.json()["notification"]["status"] == "not_applicable"
    assert peer.requests == []


def test_callback_redirect_never_forwarded(client, peer, monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, peer)
    peer.add("POST", "/business/v1/service-plans", lambda r: (302, {"Location": peer.url("/steal")}, b""))
    result = client.post("/api/v1/services/robot_patrol/subscribe", headers=account(client)).json()
    assert result["notification"]["status"] == "failed" and len(peer.requests) == 1


@pytest.mark.parametrize("extra,code", [
    ({"callback_url": "http://127.0.0.1:bad/business/v1/service-plans"}, "invalid_config"),
    ({"callback_url": "https://example.invalid/plans\n"}, "invalid_config"),
    ({"callback_url": "http://192.0.2.1/business/v1/service-plans"}, "invalid_config"),
    ({"token_env": "MISSING_TEST_CALLBACK_KEY"}, "callback_key_missing"),
])
def test_invalid_operator_settings_preserve_subscription_without_send(client, peer, monkeypatch, tmp_path, extra, code):
    monkeypatch.delenv("MISSING_TEST_CALLBACK_KEY", raising=False)
    configure(monkeypatch, tmp_path, peer, **extra)
    response = client.post("/api/v1/services/robot_patrol/subscribe", headers=account(client))
    assert response.status_code == 200
    assert response.json()["subscribed"] and response.json()["notification"]["code"] == code
    assert peer.requests == []


@pytest.mark.parametrize("legacy", [False, True])
def test_only_explicitly_selected_network_capabilities_are_sent(client, peer, monkeypatch, tmp_path, legacy):
    configure(monkeypatch, tmp_path, peer)
    headers = account(client)
    payload = {"network_capability_ids": ["target_detection", "precision_location"]}
    if legacy:
        payload.update(account="1", package_ids=["robot_patrol"])
    endpoint = "/api/v1/subscribe" if legacy else "/api/v1/services/robot_patrol/subscribe"
    assert client.post(endpoint, headers=headers, json=payload).status_code == 200
    body = json.loads(peer.requests[0]["body"])
    assert body["subscriberId"] == "subscriber-001"
    plan = body["servicePlan"]
    assert set(plan) == {"planId", "showName", "description", "price", "networkCapabilities"}
    expected = [
        {"capabilityName": cid, "showName": server.CAP_INDEX[cid].name, "description": server.CAP_INDEX[cid].description,
         "price": float(server.subscription_notifications.unit_price(cid))}
        for cid in payload["network_capability_ids"]
    ]
    assert plan["networkCapabilities"] == expected
    assert all(cap["price"] > 0 for cap in plan["networkCapabilities"])
    assert "sensing_fusion" not in [cap["capabilityName"] for cap in plan["networkCapabilities"]]


def test_explicit_empty_selection_omits_scope_for_network_planning(client, peer, monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, peer)
    assert client.post("/api/v1/services/robot_patrol/subscribe", headers=account(client),
                       json={"network_capability_ids": []}).status_code == 200
    assert "networkCapabilities" not in json.loads(peer.requests[0]["body"])["servicePlan"]


@pytest.mark.parametrize("payload", [
    {"network_capability_ids": ["unknown"]},
    {"network_capability_ids": ["ai_inference"]},
    {"network_capability_ids": ["target_detection", "target_detection"]},
    {"network_capability_ids": None},
    {"subscriberId": "2"},
])
def test_invalid_selection_or_forged_subscriber_rejected_before_purchase(client, peer, monkeypatch, tmp_path, payload):
    configure(monkeypatch, tmp_path, peer)
    response = client.post("/api/v1/services/robot_patrol/subscribe", headers=account(client), json=payload)
    assert response.status_code == 422 and peer.requests == []
    assert client.get("/api/v1/integration/subscriptions?account_id=1").json()["scene_subscriptions"] == []


def test_discount_prices_selected_capabilities_and_unsubscribe_deletes_at_partner(client, peer, monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, peer, discount=0.8, account_ids=None)
    headers = account(client, 'named-test-account')
    scenes = client.get('/api/v1/services').json()['services']
    assert [s['price'] for s in scenes] == [115.68, 119.76, 119.6]
    assert all(s['discount'] == 0.8 for s in scenes)
    event = client.post('/api/v1/services/robot_patrol/subscribe', headers=headers,
                        json={'network_capability_ids': ['target_detection']}).json()['notification']
    assert event['price'] == 15.92 and event['action'] == 'create'
    assert event['capability_ids'] == ['target_detection']
    peer.add('DELETE', '/business/v1/service-plans/'+event['plan_id'], lambda r: json_response({'removed': True}))
    response = client.delete('/api/v1/services/robot_patrol/subscribe', headers=headers)
    assert response.status_code == 200 and response.json()['subscribed'] is False
    assert response.json()['notification']['action'] == 'delete'
    assert response.json()['notification']['status'] == 'delivered'
    assert peer.requests[-1]['query'] == 'subscriberId=subscriber-001' and peer.requests[-1]['body'] == b''
    assert client.delete('/api/v1/services/robot_patrol/subscribe', headers=headers).status_code == 404
    assert client.post('/api/v1/services/robot_patrol/result', headers=headers).status_code == 403


def test_notify_plans_limits_farm_notifications_to_listed_plans(client, peer, monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, peer, discount=0.8, notify_plans=['scene:collaborative_tracking'])
    headers = account(client)
    event = client.post('/api/v1/services/robot_patrol/subscribe', headers=headers).json()['notification']
    assert event['code'] == 'plan_not_enabled' and not peer.requests
    assert client.post('/api/v1/services/collaborative_tracking/subscribe', headers=headers).json()['notification']['status'] == 'delivered'
    assert len(peer.requests) == 1


def test_operator_sees_request_reply_and_idempotent_partner_errors(client, peer, monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, peer)
    peer.add('POST', '/business/v1/service-plans', lambda r: (400, {}, b'{"errorCode":2053,"message":"SERVICE_PLAN_ALREADY_EXISTS"}'))
    headers = account(client)
    event = client.post('/api/v1/services/robot_patrol/subscribe', headers=headers).json()['notification']
    assert event['status'] == 'delivered' and event['code'] == 'already_exists'
    assert event['request']['method'] == 'POST' and event['response']['http_status'] == 400
    assert event['response']['body']['errorCode'] == 2053
    assert 'Authorization' not in event['request']['headers'] and peer.base_url not in json.dumps(event)
    peer.add('DELETE', '/business/v1/service-plans/'+event['plan_id'], lambda r: (404, {}, b'{"errorCode":2051}'))
    deleted = client.delete('/api/v1/services/robot_patrol/subscribe', headers=headers).json()['notification']
    assert deleted['status'] == 'delivered' and deleted['code'] == 'not_found'


def test_startup_reset_is_opt_in_and_deletes_every_scene_plan(peer, monkeypatch, tmp_path):
    path = configure(monkeypatch, tmp_path, peer)
    assert server.subscription_notifications.reset_partner_plans() == [] and peer.requests == []
    cfg = json.loads(path.read_text());cfg['reset_partner_plans_on_start'] = True
    path.write_text(json.dumps(cfg))
    for sid in server.SCENES:
        peer.add('DELETE', '/business/v1/service-plans/'+server.subscription_notifications.scene_plan_id(sid), lambda r: json_response({}))
    with TestClient(server.app):
        pass
    assert len(peer.requests) == 3
    assert all(r['method'] == 'DELETE' and r['query'] == 'subscriberId=subscriber-001' for r in peer.requests)


@pytest.mark.parametrize('discount',[0,-1,1.1,True,'0.8',float('inf')])
def test_invalid_discount_never_sends(client, peer, monkeypatch, tmp_path, discount):
    configure(monkeypatch, tmp_path, peer, discount=discount)
    result=client.post('/api/v1/services/robot_patrol/subscribe',headers=account(client)).json()
    assert result['notification']['code']=='invalid_config' and peer.requests==[]
