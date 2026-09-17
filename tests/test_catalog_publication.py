"""Selected export and real HTTP publication, not a production directory test."""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from network_registry import build_router
from skills import CAP_INDEX
from test_network_registry import LocalHTTPFixture, configure, fake_auth, headers, json_response

PREVIEW = "/api/v1/network/catalog/publication"
PUBLISH = "/api/v1/network/catalog/publish"
SELECTION = {"capability_ids": ["target_detection"], "service_ids": ["robot_patrol", "collaborative_tracking"]}


@pytest.fixture
def client(monkeypatch):
    configure(monkeypatch)
    app = FastAPI()
    app.include_router(build_router(fake_auth))
    with TestClient(app) as client:
        yield client


def test_export_matches_actual_catalog_and_never_exports_secrets_or_private_tools(client):
    result = client.post(PREVIEW, json=SELECTION, headers=headers())
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["update_mode"] == "upsert_selected"
    assert data["execution_readiness"] == "not_verified"
    assert len(data["items"]) == 3
    atomic = data["items"][0]
    assert atomic["inputSchema"] == CAP_INDEX["target_detection"].mcp_tool()["inputSchema"]
    assert atomic["interfaces"][1]["tool_name"] == "target_detection"
    patrol = next(i for i in data["items"] if i["id"] == "robot_patrol")
    tracking = next(i for i in data["items"] if i["id"] == "collaborative_tracking")
    assert [i["mode"] for i in patrol["interfaces"]] == ["intent"]
    assert [i["mode"] for i in tracking["interfaces"]] == ["intent", "api", "tool"]
    assert all(route["url"].startswith("http://nef.test:8069/") for item in data["items"] for route in item["interfaces"])
    assert "caller-a" not in result.text and "receiver_key" not in result.text and "source_account" not in result.text
    reversed_selection = {**SELECTION, "service_ids": list(reversed(SELECTION["service_ids"]))}
    assert client.post(PREVIEW, json=reversed_selection, headers=headers()).json() == data
    reduced = client.post(PREVIEW, json={"capability_ids": ["target_detection"]}, headers=headers()).json()
    assert reduced["catalog_id"] == data["catalog_id"] and reduced["revision"] != data["revision"]


@pytest.mark.parametrize("selection", [
    {}, {"capability_ids": ["missing"]}, {"service_ids": ["missing"]},
    {"capability_ids": ["vital_sign_detection"]}, {"capability_ids": ["target_detection"] * 2},
    {"service_ids": ["robot_patrol"] * 2}, {"capability_ids": "target_detection"},
    {**SELECTION, "publish_url": "http://127.0.0.1:1/steal"},
])
def test_rejects_unavailable_duplicate_empty_or_caller_supplied_config(client, selection):
    assert client.post(PREVIEW, json=selection, headers=headers()).status_code == 422
    assert client.post(PUBLISH, json=selection, headers=headers()).status_code == 422


def test_authorization_and_missing_configuration(client, monkeypatch):
    for path in (PREVIEW, PUBLISH):
        assert client.post(path, json=SELECTION).status_code == 401
        assert client.post(path, json=SELECTION, headers=headers("caller-list")).status_code == 403
    assert client.post(PUBLISH, json=SELECTION, headers=headers()).status_code == 503
    monkeypatch.delenv("NEF_REGISTRY_CONFIG")
    assert client.post(PREVIEW, json=SELECTION, headers=headers()).json()["detail"]["code"] == "gateway_not_configured"


@pytest.mark.parametrize("ack,accepted", [({"accepted": True}, True), ({"accepted": False}, False), ({}, False)])
def test_publication_sends_exact_preview_and_requires_explicit_ack(client, monkeypatch, ack, accepted):
    peer = LocalHTTPFixture()
    try:
        peer.add("POST", "/publish", lambda r: json_response(ack))
        monkeypatch.setenv("TEST_DIRECTORY_TOKEN", "synthetic-directory-token")
        configure(monkeypatch, publish_url=peer.url("/publish"), token_env="TEST_DIRECTORY_TOKEN")
        preview = client.post(PREVIEW, json=SELECTION, headers=headers()).json()
        assert peer.requests == []
        result = client.post(PUBLISH, json=SELECTION, headers=headers())
        assert result.status_code == 200
        assert result.json()["accepted"] is accepted
        assert result.json()["sync_status"] == ("synced" if accepted else "submitted")
        assert result.json()["revision"] == preview["revision"]
        assert json.loads(peer.requests[0]["body"]) == preview
        assert peer.requests[0]["headers"]["authorization"] == "Bearer synthetic-directory-token"
        assert "synthetic-directory-token" not in result.text
    finally:
        peer.close()


def test_publish_failure_is_not_synced_and_does_not_follow_redirect(client, monkeypatch):
    peer = LocalHTTPFixture()
    try:
        peer.add("POST", "/publish", lambda r: (302, {"Location": peer.url("/other")}, b"secret-error"))
        configure(monkeypatch, publish_url=peer.url("/publish"))
        result = client.post(PUBLISH, json=SELECTION, headers=headers())
        assert result.status_code == 502 and "secret-error" not in result.text
        assert len(peer.requests) == 1
    finally:
        peer.close()
