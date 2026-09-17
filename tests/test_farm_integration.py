"""Farm handoff rehearsal over real TCP with explicitly simulated farm/directory peers."""
import json
import socket
import threading
import time

import httpx
import uvicorn

import network_registry
import server
from test_network_registry import LocalHTTPFixture, MCP_PROTOCOL_VERSION, json_response


def test_farm_purchase_registration_publication_and_network_call(monkeypatch):
    monkeypatch.setattr(server, "API_KEYS", {})
    monkeypatch.setattr(server, "ACCOUNT_KEYS", {})
    monkeypatch.setattr(network_registry, "_ACCOUNTS", {})
    monkeypatch.setattr(network_registry, "_CATALOGS", {})
    monkeypatch.setenv("FARM_TEST_AF_TOKEN", "test-farm-only")
    monkeypatch.setenv("FARM_TEST_NW_TOKEN", "test-network-only")
    monkeypatch.setenv("FARM_TEST_DIRECTORY_TOKEN", "test-directory-only")
    farm = LocalHTTPFixture()
    directory = LocalHTTPFixture()
    calls, publications = [], []
    tool = {
        "name": "get_field_status", "description": "Read simulated field status",
        "inputSchema": {"type": "object", "properties": {"field_id": {"type": "string"}},
                        "required": ["field_id"], "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    }

    def farm_mcp(request):
        assert request["headers"]["authorization"] == "Bearer test-farm-only"
        message = json.loads(request["body"])
        calls.append(message)
        if message["method"] == "initialize":
            status, headers, body = json_response({
                "jsonrpc": "2.0", "id": message["id"], "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}}, "serverInfo": {"name": "simulated-farm", "version": "1.0"},
                },
            })
            return status, {**headers, "Mcp-Session-Id": "test-farm-session"}, body
        assert request["headers"]["mcp-session-id"] == "test-farm-session"
        if message["method"] == "notifications/initialized":
            return 202, {}, b""
        if message["method"] == "tools/list":
            result = {"tools": [tool]}
        else:
            assert message["method"] == "tools/call"
            assert message["params"]["name"] == "get_field_status"
            result = {"content": [{"type": "text", "text": json.dumps({
                "data_source": "mock", "field_id": message["params"]["arguments"]["field_id"],
                "summary": "Simulated field observation; no real farm action",
            })}], "isError": False}
        return json_response({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def publish(request):
        assert request["headers"]["authorization"] == "Bearer test-directory-only"
        publications.append(json.loads(request["body"]))
        return json_response({"accepted": True})

    farm.add("POST", "/mcp", farm_mcp)
    directory.add("POST", "/publish", publish)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(32)
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", json.dumps({
        "publish_url": directory.url("/publish"), "token_env": "FARM_TEST_DIRECTORY_TOKEN",
        "nef_base_url": base,
        "mcp_servers": {farm.url("/mcp"): {"token_env": "FARM_TEST_AF_TOKEN"}},
        "network_clients": {"test-network": {"token_env": "FARM_TEST_NW_TOKEN", "af_accounts": ["1"]}},
    }))
    host = uvicorn.Server(uvicorn.Config(server.app, log_level="error", access_log=False))
    worker = threading.Thread(target=host.run, kwargs={"sockets": [sock]}, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not host.started and worker.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert host.started
        with httpx.Client(base_url=base, trust_env=False, timeout=5) as client:
            account = client.post("/api/v1/register", json={"account": "1"}).json()
            af_headers = {"Authorization": "Bearer " + account["api_key"]}
            second = client.post("/api/v1/register", json={"account": "2"}).json()
            second_headers = {"Authorization": "Bearer " + second["api_key"]}
            assert client.post("/api/v1/services/robot_patrol/subscribe", headers=af_headers).status_code == 200
            snapshot = client.get("/api/v1/integration/subscriptions", params={"account_id": "1"})
            assert snapshot.status_code == 200
            purchased = snapshot.json()["purchased_packages"]
            assert len(purchased) == 1 and purchased[0]["kind"] == "scene"
            assert purchased[0]["id"] == "robot_patrol" and purchased[0]["description"]
            assert not any(c["standalone_entitled"] for c in purchased[0]["components"])
            assert account["api_key"] not in snapshot.text
            assert client.get("/api/v1/integration/subscriptions", params={"account_id": "2"}).json()["purchased_packages"] == []

            body = {"name": "Farm integration rehearsal", "url": farm.url("/mcp"),
                    "description": "SIMULATED read-only farm tool"}
            assert client.post("/api/v1/network/servers", json=body).status_code == 401
            registered = client.post("/api/v1/network/servers", json=body, headers=af_headers)
            assert registered.status_code == 200
            record = registered.json()
            assert record["source_account"] == "1" and record["registration_status"] == "registered"
            path = "/api/v1/network/servers/" + record["id"]
            discovered = client.post(path + "/discover", headers=af_headers)
            assert discovered.status_code == 200 and discovered.json()["discovery_status"] == "discovered"
            assert discovered.json()["tools"] == [tool]
            preview = client.get(path + "/publication", headers=af_headers).json()
            synced = client.post(path + "/sync", headers=af_headers)
            assert synced.status_code == 200 and synced.json()["sync_status"] == "synced"
            assert synced.json()["accepted"] is True
            assert publications == [preview]
            assert preview["source_account"] == "1" and preview["server"]["access_via"] == "NEF"
            gateway = record["gateway_path"]
            assert preview["server"]["url"] == base + gateway
            assert farm.url("/mcp") not in json.dumps(preview)

            nw_headers = {"Authorization": "Bearer test-network-only"}

            def rpc(method, params=None):
                return client.post(gateway, headers=nw_headers, json={
                    "jsonrpc": "2.0", "id": 1, "method": method, "params": params or {},
                })

            assert rpc("initialize", {"protocolVersion": MCP_PROTOCOL_VERSION}).json()["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
            assert client.post(gateway, headers=nw_headers, json={
                "jsonrpc": "2.0", "method": "notifications/initialized",
            }).status_code == 202
            assert rpc("tools/list").json()["result"]["tools"] == [tool]
            result = rpc("tools/call", {"name": "get_field_status", "arguments": {"field_id": "F1"}})
            assert result.status_code == 200 and result.json()["result"]["isError"] is False
            observed = json.loads(result.json()["result"]["content"][0]["text"])
            assert observed["data_source"] == "mock" and observed["field_id"] == "F1"
            prior_calls = len(calls)
            bad = rpc("tools/call", {"name": "get_field_status", "arguments": {"field_id": 1}})
            assert bad.json()["error"]["code"] == -32602 and len(calls) == prior_calls
            assert client.post(gateway, headers=af_headers, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/list",
            }).status_code == 401
            assert client.get(path + "/publication", headers=second_headers).status_code == 404
            saved = client.get("/api/v1/network/servers", headers=af_headers).json()["servers"][0]
            assert saved["last_call"]["status"] == "returned"
            assert saved["last_call"]["caller"] == "test-network"
            print("\nFarm rehearsal: purchased package -> registered -> discovered -> "
                  "directory accepted -> network via NEF -> read-only farm result: PASS. "
                  "All peers local; farm and directory simulated; no production writes.")
    finally:
        host.should_exit = True
        worker.join(timeout=10)
        sock.close()
        farm.close()
        directory.close()
        assert not worker.is_alive()
