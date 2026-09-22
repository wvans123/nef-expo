# -*- coding: utf-8 -*-
"""Built-in NEF capability catalog synchronization tests."""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import trf_catalog
from skills import CAP_INDEX, capability_tool_type, trf_catalog_capabilities
from test_network_registry import (
    fake_auth,
    headers,
    http_fixture,
    json_response,
)


@pytest.fixture(autouse=True)
def clean_trf_catalog_state():
    trf_catalog.reset_state_for_tests()
    yield
    trf_catalog.reset_state_for_tests()


@pytest.fixture
def catalog_client():
    app = FastAPI()
    app.include_router(trf_catalog.build_router(fake_auth))
    with TestClient(app) as test_client:
        yield test_client


def configure_catalog(
    monkeypatch,
    *,
    target: str | None,
    base: str | None,
    token_env: str | None = None,
):
    monkeypatch.setenv(
        "NEF_REGISTRY_CONFIG",
        json.dumps({
            "trf_mcp_servers_url": target,
            "nef_base_url": base,
            "token_env": token_env,
            "mcp_servers": {},
            "network_clients": {},
        }),
    )


def use_capabilities(monkeypatch, *capability_ids: str):
    values = [CAP_INDEX[capability_id] for capability_id in capability_ids]
    monkeypatch.setattr(trf_catalog, "_capabilities", lambda: values)
    return values


def by_capability(response):
    return {
        item["capability_id"]: item
        for item in response.json()["items"]
    }


def test_payload_classification_exclusions_and_cache_only_get(
    catalog_client, http_fixture, monkeypatch
):
    target = http_fixture.url("/trf/api/v1/mcp-servers")
    base = "http://nef.example:8069"
    configure_catalog(monkeypatch, target=target, base=base)

    payloads = trf_catalog._payloads(base)
    expected = {cap.id for cap in trf_catalog_capabilities()}
    assert set(payloads) == expected
    assert "capability_register" not in payloads
    assert "revenue_share" not in payloads
    assert all(CAP_INDEX[capability_id].status == "available" for capability_id in payloads)
    assert all(CAP_INDEX[capability_id].category != "ecosystem" for capability_id in payloads)
    for capability_id, payload in payloads.items():
        assert set(payload) == {
            "serverName",
            "serverType",
            "toolType",
            "description",
            "url",
            "serverStatus",
            "isThirdParty",
        }
        assert payload["serverName"].startswith("nef-cap-")
        assert payload["serverType"] == "Streamable HTTP"
        assert payload["toolType"] == capability_tool_type(CAP_INDEX[capability_id])
        assert payload["description"].startswith(f"[{CAP_INDEX[capability_id].name}] ")
        assert payload["url"] == f"{base}/mcp/capabilities/{capability_id}"
        assert payload["isThirdParty"] is False

    response = catalog_client.get("/api/v1/network/trf/catalog")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["configured"] is True
    assert body["base_configured"] is True
    assert body["busy"] is False
    assert body["can_withdraw"] is False
    assert body["remote_items"] == []
    assert body["summary"]["total"] == len(expected)
    assert http_fixture.requests == []
    serialized = json.dumps(body)
    assert target not in serialized
    assert base not in serialized

    assert catalog_client.post(
        "/api/v1/network/trf/catalog/refresh"
    ).status_code == 401
    assert catalog_client.post(
        "/api/v1/network/trf/catalog/refresh",
        headers=headers("caller-list"),
    ).status_code == 403

    with trf_catalog._STATE_LOCK:
        trf_catalog._BUSY = True
    try:
        assert catalog_client.get(
            "/api/v1/network/trf/catalog"
        ).json()["busy"] is True
        busy = catalog_client.post(
            "/api/v1/network/trf/catalog/publish",
            headers=headers(),
        )
        assert busy.status_code == 409
        assert busy.json()["detail"]["code"] == "busy"
    finally:
        with trf_catalog._STATE_LOCK:
            trf_catalog._BUSY = False


def test_publish_skips_exact_handles_partial_failure_and_unconfirmed(
    catalog_client, http_fixture, monkeypatch
):
    caps = use_capabilities(
        monkeypatch,
        "target_detection",
        "compute_offload",
        "qos_guarantee",
    )
    target = http_fixture.url("/trf/api/v1/mcp-servers")
    base = "http://nef.example:8069"
    configure_catalog(monkeypatch, target=target, base=base)
    payloads = trf_catalog._payloads(base)
    remote = [{**payloads[caps[0].id], "isThirdParty": False}]
    posted: list[dict] = []

    http_fixture.add(
        "GET",
        "/trf/api/v1/mcp-servers",
        lambda _request: json_response(remote),
    )

    def publish(request):
        payload = json.loads(request["body"])
        posted.append(payload)
        if payload["serverName"] == payloads[caps[2].id]["serverName"]:
            return 503, {}, b"{}"
        return 202, {}, b""

    http_fixture.add("POST", "/trf/api/v1/mcp-servers", publish)
    response = catalog_client.post(
        "/api/v1/network/trf/catalog/publish",
        headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["busy"] is False
    items = by_capability(response)
    assert items[caps[0].id]["registration_status"] == "registered"
    assert items[caps[1].id] == {
        "capability_id": caps[1].id,
        "serverName": payloads[caps[1].id]["serverName"],
        "toolType": payloads[caps[1].id]["toolType"],
        "registration_status": "submitted",
        "sync_error": "trf_confirmation_unknown",
    }
    assert items[caps[2].id]["registration_status"] == "failed"
    assert items[caps[2].id]["sync_error"] == "upstream_http_error"
    assert {payload["serverName"] for payload in posted} == {
        payloads[caps[1].id]["serverName"],
        payloads[caps[2].id]["serverName"],
    }
    assert all(set(payload) == set(trf_catalog.registry._TRF_FIELDS) | {"isThirdParty"} for payload in posted)
    assert all(payload["isThirdParty"] is False for payload in posted)
    assert [request["method"] for request in http_fixture.requests].count("GET") == 2
    assert response.json()["status"] == "partial"
    assert response.json()["can_withdraw"] is True


def test_refresh_directory_ignores_unknown_type_and_conflict_is_not_overwritten(
    catalog_client, http_fixture, monkeypatch
):
    caps = use_capabilities(monkeypatch, "target_detection", "compute_offload")
    target = http_fixture.url("/trf/api/v1/mcp-servers")
    base = "http://nef.example:8069"
    monkeypatch.setenv("TRF_TOKEN", "do-not-leak")
    configure_catalog(
        monkeypatch,
        target=target,
        base=base,
        token_env="TRF_TOKEN",
    )
    payloads = trf_catalog._payloads(base)
    conflict = {
        **payloads[caps[0].id],
        "description": "different owner",
    }
    unknown = {
        "serverName": "operator-unknown",
        "serverType": "Streamable HTTP",
        "toolType": "future tool",
        "description": "unknown classification",
        "url": "http://operator.invalid/mcp",
        "serverStatus": "active",
    }
    remote = [conflict, unknown]
    posted: list[dict] = []
    http_fixture.add(
        "GET",
        "/trf/api/v1/mcp-servers",
        lambda _request: json_response(remote),
    )
    http_fixture.add(
        "POST",
        "/trf/api/v1/mcp-servers",
        lambda request: (
            posted.append(json.loads(request["body"]))
            or (202, {}, b"")
        ),
    )

    refreshed = catalog_client.post(
        "/api/v1/network/trf/catalog/refresh",
        headers=headers(),
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["busy"] is False
    assert refreshed.json()["ignored_count"] == 1
    assert len(refreshed.json()["remote_items"]) == 1
    assert "url" not in refreshed.json()["remote_items"][0]
    assert by_capability(refreshed)[caps[0].id]["registration_status"] == "conflict"
    assert [request["method"] for request in http_fixture.requests] == ["GET"]

    published = catalog_client.post(
        "/api/v1/network/trf/catalog/publish",
        headers=headers(),
    )
    assert all(
        payload["serverName"] != conflict["serverName"]
        for payload in posted
    )
    serialized = json.dumps(published.json())
    assert target not in serialized
    assert base not in serialized
    assert "do-not-leak" not in serialized


def test_unpublish_keeps_old_target_results_out_of_current_context(
    catalog_client, http_fixture, monkeypatch
):
    cap = use_capabilities(monkeypatch, "target_detection")[0]
    target_a = http_fixture.url("/a/mcp-servers")
    target_b = http_fixture.url("/b/mcp-servers")
    base = "http://nef.example:8069"
    remote_a: list[dict] = []
    remote_b: list[dict] = []

    http_fixture.add(
        "GET",
        "/a/mcp-servers",
        lambda _request: json_response(remote_a),
    )
    http_fixture.add(
        "GET",
        "/b/mcp-servers",
        lambda _request: json_response(remote_b),
    )

    def publish_a(request):
        remote_a[:] = [json.loads(request["body"])]
        return 201, {}, b""

    def publish_b(request):
        payload = json.loads(request["body"])
        remote_b[:] = [
            payload,
            {
                **payload,
                "serverName": "nef-cap-unrelated",
                "description": "not managed here",
                "isThirdParty": True,
            },
        ]
        return 201, {}, b""

    http_fixture.add("POST", "/a/mcp-servers", publish_a)
    http_fixture.add("POST", "/b/mcp-servers", publish_b)
    configure_catalog(monkeypatch, target=target_a, base=base)
    payload_a = trf_catalog._payloads(base)[cap.id]
    http_fixture.add(
        "DELETE",
        "/a/mcp-servers/" + payload_a["serverName"],
        lambda _request: (503, {}, b"{}"),
    )
    assert catalog_client.post(
        "/api/v1/network/trf/catalog/publish",
        headers=headers(),
    ).json()["items"][0]["registration_status"] == "registered"

    configure_catalog(monkeypatch, target=target_b, base=base)
    payload_b = trf_catalog._payloads(base)[cap.id]

    def delete_b(request):
        assert request["body"] == b""
        remote_b[:] = [
            item
            for item in remote_b
            if item["serverName"] != payload_b["serverName"]
        ]
        return 204, {}, b""

    http_fixture.add(
        "DELETE",
        "/b/mcp-servers/" + payload_b["serverName"],
        delete_b,
    )
    assert catalog_client.post(
        "/api/v1/network/trf/catalog/publish",
        headers=headers(),
    ).json()["items"][0]["registration_status"] == "registered"

    withdrawn = catalog_client.post(
        "/api/v1/network/trf/catalog/unpublish",
        headers=headers(),
    )
    current = by_capability(withdrawn)[cap.id]
    assert current["registration_status"] == "unregistered"
    assert "sync_error" not in current
    assert withdrawn.json()["busy"] is False
    assert withdrawn.json()["can_withdraw"] is True
    assert [item["name"] for item in withdrawn.json()["remote_items"]] == [
        "nef-cap-unrelated"
    ]

    before = len(http_fixture.requests)
    configure_catalog(monkeypatch, target=target_a, base=base)
    old_cache = catalog_client.get("/api/v1/network/trf/catalog")
    assert len(http_fixture.requests) == before
    old_item = by_capability(old_cache)[cap.id]
    assert old_item["registration_status"] == "failed"
    assert old_item["sync_error"] == "upstream_http_error"
    assert old_cache.json()["can_withdraw"] is True


def test_refresh_recovers_exact_registration_and_missing_base_never_posts(
    catalog_client, http_fixture, monkeypatch
):
    cap = use_capabilities(monkeypatch, "target_detection")[0]
    target = http_fixture.url("/trf/api/v1/mcp-servers")
    base = "http://nef.example:8069"
    payload = trf_catalog._payloads(base)[cap.id]
    # Older TRF GET responses can still omit the optional field.
    remote = [{key: value for key, value in payload.items() if key != "isThirdParty"}]
    http_fixture.add(
        "GET",
        "/trf/api/v1/mcp-servers",
        lambda _request: json_response(remote),
    )

    configure_catalog(monkeypatch, target=target, base=base)
    refreshed = catalog_client.post(
        "/api/v1/network/trf/catalog/refresh",
        headers=headers(),
    )
    assert by_capability(refreshed)[cap.id]["registration_status"] == "registered"
    assert refreshed.json()["can_withdraw"] is True

    request_count = len(http_fixture.requests)
    configure_catalog(monkeypatch, target=target, base=None)
    blocked = catalog_client.post(
        "/api/v1/network/trf/catalog/publish",
        headers=headers(),
    )
    assert blocked.json()["base_configured"] is False
    assert blocked.json()["status"] == "not_configured"
    assert blocked.json()["items"][0]["sync_error"] == "nef_base_not_configured"
    assert len(http_fixture.requests) == request_count


def test_collection_metadata_trailing_slash_and_withdraw_after_restart(
    catalog_client, http_fixture, monkeypatch
):
    cap = use_capabilities(monkeypatch, "target_detection")[0]
    collection = "/trf/api/v1/mcp-servers"
    target = http_fixture.url(collection)
    base = "http://nef.example:8069"
    configure_catalog(monkeypatch, target=target + "/", base=base)
    remote: list[dict] = []
    foreign = {
        **trf_catalog._payloads(base)[cap.id],
        "serverName": "unrelated-service",
        "isThirdParty": True,
    }
    remote.append(foreign)
    http_fixture.add("GET", collection, lambda _r: json_response({
        "code": 200, "message": "OK",
        "data": {"items": [{**item, "id": index, "createdAt": "2026-09-22"}
                           for index, item in enumerate(remote)], "total": len(remote)},
    }))

    def publish(request):
        remote.append(json.loads(request["body"]))
        return 201, {}, b""

    http_fixture.add("POST", collection, publish)
    published = catalog_client.post("/api/v1/network/trf/catalog/publish", headers=headers())
    assert by_capability(published)[cap.id]["registration_status"] == "registered"
    assert remote[-1]["isThirdParty"] is False

    # A restart loses the local cache, not the remote registration.
    trf_catalog.reset_state_for_tests()
    payload = trf_catalog._payloads(base)[cap.id]

    def delete(request):
        assert request["body"] == b""
        remote[:] = [item for item in remote if item["serverName"] != payload["serverName"]]
        return 204, {}, b""

    http_fixture.add("DELETE", collection + "/" + payload["serverName"], delete)
    withdrawn = catalog_client.post("/api/v1/network/trf/catalog/unpublish", headers=headers())
    assert by_capability(withdrawn)[cap.id]["registration_status"] == "unregistered"
    assert withdrawn.json()["status"] == "synced"
    assert withdrawn.json()["can_withdraw"] is False
    assert remote == [foreign]
    assert [r["path"] for r in http_fixture.requests if r["method"] != "DELETE"] == [
        collection, collection, collection, collection, collection,
    ]
    assert [r["path"] for r in http_fixture.requests if r["method"] == "DELETE"] == [
        collection + "/" + payload["serverName"],
    ]


@pytest.mark.parametrize("action", ["refresh", "publish", "unpublish"])
def test_get_error_stays_failed_and_exposes_safe_diagnostic(
    catalog_client, http_fixture, monkeypatch, action
):
    cap = use_capabilities(monkeypatch, "target_detection")[0]
    target = http_fixture.url("/trf/api/v1/mcp-servers")
    configure_catalog(monkeypatch, target=target, base="http://nef.example:8069")
    http_fixture.add("GET", "/trf/api/v1/mcp-servers",
                     lambda _r: (503, {}, b"secret-debug-body"))
    response = catalog_client.post("/api/v1/network/trf/catalog/" + action, headers=headers())
    assert response.json()["status"] == "failed"
    assert by_capability(response)[cap.id]["sync_diagnostic"] == {
        "code": "upstream_http_error", "method": "GET", "http_status": 503,
    }
    assert "secret-debug-body" not in response.text
    assert target not in response.text
    assert [r["method"] for r in http_fixture.requests] == ["GET"]


def test_post_and_delete_errors_report_the_actual_method(
    catalog_client, http_fixture, monkeypatch
):
    cap = use_capabilities(monkeypatch, "target_detection")[0]
    path = "/trf/api/v1/mcp-servers"
    configure_catalog(monkeypatch, target=http_fixture.url(path), base="http://nef.example:8069")
    remote: list[dict] = []
    http_fixture.add("GET", path, lambda _r: json_response(remote))
    http_fixture.add("POST", path, lambda _r: (400, {}, b"private-body"))
    failed = catalog_client.post("/api/v1/network/trf/catalog/publish", headers=headers())
    assert by_capability(failed)[cap.id]["sync_diagnostic"] == {
        "code": "upstream_http_error", "method": "POST", "http_status": 400,
    }
    remote.append(trf_catalog._payloads("http://nef.example:8069")[cap.id])
    http_fixture.add("DELETE", path + "/" + remote[0]["serverName"],
                     lambda _r: (405, {}, b"private-delete-body"))
    failed = catalog_client.post("/api/v1/network/trf/catalog/unpublish", headers=headers())
    assert by_capability(failed)[cap.id]["sync_diagnostic"] == {
        "code": "upstream_http_error", "method": "DELETE", "http_status": 405,
    }
    assert failed.json()["can_withdraw"] is True
    assert "private-delete-body" not in failed.text
