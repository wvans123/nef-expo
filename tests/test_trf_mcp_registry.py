# -*- coding: utf-8 -*-
"""TRF MCP collection contract tests."""
from __future__ import annotations

import json

import pytest

import network_registry
from test_network_registry import (
    client,
    clean_state,
    configure,
    headers,
    http_fixture,
    install_mcp_fixture,
    json_response,
    tool,
)


def trf_server(
    name: str,
    url: str,
    *,
    tool_type: str = "third-party tool",
    description: str = "patrol server",
    is_third_party: bool | None = True,
) -> dict:
    result = {
        "serverName": name,
        "serverType": "Streamable HTTP",
        "toolType": tool_type,
        "description": description,
        "url": url,
        "serverStatus": "active",
    }
    if is_third_party is not None:
        result["isThirdParty"] = is_third_party
    return result


def register_and_discover(
    client,
    peer,
    monkeypatch,
    collection_url,
    *,
    name="patrol-car-managementx",
    publish_url=None,
):
    mcp_url = peer.url("/raw-mcp")
    install_mcp_fixture(peer, "/raw-mcp", pages=[{"tools": [tool("inspect")]}])
    configure(
        monkeypatch,
        trf_mcp_servers_url=collection_url,
        publish_url=publish_url,
        mcp_servers={mcp_url: {}},
    )
    response = client.post(
        "/api/v1/network/servers",
        headers=headers(),
        json={
            "serverName": name,
            "url": mcp_url,
            "description": "patrol server",
        },
    )
    assert response.status_code == 200, response.text
    record = response.json()
    path = f"/api/v1/network/servers/{record['id']}"
    discovered = client.post(path + "/discover", headers=headers())
    assert discovered.status_code == 200, discovered.text
    return path, record, mcp_url


def test_exact_post_raw_url_preview_and_market_projection(
    client, http_fixture, monkeypatch
):
    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    path, record, raw_url = register_and_discover(
        client, http_fixture, monkeypatch, collection_url
    )
    expected = trf_server(record["serverName"], raw_url)
    stored: list[dict] = []

    def post_server(request):
        payload = json.loads(request["body"])
        stored[:] = [payload]
        return 201, {}, b""

    http_fixture.add("POST", "/trf/api/v1/mcp-servers", post_server)
    http_fixture.add("GET", "/trf/api/v1/mcp-servers", lambda _r: json_response({
        "code": 200, "message": "OK",
        "data": [{**item, "id": 42, "createdAt": "2026-09-22"} for item in stored],
    }))

    preview = client.get(path + "/publication", headers=headers())
    assert preview.status_code == 200
    assert preview.json() == expected

    published = client.post(path + "/publish", headers=headers())
    assert published.status_code == 200, published.text
    assert published.json()["sync_status"] == "synced"
    post = next(
        request
        for request in http_fixture.requests
        if request["method"] == "POST"
        and request["path"] == "/trf/api/v1/mcp-servers"
    )
    assert json.loads(post["body"]) == expected
    assert set(json.loads(post["body"])) == {
        "serverName",
        "serverType",
        "toolType",
        "description",
        "url",
        "serverStatus",
        "isThirdParty",
    }
    assert json.loads(post["body"])["isThirdParty"] is True
    assert json.loads(post["body"])["url"] == raw_url
    assert "tools" not in json.loads(post["body"])
    assert "account" not in json.loads(post["body"])

    item = client.get("/api/v1/network/market").json()["items"][0]
    assert item["serverName"] == record["serverName"]
    assert item["toolType"] == "third-party tool"
    assert item["registration_status"] == "registered"


@pytest.mark.parametrize("envelope", ["array", "items", "data"])
def test_trf_get_supports_envelopes_and_four_categories_without_tool_discovery(
    client, http_fixture, monkeypatch, envelope
):
    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    categories = [
        "nf tool",
        "computing tool",
        "sensing tool",
        "third-party tool",
    ]
    values = [
        trf_server(
            f"server-{index}",
            f"http://example.invalid/{index}",
            tool_type=kind,
            is_third_party=None,
        )
        for index, kind in enumerate(categories)
    ]
    body = values if envelope == "array" else {envelope: values}
    http_fixture.add("GET", "/trf/api/v1/mcp-servers", lambda _r: json_response(body))
    configure(monkeypatch, trf_mcp_servers_url=collection_url)

    response = client.get("/api/v1/network/trf/servers", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "loaded", "servers": values}
    assert all(set(item) == set(network_registry._TRF_FIELDS) for item in response.json()["servers"])
    assert all("tools" not in item for item in response.json()["servers"])
    assert [request["method"] for request in http_fixture.requests] == ["GET"]


def test_optional_third_party_marker_schema_and_matching():
    base = trf_server(
        "nef-cap-12345678-demo",
        "http://nef.invalid/mcp/capabilities/demo",
        tool_type="nf tool",
        description="[Demo] capability",
        is_third_party=None,
    )
    parsed = network_registry._validate_trf_servers([
        {**base, "isThirdParty": False},
    ])
    assert parsed[0]["isThirdParty"] is False
    assert network_registry._same_trf_server(parsed[0], base) is True
    assert network_registry._same_trf_server(
        {**base, "isThirdParty": True},
        base,
    ) is False

    af = trf_server("af-server", "http://af.invalid/mcp")
    assert network_registry._same_trf_server(
        {key: value for key, value in af.items() if key != "isThirdParty"},
        af,
    ) is True
    assert network_registry._same_trf_server(
        {**af, "isThirdParty": False},
        af,
    ) is False
    with pytest.raises(network_registry._RemoteSchemaFailure):
        network_registry._validate_trf_servers([
            {**base, "isThirdParty": "false"},
        ])


def test_trf_get_not_configured_and_schema_failure(client, http_fixture, monkeypatch):
    configure(monkeypatch)
    assert client.get(
        "/api/v1/network/trf/servers", headers=headers()
    ).json() == {"status": "not_configured", "servers": []}

    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    http_fixture.add(
        "GET",
        "/trf/api/v1/mcp-servers",
        lambda _r: json_response({"items": [], "nextCursor": "unsupported"}),
    )
    configure(monkeypatch, trf_mcp_servers_url=collection_url)
    failed = client.get("/api/v1/network/trf/servers", headers=headers())
    assert failed.status_code == 502
    assert failed.json()["detail"]["code"] == "trf_incomplete_list"


@pytest.mark.parametrize("envelope", [
    lambda rows: rows,
    lambda rows: {"items": rows, "total": len(rows)},
    lambda rows: {"code": 200, "message": "OK", "data": rows},
    lambda rows: {"code": 0, "data": {"records": rows, "total": len(rows)}},
    lambda rows: {"data": {"items": rows, "nextCursor": None}},
    lambda rows: {"servers": rows},
])
def test_get_projects_metadata_without_rejecting_complete_collection(envelope):
    item = trf_server("sample", "http://example.invalid/mcp")
    enriched = {**item, "id": 10, "createdAt": "2026-09-22", "internalSecret": "not-projected"}
    assert network_registry._validate_trf_servers(envelope([enriched])) == [item]


@pytest.mark.parametrize("body", [
    {"message": "error"},
    {"code": 500, "data": []},
    {"success": False, "items": []},
    {"items": [], "total": 5},
    {"data": {"records": [], "hasMore": True}},
    {"items": [], "totalPages": 3},
    {"data": [], "pagination": {"total": 10}},
    {"items": [], "nextCursor": "next"},
    {"items": [], "data": []},
    {"data": None},
])
def test_incomplete_or_error_envelope_is_not_an_empty_directory(body):
    with pytest.raises(network_registry._RemoteSchemaFailure):
        network_registry._validate_trf_servers(body)


def test_duplicate_names_cannot_mask_a_conflicting_server():
    item = trf_server("same-name", "http://example.invalid/mcp")
    with pytest.raises(network_registry._RemoteSchemaFailure):
        network_registry._validate_trf_servers([item, {**item, "url": "http://other.invalid/mcp"}])


def test_delete_uses_saved_encoded_target_empty_body_and_404_confirmation(
    client, http_fixture, monkeypatch
):
    assert network_registry._trf_delete_url(
        "http://trf.invalid/mcp-servers", "patrol/car name"
    ) == "http://trf.invalid/mcp-servers/patrol%2Fcar%20name"
    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    name = "patrol.car_1-x"
    path, _record, raw_url = register_and_discover(
        client, http_fixture, monkeypatch, collection_url, name=name
    )
    remote = [trf_server(name, raw_url)]
    http_fixture.add("POST", "/trf/api/v1/mcp-servers", lambda _r: (201, {}, b""))
    http_fixture.add("GET", "/trf/api/v1/mcp-servers", lambda _r: json_response(remote))
    assert client.post(path + "/publish", headers=headers()).json()["sync_status"] == "synced"

    delete_path = "/trf/api/v1/mcp-servers/patrol.car_1-x"

    def missing(request):
        assert request["body"] == b""
        remote.clear()
        return 404, {}, b""

    http_fixture.add("DELETE", delete_path, missing)
    withdrawn = client.post(path + "/unpublish", headers=headers())
    assert withdrawn.status_code == 200
    assert withdrawn.json()["sync_status"] == "synced"
    assert withdrawn.json()["trf_may_exist"] is False
    delete_request = next(r for r in http_fixture.requests if r["method"] == "DELETE")
    assert delete_request["path"] == delete_path
    assert delete_request["body"] == b""


def test_delete_timeout_and_success_without_confirmation_remain_honest(
    client, http_fixture, monkeypatch
):
    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    path, _record, raw_url = register_and_discover(
        client, http_fixture, monkeypatch, collection_url
    )
    remote = [trf_server("patrol-car-managementx", raw_url)]
    http_fixture.add("POST", "/trf/api/v1/mcp-servers", lambda _r: (200, {}, b"{}"))
    http_fixture.add("GET", "/trf/api/v1/mcp-servers", lambda _r: json_response(remote))
    assert client.post(path + "/publish", headers=headers()).json()["sync_status"] == "synced"

    async def timeout(*_args, **_kwargs):
        raise network_registry._RemoteFailure("upstream_timeout")

    monkeypatch.setattr(network_registry, "_delete_trf_server", timeout)
    timed_out = client.post(path + "/unpublish", headers=headers()).json()
    assert timed_out["publication_status"] == "unpublished"
    assert timed_out["sync_status"] == "failed"
    assert timed_out["sync_error"] == "upstream_timeout"
    assert timed_out["trf_may_exist"] is True

    async def deleted(*_args, **_kwargs):
        return 204

    monkeypatch.setattr(network_registry, "_delete_trf_server", deleted)
    unconfirmed = client.post(path + "/unpublish", headers=headers()).json()
    assert unconfirmed["sync_status"] == "submitted"
    assert unconfirmed["sync_error"] == "trf_confirmation_unknown"
    assert unconfirmed["trf_may_exist"] is True
    assert client.get("/api/v1/network/market").json()["items"] == []


def test_post_2xx_without_matching_get_is_only_submitted(
    client, http_fixture, monkeypatch
):
    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    path, _record, _raw_url = register_and_discover(
        client, http_fixture, monkeypatch, collection_url
    )
    http_fixture.add("POST", "/trf/api/v1/mcp-servers", lambda _r: (204, {}, b""))
    http_fixture.add("GET", "/trf/api/v1/mcp-servers", lambda _r: json_response([]))
    result = client.post(path + "/publish", headers=headers())
    assert result.status_code == 200
    assert result.json()["sync_status"] == "submitted"
    assert result.json()["sync_error"] == "trf_confirmation_unknown"
    assert result.json()["trf_may_exist"] is True


def test_explicit_server_name_without_any_publish_url_uses_trf_preview_and_retries(
    client, http_fixture, monkeypatch
):
    path, record, raw_url = register_and_discover(
        client, http_fixture, monkeypatch, None
    )
    expected = trf_server(record["serverName"], raw_url)
    preview = client.get(path + "/publication", headers=headers())
    assert preview.status_code == 200
    assert preview.json() == expected

    initial_request_count = len(http_fixture.requests)
    pending = client.post(path + "/publish", headers=headers())
    assert pending.status_code == 200
    assert pending.json()["publication_status"] == "published"
    assert pending.json()["sync_status"] == "pending"
    assert pending.json()["trf_may_exist"] is False
    assert len(http_fixture.requests) == initial_request_count
    assert client.get(
        "/api/v1/network/market"
    ).json()["items"][0]["registration_status"] == "unknown"

    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    configure(
        monkeypatch,
        trf_mcp_servers_url=collection_url,
        mcp_servers={raw_url: {}},
    )
    stored: list[dict] = []

    def publish(request):
        stored[:] = [json.loads(request["body"])]
        return 202, {}, b""

    http_fixture.add("POST", "/trf/api/v1/mcp-servers", publish)
    http_fixture.add("GET", "/trf/api/v1/mcp-servers", lambda _r: json_response(stored))
    retried = client.post(path + "/publish", headers=headers())
    assert retried.status_code == 200
    assert retried.json()["sync_status"] == "synced"
    assert stored == [expected]


def test_explicit_server_name_keeps_legacy_publish_when_publish_url_is_configured(
    client, http_fixture, monkeypatch
):
    legacy_url = http_fixture.url("/legacy-publish")
    path, _record, _raw_url = register_and_discover(
        client,
        http_fixture,
        monkeypatch,
        None,
        publish_url=legacy_url,
    )
    sent: list[dict] = []

    def legacy_publish(request):
        sent.append(json.loads(request["body"]))
        return json_response({"accepted": True})

    http_fixture.add("POST", "/legacy-publish", legacy_publish)
    preview = client.get(path + "/publication", headers=headers())
    assert preview.status_code == 200
    assert preview.json()["type"] == "mcp_server_registration"
    assert preview.json()["server"]["url"].startswith(
        "http://nef.test:8069/api/v1/network/af-servers/"
    )
    published = client.post(path + "/publish", headers=headers())
    assert published.status_code == 200
    assert published.json()["sync_status"] == "synced"
    assert sent == [preview.json()]
    assert client.get(
        "/api/v1/network/market"
    ).json()["items"][0]["registration_status"] == "unknown"


def test_reserved_builtin_catalog_prefix_cannot_be_registered(client, monkeypatch):
    configure(monkeypatch)
    denied = client.post(
        "/api/v1/network/servers",
        headers=headers(),
        json={
            "serverName": "nef-cap-12345678-target_detection",
            "url": "http://example.invalid/mcp",
        },
    )
    assert denied.status_code == 422
    assert denied.json()["detail"]["code"] == "reserved_server_name"


def test_config_change_withdraws_first_target_not_new_collection(
    client, http_fixture, monkeypatch
):
    old_url = http_fixture.url("/old/trf/api/v1/mcp-servers")
    new_url = http_fixture.url("/new/trf/api/v1/mcp-servers")
    path, _record, raw_url = register_and_discover(
        client, http_fixture, monkeypatch, old_url
    )
    remote = [trf_server("patrol-car-managementx", raw_url)]
    http_fixture.add("POST", "/old/trf/api/v1/mcp-servers", lambda _r: (201, {}, b""))
    http_fixture.add("GET", "/old/trf/api/v1/mcp-servers", lambda _r: json_response(remote))
    assert client.post(path + "/publish", headers=headers()).json()["sync_status"] == "synced"

    config = configure(
        monkeypatch,
        trf_mcp_servers_url=new_url,
        mcp_servers={raw_url: {}},
    )

    def remove_old(_request):
        remote.clear()
        return 204, {}, b""

    http_fixture.add(
        "DELETE",
        "/old/trf/api/v1/mcp-servers/patrol-car-managementx",
        remove_old,
    )
    http_fixture.add("GET", "/old/trf/api/v1/mcp-servers", lambda _r: json_response(remote))
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", json.dumps(config))
    result = client.post(path + "/unpublish", headers=headers())
    assert result.status_code == 200
    assert result.json()["sync_status"] == "synced"
    assert any(request["path"].startswith("/old/") for request in http_fixture.requests)
    assert not any(request["path"].startswith("/new/") for request in http_fixture.requests)


def test_server_name_conflict_draft_delete_cross_account_and_busy(
    client, monkeypatch
):
    configure(monkeypatch)
    first = client.post(
        "/api/v1/network/servers",
        headers=headers("caller-a"),
        json={"serverName": "shared-name", "url": "http://example.invalid/a"},
    )
    assert first.status_code == 200
    server_id = first.json()["id"]
    conflict = client.post(
        "/api/v1/network/servers",
        headers=headers("caller-b"),
        json={"serverName": "shared-name", "url": "http://example.invalid/b"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "server_name_conflict"
    assert client.delete(
        f"/api/v1/network/servers/{server_id}", headers=headers("caller-b")
    ).status_code == 404

    with network_registry._STATE_LOCK:
        network_registry._ACCOUNTS["account-a"]["servers"][server_id]["sync_status"] = "syncing"
    busy = client.delete(
        f"/api/v1/network/servers/{server_id}", headers=headers("caller-a")
    )
    assert busy.status_code == 409
    assert busy.json()["detail"]["code"] == "busy"
    with network_registry._STATE_LOCK:
        network_registry._ACCOUNTS["account-a"]["servers"][server_id]["sync_status"] = "failed"
    deleted = client.delete(
        f"/api/v1/network/servers/{server_id}", headers=headers("caller-a")
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": server_id}


def test_delete_open_record_uses_source_account_but_private_stays_isolated(
    client, http_fixture, monkeypatch
):
    mcp_url = http_fixture.url("/open-delete-mcp")
    install_mcp_fixture(
        http_fixture,
        "/open-delete-mcp",
        pages=[{"tools": [tool("inspect")]}],
    )
    configure(monkeypatch, mcp_servers={mcp_url: {}})
    opened = client.post(
        "/api/v1/af/mcp-servers",
        json={"name": "OpenDelete", "url": mcp_url},
    )
    assert opened.status_code == 200, opened.text
    open_id = opened.json()["id"]
    removed = client.delete(
        f"/api/v1/network/servers/{open_id}",
        headers=headers("caller-b"),
    )
    assert removed.status_code == 200
    assert removed.json() == {"deleted": True, "id": open_id}
    assert all(
        item["id"] != open_id
        for item in client.get(
            "/api/v1/network/servers", headers=headers("caller-a")
        ).json()["servers"]
    )

    private = client.post(
        "/api/v1/network/servers",
        headers=headers("caller-a"),
        json={"name": "PrivateDelete", "url": mcp_url},
    )
    assert private.status_code == 200
    private_id = private.json()["id"]
    denied = client.delete(
        f"/api/v1/network/servers/{private_id}",
        headers=headers("caller-b"),
    )
    assert denied.status_code == 404
    assert client.delete(
        f"/api/v1/network/servers/{private_id}",
        headers=headers("caller-a"),
    ).status_code == 200


def test_published_or_remote_uncertain_record_cannot_be_deleted(
    client, http_fixture, monkeypatch
):
    collection_url = http_fixture.url("/trf/api/v1/mcp-servers")
    path, record, _raw_url = register_and_discover(
        client, http_fixture, monkeypatch, collection_url
    )
    http_fixture.add("POST", "/trf/api/v1/mcp-servers", lambda _r: (503, {}, b""))
    published = client.post(path + "/publish", headers=headers()).json()
    assert published["publication_status"] == "published"
    assert published["trf_may_exist"] is True
    assert client.delete(path, headers=headers()).json()["detail"]["code"] == "unpublish_required"
    client.post(path + "/unpublish", headers=headers())
    blocked = client.delete(path, headers=headers())
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "withdraw_required"
    assert record["id"] in [item["id"] for item in client.get(
        "/api/v1/network/servers", headers=headers()
    ).json()["servers"]]


def test_package_publish_is_local_only_in_new_trf_mode(
    client, http_fixture, monkeypatch
):
    configure(
        monkeypatch,
        trf_mcp_servers_url=http_fixture.url("/trf/api/v1/mcp-servers"),
        publish_url=http_fixture.url("/legacy-publish"),
    )
    package = client.post(
        "/api/v1/network/packages",
        headers=headers(),
        json={
            "name": "local offer",
            "description": "not a TRF MCP server",
            "steps": [{"capability_id": "target_detection"}],
            "execution_target": "network",
        },
    ).json()
    published = client.post(
        f"/api/v1/network/packages/{package['id']}/publish",
        headers=headers(),
    )
    assert published.status_code == 200
    assert published.json()["sync_status"] == "not_required"
    assert http_fixture.requests == []
    market_item = client.get("/api/v1/network/market").json()["items"][0]
    assert market_item["kind"] == "package"
    assert "toolType" not in market_item


def test_package_without_any_publish_url_is_local_not_required(
    client, monkeypatch
):
    configure(monkeypatch)
    package = client.post(
        "/api/v1/network/packages",
        headers=headers(),
        json={
            "name": "local-only offer",
            "steps": [{"capability_id": "target_detection"}],
            "execution_target": "network",
        },
    ).json()
    published = client.post(
        f"/api/v1/network/packages/{package['id']}/publish",
        headers=headers(),
    )
    assert published.status_code == 200
    assert published.json()["publication_status"] == "published"
    assert published.json()["sync_status"] == "not_required"
