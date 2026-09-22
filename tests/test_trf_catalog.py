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
