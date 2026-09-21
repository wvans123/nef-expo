# -*- coding: utf-8 -*-
"""Bounded network registry API tests using a real local HTTP fixture."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Callable

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from network_registry import (
    CAPABILITIES,
    MCP_PROTOCOL_VERSION,
    build_router,
    reset_state_for_tests,
)


CALLER_KEYS = {
    "caller-a": {"account": "account-a", "scopes": {"af:register", "pipeline:manage"}},
    "caller-b": {"account": "account-b", "scopes": {"af:register", "pipeline:manage"}},
    "caller-af": {"account": "account-af", "scopes": {"af:register"}},
    "caller-list": {"account": "account-list", "scopes": set()},
}


def fake_auth(authorization: str | None, required_scope: str | None = None):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing authorization")
    key = authorization.removeprefix("Bearer ").strip()
    record = CALLER_KEYS.get(key)
    if record is None:
        raise HTTPException(401, "invalid authorization")
    if required_scope and required_scope not in record["scopes"]:
        raise HTTPException(403, "missing scope")
    return key, record


class LocalHTTPFixture:
    """Small real TCP HTTP fixture; callbacks return status, headers, body."""

    def __init__(self):
        self.routes: dict[tuple[str, str], Callable[[dict[str, Any]], tuple[int, dict[str, str], bytes]]] = {}
        self.requests: list[dict[str, Any]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                outer.handle(self, "GET")

            def do_POST(self):  # noqa: N802
                outer.handle(self, "POST")

            def do_DELETE(self):
                outer.handle(self, "DELETE")

            def log_message(self, *_args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def url(self, path: str) -> str:
        return self.base_url + path

    def add(self, method: str, path: str, callback: Callable[[dict[str, Any]], tuple[int, dict[str, str], bytes]]):
        self.routes[(method.upper(), path)] = callback

    def handle(self, request, method: str):
        length = int(request.headers.get("content-length", "0"))
        body = request.rfile.read(length)
        entry = {
            "method": method,
            "path": urlsplit(request.path).path,
            "query": urlsplit(request.path).query,
            "headers": {key.lower(): value for key, value in request.headers.items()},
            "body": body,
        }
        self.requests.append(entry)
        callback = self.routes.get((method, entry["path"]))
        if callback is None:
            status, headers, response_body = 404, {}, b"not found"
        else:
            status, headers, response_body = callback(entry)
        response_body = response_body if isinstance(response_body, bytes) else str(response_body).encode()
        request.send_response(status)
        sent_headers = {key.lower(): value for key, value in headers.items()}
        if "content-type" not in sent_headers:
            sent_headers["content-type"] = "application/json"
        sent_headers["content-length"] = str(len(response_body))
        sent_headers["connection"] = "close"
        for key, value in sent_headers.items():
            request.send_header(key, value)
        request.end_headers()
        if response_body:
            request.wfile.write(response_body)
        request.close_connection = True

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    reset_state_for_tests()
    monkeypatch.delenv("NEF_REGISTRY_CONFIG", raising=False)
    monkeypatch.delenv("NEF_REGISTRY_TOKEN", raising=False)
    monkeypatch.delenv("NEF_MCP_TOKEN", raising=False)
    yield
    reset_state_for_tests()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(build_router(fake_auth))
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def http_fixture():
    fixture = LocalHTTPFixture()
    try:
        yield fixture
    finally:
        fixture.close()


def headers(key: str = "caller-a") -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


def configure(monkeypatch, *, catalog_url=None, publish_url=None, mcp_servers=None, token_env=None):
    config = {
        "catalog_url": catalog_url,
        "publish_url": publish_url,
        "token_env": token_env,
        "mcp_servers": mcp_servers or {},
        "nef_base_url": "http://nef.test:8069",
    }
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", json.dumps(config))
    return config


def json_response(value: Any, *, content_type: str = "application/json"):
    return 200, {"Content-Type": content_type}, json.dumps(value).encode("utf-8")


def mcp_message(message: dict[str, Any], *, content_type: str = "application/json"):
    return json_response(message, content_type=content_type)


def sse_message(message: dict[str, Any]):
    body = f"data: {json.dumps(message)}\n\n".encode("utf-8")
    return 200, {"Content-Type": "text/event-stream"}, body


def tool(name: str, description: str = "A bounded test tool") -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": [],
        },
    }


def install_mcp_fixture(fixture: LocalHTTPFixture, path: str, *, pages, init_response=None):
    calls: list[dict[str, Any]] = []

    def mcp(request):
        message = json.loads(request["body"].decode("utf-8"))
        calls.append(message)
        method = message.get("method")
        if method == "initialize":
            result = init_response or {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture-mcp", "version": "1.0"},
                },
            }
            return json_response(result)
        if method == "notifications/initialized":
            return 202, {}, b""
        if method == "tools/list":
            cursor = message.get("params", {}).get("cursor")
            page_index = 0 if cursor is None else int(cursor.removeprefix("page-"))
            response = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": pages[page_index],
            }
            if pages[page_index].get("_sse"):
                response["result"] = {key: value for key, value in pages[page_index].items() if key != "_sse"}
                return sse_message(response)
            return json_response(response)
        return 400, {}, b"{}"

    fixture.add("POST", path, mcp)
    return calls


def register_server(client: TestClient, url: str, *, key: str = "caller-a") -> dict[str, Any]:
    response = client.post(
        "/api/v1/network/servers",
        headers=headers(key),
        json={"name": "Fixture MCP", "url": url, "description": "bounded fixture"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_open_registration_discovers_waits_for_publish_and_is_shared(client, http_fixture, monkeypatch):
    url = http_fixture.url('/mcp')
    calls = install_mcp_fixture(http_fixture, '/mcp', pages=[{'tools': [tool('inspect')]}])
    http_fixture.add('POST','/publish',lambda r:json_response({'accepted': True}))
    cfg = configure(monkeypatch, publish_url=http_fixture.url('/publish'), mcp_servers={url:{}})
    cfg['open_registration_account']='1'
    monkeypatch.setenv('NEF_REGISTRY_CONFIG',json.dumps(cfg))
    payload={'name':'Farm','url':url,'description':'Open registration'}
    response=client.post('/api/v1/af/mcp-servers',json=payload)
    assert response.status_code==200,response.text
    result=response.json();sid=result['id']
    assert result['created'] and result['discovery_status']=='ok' and result['sync_status']=='pending'
    assert client.get('/api/v1/network/market').json()['items']==[]
    assert not any(r['path']=='/publish' for r in http_fixture.requests)
    assert [c['method'] for c in calls]==['initialize','notifications/initialized','tools/list']
    assert result['registered_via']=='open'
    again=client.post('/api/v1/af/mcp-servers',json={**payload,'name':'Updated'}).json()
    assert again['id']==sid and not again['created']
    for key in ['caller-a','caller-b']:
        listing=client.get('/api/v1/network/servers',headers=headers(key)).json()['servers']
        assert len(listing)==1 and listing[0]['name']=='Updated'
        assert client.post(f'/api/v1/network/servers/{sid}/discover',headers=headers(key)).status_code==200
        publication=client.get(f'/api/v1/network/servers/{sid}/publication',headers=headers(key)).json()
        assert publication['source_account']=='1'
        assert client.post(f'/api/v1/network/servers/{sid}/sync',headers=headers(key)).status_code==200
        assert client.post(f'/api/v1/network/servers/{sid}/unpublish',headers=headers(key)).status_code==200
    private=register_server(client,url)
    assert client.get(f"/api/v1/network/servers/{private['id']}/publication",headers=headers('caller-b')).status_code==404


def test_open_registration_allowlist_and_unreachable_records_survive(client,http_fixture,monkeypatch):
    url=http_fixture.url('/mcp')
    cfg=configure(monkeypatch)
    denied=client.post('/api/v1/af/mcp-servers',json={'name':'Farm','url':url})
    assert denied.status_code in (403,503) and not http_fixture.requests
    sid=denied.json()['detail']['id']
    cfg['allow_unlisted_mcp_servers']=True
    monkeypatch.setenv('NEF_REGISTRY_CONFIG',json.dumps(cfg))
    failed=client.post('/api/v1/af/mcp-servers',json={'name':'Farm','url':url})
    assert failed.status_code==502 and failed.json()['detail']['id']==sid
    install_mcp_fixture(http_fixture,'/mcp',pages=[{'tools':[]}])
    result=client.post('/api/v1/af/mcp-servers',json={'name':'Farm','url':url}).json()
    assert result['id']==sid and result['sync_status']=='pending' and 'sync_note' in result


def test_missing_config_is_explicit_and_local_state_survives(client):
    catalog = client.get("/api/v1/network/catalog", headers=headers())
    assert catalog.status_code == 200
    assert catalog.json() == {"items": [], "status": "not_configured"}

    server = register_server(client, "http://127.0.0.1:1/mcp")
    refresh = client.post("/api/v1/network/catalog/refresh", headers=headers())
    assert refresh.status_code == 503
    assert refresh.json()["detail"]["code"] == "not_configured"

    discover = client.post(
        f"/api/v1/network/servers/{server['id']}/discover", headers=headers()
    )
    assert discover.status_code == 503
    assert discover.json()["detail"]["code"] == "not_configured"
    listed = client.get("/api/v1/network/servers", headers=headers()).json()
    assert listed["servers"][0]["id"] == server["id"]
    assert listed["servers"][0]["discovery_status"] == "failed"


def test_disabled_example_config_has_no_auto_mock(client, monkeypatch):
    path = Path(__file__).parents[1] / "config" / "registry.example.json"
    example = json.loads(path.read_text(encoding="utf-8"))
    assert example == {
        "catalog_url": None,
        "publish_url": None,
        "withdraw_url": None,
        "token_env": None,
        "mcp_servers": {},
        "nef_base_url": None,
        "network_clients": {},
    }
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", str(path))
    assert client.get("/api/v1/network/catalog", headers=headers()).json() == {
        "items": [], "status": "not_configured"
    }
    refresh = client.post("/api/v1/network/catalog/refresh", headers=headers())
    assert refresh.status_code == 503
    assert refresh.json()["detail"]["code"] == "not_configured"


def test_catalog_refresh_is_bounded_and_atomic(client, http_fixture, monkeypatch):
    first = {
        "items": [
            {"id": "catalog-tool", "name": "Catalog Tool", "description": "one", "kind": "tool"},
            {"id": "catalog-package", "name": "Catalog Package", "description": "two", "kind": "package"},
        ]
    }
    invalid_duplicate = {
        "items": [
            {"id": "dup", "name": "one", "description": "one", "kind": "tool"},
            {"id": "dup", "name": "two", "description": "two", "kind": "tool"},
        ]
    }
    responses = iter([first, invalid_duplicate])
    http_fixture.add("GET", "/catalog", lambda _request: json_response(next(responses)))
    configure(monkeypatch, catalog_url=http_fixture.url("/catalog"))

    refreshed = client.post("/api/v1/network/catalog/refresh", headers=headers())
    assert refreshed.status_code == 200
    assert refreshed.json() == {"items": first["items"], "status": "synced"}

    rejected = client.post("/api/v1/network/catalog/refresh", headers=headers())
    assert rejected.status_code == 502
    assert rejected.json()["detail"]["code"] == "catalog_duplicate_id"
    current = client.get("/api/v1/network/catalog", headers=headers()).json()
    assert current["status"] == "failed"
    assert current["error"] == "catalog_duplicate_id"
    assert current["items"] == first["items"]



def test_catalog_snapshot_is_account_scoped_across_refresh_and_get(
    client, http_fixture, monkeypatch
):
    snapshots = iter([
        {"items": [{"id": "account-a-item", "name": "A", "description": "for A", "kind": "tool"}]},
        {"items": [{"id": "account-b-item", "name": "B", "description": "for B", "kind": "package"}]},
    ])
    http_fixture.add("GET", "/catalog", lambda _request: json_response(next(snapshots)))
    configure(monkeypatch, catalog_url=http_fixture.url("/catalog"))

    refreshed_a = client.post("/api/v1/network/catalog/refresh", headers=headers("caller-a"))
    assert refreshed_a.status_code == 200
    assert refreshed_a.json()["items"][0]["id"] == "account-a-item"
    refreshed_b = client.post("/api/v1/network/catalog/refresh", headers=headers("caller-b"))
    assert refreshed_b.status_code == 200
    assert refreshed_b.json()["items"][0]["id"] == "account-b-item"

    listed_a = client.get("/api/v1/network/catalog", headers=headers("caller-a"))
    listed_b = client.get("/api/v1/network/catalog", headers=headers("caller-b"))
    assert listed_a.json() == {
        "items": [{"id": "account-a-item", "name": "A", "description": "for A", "kind": "tool"}],
        "status": "synced",
    }
    assert listed_b.json() == {
        "items": [{"id": "account-b-item", "name": "B", "description": "for B", "kind": "package"}],
        "status": "synced",
    }


def test_allowlist_is_exact_and_redirects_are_not_followed(client, http_fixture, monkeypatch):
    approved_url = http_fixture.url("/approved")
    blocked_url = http_fixture.url("/blocked")
    redirect_url = http_fixture.url("/redirect")
    http_fixture.add("POST", "/blocked", lambda _request: json_response({"unexpected": True}))
    http_fixture.add(
        "POST", "/redirect",
        lambda _request: (307, {"Location": "/approved"}, b""),
    )
    reached_approved: list[bool] = []
    http_fixture.add("POST", "/approved", lambda _request: (reached_approved.append(True) or json_response({})))
    configure(monkeypatch, mcp_servers={approved_url: {}})

    blocked = register_server(client, blocked_url)
    response = client.post(f"/api/v1/network/servers/{blocked['id']}/discover", headers=headers())
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "not_approved"
    assert not [request for request in http_fixture.requests if request["path"] == "/blocked"]

    configure(monkeypatch, mcp_servers={redirect_url: {}})
    redirected = register_server(client, redirect_url)
    response = client.post(f"/api/v1/network/servers/{redirected['id']}/discover", headers=headers())
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "redirect_not_allowed"
    assert not reached_approved
    server = client.get("/api/v1/network/servers", headers=headers()).json()["servers"][-1]
    assert server["discovery_status"] == "failed"
    assert server["tools"] == []



def test_server_lifecycle_pagination_sse_and_operator_token(client, http_fixture, monkeypatch):
    mcp_url = http_fixture.url("/mcp")
    pages = [
        {"tools": [tool("alpha")], "nextCursor": "page-1"},
        {"tools": [tool("beta")], "_sse": True},
    ]
    calls = install_mcp_fixture(http_fixture, "/mcp", pages=pages)
    monkeypatch.setenv("NEF_MCP_TOKEN", "operator-mcp-secret")
    configure(monkeypatch, mcp_servers={mcp_url: {"token_env": "NEF_MCP_TOKEN"}})

    server = register_server(client, mcp_url)
    discovered = client.post(
        f"/api/v1/network/servers/{server['id']}/discover",
        headers=headers(),
    )
    assert discovered.status_code == 200, discovered.text
    body = discovered.json()
    assert body["discovery_status"] == "discovered"
    assert [item["name"] for item in body["tools"]] == ["alpha", "beta"]
    assert body["sync_status"] == "pending"
    assert [message["method"] for message in calls] == [
        "initialize", "notifications/initialized", "tools/list", "tools/list"
    ]
    assert calls[2]["params"] == {}
    assert calls[3]["params"] == {"cursor": "page-1"}
    for request in http_fixture.requests:
        assert request["headers"].get("authorization") == "Bearer operator-mcp-secret"
        assert request["headers"].get("mcp-protocol-version") == MCP_PROTOCOL_VERSION


def test_discovery_rejects_duplicate_tools_and_cursor_loops(client, http_fixture, monkeypatch):
    mcp_url = http_fixture.url("/mcp")
    calls = install_mcp_fixture(
        http_fixture,
        "/mcp",
        pages=[
            {"tools": [tool("same")], "nextCursor": "page-1"},
            {"tools": [tool("same")]},
        ],
    )
    configure(monkeypatch, mcp_servers={mcp_url: {}})
    server = register_server(client, mcp_url)
    duplicate = client.post(f"/api/v1/network/servers/{server['id']}/discover", headers=headers())
    assert duplicate.status_code == 502
    assert duplicate.json()["detail"]["code"] == "duplicate_tool"
    stored = client.get("/api/v1/network/servers", headers=headers()).json()["servers"][0]
    assert stored["discovery_status"] == "failed"
    assert stored["tools"] == []

    reset_state_for_tests()
    http_fixture.requests.clear()
    calls.clear()
    loop_url = http_fixture.url("/loop")

    def loop_mcp(request):
        message = json.loads(request["body"].decode("utf-8"))
        if message.get("method") == "initialize":
            return mcp_message({
                "jsonrpc": "2.0", "id": message["id"], "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture-mcp", "version": "1.0"},
                }
            })
        if message.get("method") == "notifications/initialized":
            return 202, {}, b""
        return mcp_message({
            "jsonrpc": "2.0", "id": message["id"], "result": {
                "tools": [tool("loop" if message.get("params", {}).get("cursor") is None else "loop-next")], "nextCursor": "same"
            }
        })

    http_fixture.add("POST", "/loop", loop_mcp)
    configure(monkeypatch, mcp_servers={loop_url: {}})
    loop_server = register_server(client, loop_url)
    looped = client.post(f"/api/v1/network/servers/{loop_server['id']}/discover", headers=headers())
    assert looped.status_code == 502
    assert looped.json()["detail"]["code"] == "cursor_loop"


def test_discovery_schema_and_protocol_validation_are_fail_closed(client, http_fixture, monkeypatch):
    mcp_url = http_fixture.url("/bad")

    def bad_mcp(request):
        message = json.loads(request["body"].decode("utf-8"))
        if message.get("method") == "initialize":
            return mcp_message({
                "jsonrpc": "2.0", "id": message["id"], "result": {
                    "protocolVersion": "wrong-version",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fixture-mcp", "version": "1.0"},
                }
            })
        return 202, {}, b""

    http_fixture.add("POST", "/bad", bad_mcp)
    configure(monkeypatch, mcp_servers={mcp_url: {}})
    server = register_server(client, mcp_url)
    response = client.post(f"/api/v1/network/servers/{server['id']}/discover", headers=headers())
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "protocol_version_mismatch"
    stored = client.get("/api/v1/network/servers", headers=headers()).json()["servers"][0]
    assert stored["discovery_status"] == "failed" and stored["tools"] == []


def test_sync_requires_explicit_acceptance_and_publishes_discovered_tools(client, http_fixture, monkeypatch):
    mcp_url = http_fixture.url("/mcp")
    publish_url = http_fixture.url("/publish")
    install_mcp_fixture(http_fixture, "/mcp", pages=[{"tools": [tool("remote")]}])
    publish_bodies: list[dict[str, Any]] = []
    accept_server = False

    def publish(request):
        nonlocal accept_server
        payload = json.loads(request["body"].decode("utf-8"))
        publish_bodies.append(payload)
        assert request["headers"].get("authorization") == "Bearer operator-publish-secret"
        return json_response({"accepted": accept_server})

    http_fixture.add("POST", "/publish", publish)
    monkeypatch.setenv("NEF_REGISTRY_TOKEN", "operator-publish-secret")
    configure(
        monkeypatch,
        publish_url=publish_url,
        mcp_servers={mcp_url: {}},
        token_env="NEF_REGISTRY_TOKEN",
    )
    server = register_server(client, mcp_url)
    assert client.post(f"/api/v1/network/servers/{server['id']}/discover", headers=headers()).status_code == 200

    submitted = client.post(f"/api/v1/network/servers/{server['id']}/sync", headers=headers())
    assert submitted.status_code == 200
    assert submitted.json()["accepted"] is False
    assert submitted.json()["sync_status"] == "submitted"

    accept_server = True
    synced = client.post(f"/api/v1/network/servers/{server['id']}/sync", headers=headers())
    assert synced.status_code == 200
    assert synced.json()["accepted"] is True
    assert synced.json()["sync_status"] == "synced"
    assert publish_bodies[0]["type"] == "mcp_server_registration"
    assert publish_bodies[0]["server"]["tools"][0]["name"] == "remote"


def test_packages_accept_existing_catalog_ids_and_owner_tools_only(client, http_fixture, monkeypatch):
    mcp_url = http_fixture.url("/mcp")
    catalog_url = http_fixture.url("/catalog")
    publish_url = http_fixture.url("/publish")
    install_mcp_fixture(http_fixture, "/mcp", pages=[{"tools": [tool("remote")]}])
    http_fixture.add("GET", "/catalog", lambda _request: json_response({
        "items": [
            {"id": "catalog-cap", "name": "Catalog Capability", "description": "catalog", "kind": "tool"}
        ]
    }))
    http_fixture.add("POST", "/publish", lambda _request: json_response({"accepted": True}))
    configure(monkeypatch, catalog_url=catalog_url, publish_url=publish_url, mcp_servers={mcp_url: {}})
    assert client.post("/api/v1/network/catalog/refresh", headers=headers()).status_code == 200
    server = register_server(client, mcp_url)
    assert client.post(f"/api/v1/network/servers/{server['id']}/discover", headers=headers()).status_code == 200

    package_response = client.post(
        "/api/v1/network/packages",
        headers=headers(),
        json={
            "name": "bounded package",
            "description": "declaration only",
            "steps": [
                {"capability_id": "target_detection"},
                {"capability_id": "catalog-cap"},
                {"capability_id": f"{server['id']}:remote"},
            ],
            "execution_target": "network",
        },
    )
    assert package_response.status_code == 200, package_response.text
    package = package_response.json()
    assert package["execution_target"] == "network"
    assert package["sync_status"] == "pending"
    assert [step["capability_id"] for step in package["steps"]] == [
        "target_detection", "catalog-cap", f"{server['id']}:remote"
    ]
    assert "target_detection" in CAPABILITIES

    unknown = client.post(
        "/api/v1/network/packages",
        headers=headers(),
        json={"name": "bad", "steps": [{"capability_id": "unknown-cap"}], "execution_target": "network"},
    )
    assert unknown.status_code == 422
    duplicate = client.post(
        "/api/v1/network/packages",
        headers=headers(),
        json={
            "name": "bad",
            "steps": [{"capability_id": "target_detection"}, {"capability_id": "target_detection"}],
            "execution_target": "network",
        },
    )
    assert duplicate.status_code == 422
    wrong_target = client.post(
        "/api/v1/network/packages",
        headers=headers(),
        json={"name": "bad", "steps": [{"capability_id": "target_detection"}], "execution_target": "local"},
    )
    assert wrong_target.status_code == 422

    foreign = client.post(
        "/api/v1/network/packages",
        headers=headers("caller-b"),
        json={
            "name": "foreign",
            "steps": [{"capability_id": f"{server['id']}:remote"}],
            "execution_target": "network",
        },
    )
    assert foreign.status_code == 422
    assert client.get("/api/v1/network/servers", headers=headers("caller-b")).json() == {"servers": []}
    assert client.post(f"/api/v1/network/servers/{server['id']}/sync", headers=headers("caller-b")).status_code == 404
    assert client.post(f"/api/v1/network/packages/{package['id']}/sync", headers=headers("caller-b")).status_code == 404

    package_sync = client.post(f"/api/v1/network/packages/{package['id']}/sync", headers=headers())
    assert package_sync.status_code == 200
    assert package_sync.json()["accepted"] is True
    assert package_sync.json()["sync_status"] == "synced"


def test_listing_auth_and_mutation_scopes_are_enforced(client):
    assert client.get("/api/v1/network/catalog", headers=headers("caller-list")).status_code == 200
    assert client.get("/api/v1/network/servers", headers=headers("caller-list")).status_code == 200
    assert client.get("/api/v1/network/packages", headers=headers("caller-list")).status_code == 200

    server = client.post(
        "/api/v1/network/servers",
        headers=headers("caller-list"),
        json={"name": "not allowed", "url": "http://example.invalid/mcp"},
    )
    assert server.status_code == 403
    package = client.post(
        "/api/v1/network/packages",
        headers=headers("caller-af"),
        json={"name": "not allowed", "steps": [{"capability_id": "target_detection"}], "execution_target": "network"},
    )
    assert package.status_code == 403

    too_many = client.post(
        "/api/v1/network/packages",
        headers=headers(),
        json={
            "name": "too many",
            "steps": [{"capability_id": f"missing-{index}"} for index in range(13)],
            "execution_target": "network",
        },
    )
    assert too_many.status_code == 422


@pytest.mark.parametrize("url", [
    "ftp://example.invalid/mcp",
    "http://user:pass@example.invalid/mcp",
    "http://example.invalid/mcp#fragment",
])
def test_server_url_rejects_credentialed_or_unsupported_urls(client, url):
    response = client.post(
        "/api/v1/network/servers",
        headers=headers(),
        json={"name": "bad", "url": url},
    )
    assert response.status_code == 422


def test_af_source_is_server_assigned_and_publish_requires_discovery(client, http_fixture, monkeypatch):
    published=[]
    def publish(request):
        published.append(json.loads(request['body']))
        return json_response({'accepted':True})
    http_fixture.add('POST','/publish',publish)
    configure(monkeypatch,publish_url=http_fixture.url('/publish'))
    response=client.post('/api/v1/network/servers',headers=headers(),json={
        'name':'AF camera','url':http_fixture.url('/mcp'),'description':'camera',
        'source':'TRF','source_account':'spoofed'
    })
    assert response.status_code==200
    server=response.json()
    assert server['source']=='AF' and server['source_account']!='spoofed'
    assert server['registration_status']=='registered'
    result=client.post('/api/v1/network/servers/'+server['id']+'/sync',headers=headers())
    assert result.status_code==409 and result.json()['detail']['code']=='not_discovered'
    assert published==[]
