# -*- coding: utf-8 -*-
"""Published external MCP tools can be explicitly subscribed and invoked."""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

import network_registry
import server
from test_network_registry import LocalHTTPFixture, json_response


@pytest.fixture
def client(monkeypatch):
    network_registry.reset_state_for_tests()
    monkeypatch.setattr(server, "API_KEYS", {})
    monkeypatch.setattr(server, "ACCOUNT_KEYS", {})
    monkeypatch.setattr(server, "PER_CALL_BILLS", {})
    monkeypatch.delenv("NEF_REGISTRY_CONFIG", raising=False)
    with TestClient(server.app) as test_client:
        yield test_client
    network_registry.reset_state_for_tests()


@pytest.fixture
def peer():
    fixture = LocalHTTPFixture()
    try:
        yield fixture
    finally:
        fixture.close()


def register(client: TestClient, account: str, plan: str = "free"):
    response = client.post("/api/v1/register", json={"account": account, "plan": plan})
    assert response.status_code == 200, response.text
    return {
        "Authorization": "Bearer " + response.json()["api_key"]
    }, response.json()["api_key"]


def install_external_mcp(peer, path, *, tool_name="inspect", is_error=False):
    calls = []
    schema = {
        "type": "object",
        "properties": {"frame": {"type": "string"}},
        "required": ["frame"],
        "additionalProperties": False,
    }
    tool = {
        "name": tool_name,
        "description": f"External {tool_name}",
        "inputSchema": schema,
    }

    def mcp(request):
        message = json.loads(request["body"])
        calls.append((message, request["headers"]))
        method = message.get("method")
        if method == "initialize":
            status, headers, body = json_response({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "protocolVersion": network_registry.MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": path, "version": "1.0"},
                },
            })
            return status, {**headers, "Mcp-Session-Id": "market-session"}, body
        if method == "notifications/initialized":
            return 202, {}, b""
        if method == "tools/list":
            return json_response({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"tools": [tool]},
            })
        if method == "tools/call":
            return json_response({
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "content": [{
                        "type": "text",
                        "text": f"{path}:{message['params']['arguments']['frame']}",
                    }],
                    "isError": is_error,
                },
            })
        raise AssertionError(f"unexpected method: {method}")

    peer.add("POST", path, mcp)
    return tool, calls


def configure(monkeypatch, peer, paths, *, network_token=False):
    monkeypatch.setenv("MARKET_AF_TOKEN", "server-side-af-secret")
    config = {
        "trf_mcp_servers_url": None,
        "publish_url": None,
        "withdraw_url": None,
        "token_env": None,
        "nef_base_url": None,
        "mcp_servers": {
            peer.url(path): {"token_env": "MARKET_AF_TOKEN"} for path in paths
        },
        "network_clients": {},
    }
    if network_token:
        monkeypatch.setenv("MARKET_NETWORK_TOKEN", "network-client-secret")
        config["network_clients"] = {
            "legacy-agent": {
                "token_env": "MARKET_NETWORK_TOKEN",
                "af_accounts": ["publisher-a"],
            }
        }
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", json.dumps(config))
    return config


def publish_server(client, headers, peer, path, server_name):
    registered = client.post(
        "/api/v1/network/servers",
        headers=headers,
        json={
            "serverName": server_name,
            "url": peer.url(path),
            "description": f"{server_name} description",
        },
    )
    assert registered.status_code == 200, registered.text
    server_id = registered.json()["id"]
    base = f"/api/v1/network/servers/{server_id}"
    assert client.post(base + "/discover", headers=headers).status_code == 200
    published = client.post(base + "/publish", headers=headers)
    assert published.status_code == 200
    assert published.json()["publication_status"] == "published"
    return server_id, base


def rpc(client, endpoint, headers, name, frame="f-1", *, include_id=True):
    body = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": name, "arguments": {"frame": frame}},
    }
    if include_id:
        body["id"] = "rpc-1"
    return client.post(endpoint, headers=headers, json=body)


def test_account_subscription_enables_both_rpc_entries_and_preserves_is_error(
    client, peer, monkeypatch
):
    tool, calls = install_external_mcp(peer, "/af", is_error=True)
    configure(monkeypatch, peer, ["/af"])
    publisher, _ = register(client, "publisher-a", plan="max")
    subscriber, subscriber_key = register(client, "subscriber-b", plan="pro")
    outsider, _ = register(client, "outsider-c", plan="max")
    server_id, _ = publish_server(
        client, publisher, peer, "/af", "shared-inspection"
    )

    market = client.get("/api/v1/network/market").json()["items"]
    item = next(row for row in market if row["id"] == f"{server_id}:{tool['name']}")
    assert item["price"] == 0 and item["billing"] == "demo_free"
    assert item["mcp_name"].startswith(f"external_{server_id}_")
    assert len(item["mcp_name"]) <= 64

    before = len(calls)
    assert rpc(
        client, "/api/v1/mcp/tools/call", publisher, item["mcp_name"]
    ).status_code == 403
    assert rpc(client, "/mcp", outsider, item["mcp_name"]).status_code == 403
    assert len(calls) == before

    subscribed = client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    )
    assert subscribed.json() == {
        "subscribed": True,
        "tool_id": item["id"],
        "billing": "demo_free",
    }
    again = client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    )
    assert again.json() == subscribed.json()

    listed = client.post(
        "/api/v1/mcp/tools/list",
        headers=subscriber,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    ).json()["result"]["tools"]
    external = next(row for row in listed if row["name"] == item["mcp_name"])
    assert external["title"] == tool["name"]
    assert external["serverName"] == item["serverName"]
    assert external["inputSchema"] == tool["inputSchema"]
    assert external["subscribed"] is True

    api_result = rpc(
        client,
        "/api/v1/mcp/tools/call",
        subscriber,
        item["mcp_name"],
        "api",
    )
    assert api_result.status_code == 200
    assert api_result.json()["result"]["isError"] is True
    mcp_result = rpc(client, "/mcp", subscriber, item["mcp_name"], "mcp")
    assert mcp_result.status_code == 200
    assert mcp_result.json()["result"]["content"][0]["text"] == "/af:mcp"
    outbound = calls[before:]
    assert [message["method"] for message, _headers in outbound] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    assert all(
        request_headers["authorization"] == "Bearer server-side-af-secret"
        for _message, request_headers in outbound
    )
    assert all(subscriber_key not in json.dumps(headers) for _message, headers in outbound)


def test_cancel_unpublish_republish_delete_scope_and_snapshots(
    client, peer, monkeypatch
):
    _tool, calls = install_external_mcp(peer, "/lifecycle")
    configure(monkeypatch, peer, ["/lifecycle"])
    publisher, _ = register(client, "publisher-a")
    subscriber, subscriber_key = register(client, "subscriber-b")
    server_id, base = publish_server(
        client, publisher, peer, "/lifecycle", "lifecycle-server"
    )
    item = client.get("/api/v1/network/market").json()["items"][0]

    record = server.API_KEYS[subscriber_key]
    record["scopes"].discard("capabilities:invoke")
    assert client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    ).status_code == 403
    assert client.get(
        "/api/v1/network/market/subscriptions", headers=subscriber
    ).status_code == 200
    record["scopes"].add("capabilities:invoke")
    assert client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    ).status_code == 200
    assert client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"], "account": "publisher-a"},
    ).status_code == 422

    subscription = client.get(
        "/api/v1/network/market/subscriptions", headers=subscriber
    ).json()["subscriptions"][0]
    assert subscription["available"] is True
    secret_text = json.dumps(subscription)
    assert peer.url("/lifecycle") not in secret_text
    assert "server-side-af-secret" not in secret_text

    assert client.post(base + "/unpublish", headers=publisher).status_code == 200
    unavailable = client.get(
        "/api/v1/network/market/subscriptions", headers=subscriber
    ).json()["subscriptions"][0]
    assert unavailable["available"] is False
    before = len(calls)
    unavailable_call = rpc(client, "/mcp", subscriber, item["mcp_name"])
    assert unavailable_call.status_code == 200
    unavailable_result = unavailable_call.json()["result"]
    assert unavailable_result["isError"] is True
    unavailable_detail = json.loads(unavailable_result["content"][0]["text"])
    assert unavailable_detail["http_status"] == 409
    assert client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    ).status_code == 409
    assert len(calls) == before

    assert client.post(base + "/publish", headers=publisher).status_code == 200
    assert client.get(
        "/api/v1/network/market/subscriptions", headers=subscriber
    ).json()["subscriptions"][0]["available"] is True

    record["scopes"].discard("capabilities:invoke")
    assert client.request(
        "DELETE",
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    ).status_code == 403
    record["scopes"].add("capabilities:invoke")

    auth_info = client.get("/api/v1/auth/info", headers=subscriber).json()
    query = client.get(
        "/api/v1/integration/subscriptions",
        params={"account_id": "subscriber-b"},
    ).json()
    for snapshot in (
        auth_info["external_tool_subscriptions"][0],
        query["external_tool_subscriptions"][0],
    ):
        assert snapshot["id"] == item["id"]
        snapshot_text = json.dumps(snapshot)
        assert peer.url("/lifecycle") not in snapshot_text
        assert "server-side-af-secret" not in snapshot_text
    assert query["schema_version"] == "1.1"

    assert client.request(
        "DELETE",
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    ).json()["subscribed"] is False
    assert rpc(
        client, "/api/v1/mcp/tools/call", subscriber, item["mcp_name"]
    ).status_code == 403
    assert len(calls) == before

    client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    )
    client.post(base + "/unpublish", headers=publisher)
    assert client.delete(base, headers=publisher).status_code == 200
    assert client.get(
        "/api/v1/network/market/subscriptions", headers=subscriber
    ).json() == {"subscriptions": []}

    auth_info = client.get("/api/v1/auth/info", headers=subscriber).json()
    query = client.get(
        "/api/v1/integration/subscriptions",
        params={"account_id": "subscriber-b"},
    ).json()
    assert auth_info["external_tool_subscriptions"] == []
    assert query["external_tool_subscriptions"] == []
    assert query["schema_version"] == "1.1"


def test_same_tool_name_isolated_notification_no_call_and_legacy_gateway_unchanged(
    client, peer, monkeypatch
):
    _tool_a, calls_a = install_external_mcp(peer, "/a", tool_name="same")
    _tool_b, calls_b = install_external_mcp(peer, "/b", tool_name="same")
    configure(monkeypatch, peer, ["/a", "/b"], network_token=True)
    publisher, _ = register(client, "publisher-a")
    subscriber, _ = register(client, "subscriber-b")
    first_id, _ = publish_server(client, publisher, peer, "/a", "server-a")
    second_id, _ = publish_server(client, publisher, peer, "/b", "server-b")
    market = {
        item["server_id"]: item
        for item in client.get("/api/v1/network/market").json()["items"]
        if item["kind"] == "tool"
    }
    assert market[first_id]["mcp_name"] != market[second_id]["mcp_name"]
    client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": market[first_id]["id"]},
    )

    before_b = len(calls_b)
    assert rpc(
        client, "/mcp", subscriber, market[second_id]["mcp_name"]
    ).status_code == 403
    assert len(calls_b) == before_b

    before_a = len(calls_a)
    notification = rpc(
        client,
        "/mcp",
        subscriber,
        market[first_id]["mcp_name"],
        include_id=False,
    )
    assert notification.status_code == 202
    assert len(calls_a) == before_a
    api_notification = rpc(
        client,
        "/api/v1/mcp/tools/call",
        subscriber,
        market[first_id]["mcp_name"],
        include_id=False,
    )
    assert api_notification.status_code == 202
    assert len(calls_a) == before_a

    gateway = f"/api/v1/network/af-servers/{first_id}/mcp"
    legacy = client.post(
        gateway,
        headers={"Authorization": "Bearer network-client-secret"},
        json={
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "same", "arguments": {"frame": "legacy"}},
        },
    )
    assert legacy.status_code == 200
    assert legacy.json()["result"]["content"][0]["text"] == "/a:legacy"


def test_subscribed_external_tool_can_be_declared_in_package_only_while_available(
    client, peer, monkeypatch
):
    install_external_mcp(peer, "/compose")
    configure(monkeypatch, peer, ["/compose"])
    publisher, _ = register(client, "publisher-a")
    subscriber, _ = register(client, "subscriber-b")
    outsider, _ = register(client, "outsider-c")
    _server_id, base = publish_server(
        client, publisher, peer, "/compose", "compose-server"
    )
    item = client.get("/api/v1/network/market").json()["items"][0]
    client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    )
    payload = {
        "name": "external declaration",
        "steps": [{"capability_id": item["id"]}],
        "execution_target": "network",
    }
    assert client.post(
        "/api/v1/network/packages", headers=subscriber, json=payload
    ).status_code == 200
    assert client.post(
        "/api/v1/network/packages", headers=outsider, json=payload
    ).status_code == 422
    client.post(base + "/unpublish", headers=publisher)
    assert client.post(
        "/api/v1/network/packages", headers=subscriber, json=payload
    ).status_code == 422


def test_subscribed_call_checks_scope_schema_and_current_allowlist_before_outbound(
    client, peer, monkeypatch
):
    _tool, calls = install_external_mcp(peer, "/guarded")
    configure(monkeypatch, peer, ["/guarded"])
    publisher, _ = register(client, "publisher")
    subscriber, key = register(client, "subscriber")
    publish_server(client, publisher, peer, "/guarded", "guarded-server")
    item = client.get("/api/v1/network/market").json()["items"][0]
    assert client.post(
        "/api/v1/network/market/subscriptions",
        headers=subscriber,
        json={"tool_id": item["id"]},
    ).status_code == 200
    before = len(calls)
    server.API_KEYS[key]["scopes"].discard("mcp:tools")
    for endpoint in ("/mcp", "/api/v1/mcp/tools/call"):
        assert rpc(client, endpoint, subscriber, item["mcp_name"]).status_code == 403
    server.API_KEYS[key]["scopes"].add("mcp:tools")
    invalid = rpc(client, "/api/v1/mcp/tools/call", subscriber, item["mcp_name"], 123)
    assert invalid.status_code == 422
    config = json.loads(os.environ["NEF_REGISTRY_CONFIG"])
    config["mcp_servers"] = {}
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", json.dumps(config))
    denied = rpc(client, "/mcp", subscriber, item["mcp_name"])
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "not_approved"
    assert len(calls) == before
