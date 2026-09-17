"""Single-address feedback contract; keys route writes without caller scene IDs."""
import base64
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
import exhibition
from server import app

client = TestClient(app)
URL = "/api/v1/scene-feedback"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


@pytest.fixture(autouse=True)
def isolated():
    exhibition.CHANNELS.clear()
    yield
    exhibition.CHANNELS.clear()


def provision(service="robot_patrol"):
    key = client.post("/api/v1/register", json={"account": "feedback-" + uuid.uuid4().hex, "plan": "free"}).json()["api_key"]
    owner = {"Authorization": "Bearer " + key}
    body = {"name": "场景测试"}
    if service:
        body["service_id"] = service
    response = client.post("/api/v1/exhibition/channels", headers=owner, json=body)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    channel = response.json()
    assert channel["feedback_endpoint"] == URL
    return owner, channel, {"Authorization": "Bearer " + channel["receiver_key"]}


def events(owner, channel):
    return client.get(channel["events_endpoint"], headers=owner).json()["events"]


def test_json_routes_by_key_not_caller_scene_or_channel():
    owner_a, a, write_a = provision()
    owner_b, b, _ = provision("traffic_flow_detection")
    response = client.post(URL, headers=write_a, json={"kind": "status", "text": "巡检中", "service_id": "traffic_flow_detection", "channel_id": b["id"]})
    assert response.json() == {"received": True, "event_id": 1}
    saved = events(owner_a, a)
    assert saved[0]["text"] == "巡检中" and "channel_id" not in saved[0]
    assert events(owner_b, b) == []
    assert client.post(URL, headers=write_a, json={"kind": "data", "data": {"count": 3}, "request_id": "optional-id"}).status_code == 200
    assert events(owner_a, a)[1]["request_id"] == "optional-id"
    listed = client.get("/api/v1/exhibition/channels", headers=owner_a).json()["channels"]
    assert listed[0]["service_id"] == "robot_patrol" and "receiver_key" not in listed[0]
    assert client.get(b["events_endpoint"], headers=owner_a).status_code == 404


def test_raw_image_upload_automatically_publishes_and_remains_owner_only():
    owner, channel, writer = provision()
    response = client.post(URL, headers={**writer, "Content-Type": "image/png", "X-NEF-Request-ID": "optional-image-id"}, content=PNG)
    assert response.status_code == 200
    assert response.json() == {"received": True, "event_id": 1}
    saved = events(owner, channel)
    assert len(saved) == 1 and saved[0]["kind"] == "image"
    assert saved[0]["request_id"] == "optional-image-id"
    media_url = channel["media_endpoint"] + "/" + saved[0]["asset_id"]
    assert client.get(media_url, headers=owner).content == PNG
    assert client.get(media_url, headers=writer).status_code == 401
    assert client.post(URL, headers=owner, json={"kind": "status"}).status_code == 401
    assert client.post(URL, json={"kind": "status"}).status_code == 401
    _, other, other_writer = provision("traffic_flow_detection")
    assert client.post(URL, headers=other_writer, json={"kind": "image", "asset_id": saved[0]["asset_id"]}).status_code == 422


@pytest.mark.parametrize("mime,content,kind", [
    ("image/jpeg", b"\xff\xd8\xffheaders-only", "image"),
    ("image/webp", b"RIFF0000WEBPheaders-only", "image"),
    ("video/mp4", b"\x00\x00\x00\x18ftypisomheaders-only", "video"),
    ("video/webm", b"\x1aE\xdf\xa3headers-only", "video"),
])
def test_media_signature_dispatch_not_decoder_validation(mime, content, kind):
    owner, channel, writer = provision()
    response = client.post(URL, headers={**writer, "Content-Type": mime}, content=content)
    assert response.status_code == 200
    assert events(owner, channel)[0]["kind"] == kind


def test_legacy_unbound_key_and_old_two_step_upload_still_work():
    owner, channel, writer = provision(None)
    assert channel["service_id"] is None
    assert client.post(URL, headers=writer, json={"kind": "status", "text": "兼容"}).status_code == 200
    asset = client.post(channel["media_endpoint"], headers={**writer, "Content-Type": "image/png"}, content=PNG).json()["asset_id"]
    assert len(events(owner, channel)) == 1
    assert client.post(channel["events_endpoint"], headers=writer, json={"kind": "image", "asset_id": asset}).status_code == 200
    assert len(events(owner, channel)) == 2
    assert client.post("/api/v1/exhibition/channels", headers=owner, json={"name": "bad", "service_id": "unknown"}).status_code == 422


def test_invalid_feedback_has_no_partial_writes(monkeypatch):
    owner, channel, writer = provision()
    for body in [[], {"kind": "unknown"}, {"kind": "data", "data": "not-object"}, {"kind": "status", "request_id": 42}]:
        assert client.post(URL, headers=writer, json=body).status_code == 422
    assert client.post(URL, headers={**writer, "Content-Type": "application/json"}, content=b"{bad").status_code == 422
    for mime, content in [("text/html", b"<html>"), ("image/png", b"not-image"), ("multipart/form-data", PNG)]:
        assert client.post(URL, headers={**writer, "Content-Type": mime}, content=content).status_code == 415
    assert client.post(URL, headers={**writer, "Content-Type": "image/png", "X-NEF-Request-ID": "x" * 1001}, content=PNG).status_code == 422
    monkeypatch.setattr(exhibition, "MAX_UPLOAD", len(PNG) - 1)
    assert client.post(URL, headers={**writer, "Content-Type": "image/png"}, content=PNG).status_code == 413
    monkeypatch.setattr(exhibition, "MAX_JSON", 4)
    assert client.post(URL, headers=writer, json={"kind": "status"}).status_code == 413
    assert events(owner, channel) == []
    assert exhibition.CHANNELS[channel["id"]]["media"] == {}


def test_concurrent_capacity_failure_cannot_publish_or_leave_orphan(monkeypatch):
    owner, channel, writer = provision()
    monkeypatch.setattr(exhibition, "MAX_MEDIA_TOTAL", len(PNG))
    def upload(_):
        with TestClient(app) as local:
            return local.post(URL, headers={**writer, "Content-Type": "image/png"}, content=PNG).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(upload, range(2))) == [200, 507]
    assert len(events(owner, channel)) == len(exhibition.CHANNELS[channel["id"]]["media"]) == 1


def test_automatic_access_is_reused_isolated_and_write_only():
    key = client.post('/api/v1/register', json={'account':'auto-'+uuid.uuid4().hex}).json()['api_key']
    owner = {'Authorization':'Bearer '+key}
    path='/api/v1/services/robot_patrol/feedback-access'
    first=client.post(path,headers=owner)
    assert first.status_code==200 and first.headers['cache-control']=='no-store'
    a=first.json()
    assert client.post(path,headers=owner).json()==a
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _: client.post(path,headers=owner).json(),range(4)))
    assert all(r==a for r in responses)
    writer={'Authorization':'Bearer '+a['receiver_key']}
    assert client.post('/api/v1/scene-feedback',headers=writer,json={'kind':'status','text':'巡检已完成'}).status_code==200
    events_path='/api/v1/exhibition/channels/'+a['id']+'/events'
    assert client.get(events_path,headers=owner).json()['events'][0]['text']=='巡检已完成'
    assert client.post(path,headers=writer).status_code==401
    assert client.post(path).status_code==401
    assert client.post('/api/v1/services/unknown/feedback-access',headers=owner).status_code==404
    other_key=client.post('/api/v1/register',json={'account':'auto-other-'+uuid.uuid4().hex}).json()['api_key']
    other={'Authorization':'Bearer '+other_key}
    b=client.post(path,headers=other).json()
    assert b['id']!=a['id'] and b['receiver_key']!=a['receiver_key']
    assert client.get(events_path,headers=other).status_code==404
    listing=client.get('/api/v1/exhibition/channels',headers=owner).text
    assert a['receiver_key'] not in listing and 'access_key' not in listing


def test_json_request_header_correlation_and_conflicts():
    owner, channel, writer = provision()
    headers = {**writer, "X-NEF-Request-ID": "request-a"}
    assert client.post(URL, headers=headers, json={"kind": "status", "text": "received"}).status_code == 200
    assert client.post(URL, headers=headers, json={"kind": "data", "request_id": "request-a", "data": {}}).status_code == 200
    assert client.post(URL, headers=headers, json={"kind": "status", "request_id": "request-b"}).status_code == 422
    for invalid_id in ("", "x" * 1001):
        assert client.post(URL, headers={**writer, "X-NEF-Request-ID": invalid_id},
                           json={"kind": "status"}).status_code == 422
    saved = events(owner, channel)
    assert len(saved) == 2 and all(event["request_id"] == "request-a" for event in saved)


def test_event_cursor_filter_reset_and_owner_isolation():
    owner, channel, writer = provision()
    for request_id in ("request-a", "request-b", "request-a"):
        assert client.post(URL, headers=writer, json={"kind": "status", "request_id": request_id}).status_code == 200
    endpoint = channel["events_endpoint"]
    result = client.get(endpoint, headers=owner, params={"after": 1, "request_id": "request-a"}).json()
    assert [event["id"] for event in result["events"]] == [3]
    assert result["next_cursor"] == 3 and not result["reset_required"] and not result["history_truncated"]
    empty = client.get(endpoint, headers=owner, params={"after": 3}).json()
    assert empty["events"] == [] and empty["next_cursor"] == 3
    no_match = client.get(endpoint, headers=owner, params={"request_id": "missing"}).json()
    assert no_match["events"] == [] and no_match["next_cursor"] == 3
    reset = client.get(endpoint, headers=owner, params={"after": 99}).json()
    assert reset["reset_required"] and len(reset["events"]) == 3 and reset["next_cursor"] == 3
    assert client.get(endpoint, headers=owner, params={"after": -1}).status_code == 422
    assert client.get(endpoint, headers=owner, params={"request_id": ""}).status_code == 422
    assert client.get(endpoint, headers=writer).status_code == 401
    other_owner, _, _ = provision()
    assert client.get(endpoint, headers=other_owner).status_code == 404


def test_cursor_reports_evicted_history():
    owner, channel, writer = provision()
    for number in range(102):
        assert client.post(URL, headers=writer, json={"kind": "data", "data": {"n": number}}).status_code == 200
    result = client.get(channel["events_endpoint"], headers=owner, params={"after": 0}).json()
    assert result["history_truncated"] and len(result["events"]) == 100
    assert result["events"][0]["id"] == 3 and result["next_cursor"] == 102
    retained = client.get(channel["events_endpoint"], headers=owner, params={"after": 2}).json()
    assert not retained["history_truncated"]
