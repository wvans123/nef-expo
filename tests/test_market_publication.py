"""Explicit publication, public projection and TRF withdrawal over local HTTP."""
import json
from test_network_registry import (
    client, clean_state, http_fixture, configure, headers, register_server,
    install_mcp_fixture, tool, json_response,
)


def discovered(client, peer, monkeypatch, **config):
    url = peer.url("/mcp")
    install_mcp_fixture(peer, "/mcp", pages=[{"tools": [tool("patrol_inspect")]}])
    cfg = configure(monkeypatch, mcp_servers={url: {}}, **config)
    record = register_server(client, url)
    path = "/api/v1/network/servers/" + record["id"]
    assert client.post(path + "/discover", headers=headers()).status_code == 200
    return path, record, cfg


def test_draft_hidden_publish_visible_to_customers_unpublish_hides(client, http_fixture, monkeypatch):
    path, record, cfg = discovered(client, http_fixture, monkeypatch)
    assert client.get("/api/v1/network/market").json()["items"] == []
    assert client.post(path+"/publish", headers=headers("caller-b")).status_code == 404
    result = client.post(path+"/publish", headers=headers()).json()
    assert result["publication_status"] == "published" and result["sync_status"] == "pending"
    market = client.get("/api/v1/network/market").json()
    assert market["items"][0]["id"] == record["id"] + ":patrol_inspect"
    public_text = json.dumps(market)
    assert "source_account" not in public_text and http_fixture.url("/mcp") not in public_text
    assert client.post(path+"/discover", headers=headers()).status_code == 409
    monkeypatch.setenv("MARKET_TEST_KEY", "network-test")
    cfg["network_clients"] = {"nw": {"token_env": "MARKET_TEST_KEY", "af_accounts": ["account-a"]}}
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", json.dumps(cfg))
    gateway = "/api/v1/network/af-servers/" + record["id"] + "/mcp"
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post(gateway, headers={"Authorization":"Bearer network-test"}, json=request).status_code == 200
    result = client.post(path+"/unpublish", headers=headers()).json()
    assert result["publication_status"] == "unpublished" and result["sync_status"] == "not_required"
    assert client.get("/api/v1/network/market").json()["items"] == []
    assert client.post(gateway, headers={"Authorization":"Bearer network-test"}, json=request).status_code == 409
    assert not any(r["path"] == "/publish" for r in http_fixture.requests)


def test_trf_failure_withdrawal_and_retry_do_not_republish_locally(client, http_fixture, monkeypatch):
    path, record, cfg = discovered(client, http_fixture, monkeypatch, publish_url=http_fixture.url("/publish"))
    http_fixture.add("POST", "/publish", lambda r: (503, {}, b"temporarily unavailable"))
    failed = client.post(path+"/publish", headers=headers()).json()
    assert failed["publication_status"] == "published" and failed["sync_status"] == "failed"
    assert failed["trf_may_exist"]
    body = json.loads(http_fixture.requests[-1]["body"])
    assert body["type"] == "mcp_server_registration" and body["server"]["tools"][0]["name"] == "patrol_inspect"
    assert body["server"]["url"].startswith("http://nef.test:8069/api/v1/network/af-servers/")
    removed = client.post(path+"/unpublish", headers=headers()).json()
    assert removed["publication_status"] == "unpublished" and removed["trf_may_exist"]
    assert removed["sync_status"] == "pending"
    cfg["withdraw_url"] = http_fixture.url("/withdraw")
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", json.dumps(cfg))
    http_fixture.add("POST", "/withdraw", lambda r: json_response({"accepted":False}))
    submitted = client.post(path+"/unpublish", headers=headers()).json()
    assert submitted["sync_status"] == "submitted" and submitted["trf_may_exist"]
    assert client.get("/api/v1/network/market").json()["items"] == []
    http_fixture.add("POST", "/withdraw", lambda r: json_response({"accepted":True}))
    confirmed = client.post(path+"/unpublish", headers=headers()).json()
    assert confirmed["sync_status"] == "synced" and not confirmed["trf_may_exist"]
    assert json.loads(http_fixture.requests[-1]["body"]) == {
        "type":"mcp_server_withdrawal", "registration_id":record["id"], "account":"account-a"
    }


def test_package_draft_only_enters_market_after_explicit_publish(client, http_fixture, monkeypatch):
    configure(monkeypatch)
    package = client.post("/api/v1/network/packages", headers=headers(), json={
        "name":"Inspection plan", "description":"local test", "execution_target":"network",
        "steps":[{"capability_id":"target_detection"}],
    }).json()
    assert package["publication_status"] == "draft"
    assert client.get("/api/v1/network/market").json()["items"] == []
    path = "/api/v1/network/packages/" + package["id"]
    assert client.post(path+"/publish", headers=headers()).json()["publication_status"] == "published"
    assert client.get("/api/v1/network/market").json()["items"][0]["name"] == "Inspection plan"
    assert client.post(path+"/unpublish", headers=headers()).status_code == 200
    assert client.get("/api/v1/network/market").json()["items"] == []
