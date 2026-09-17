"""Partner handoff contract: shipped bridge template -> HTTP -> result channel.

The execution service is a real local HTTP receiver. Callback requests exercise
NEF's actual ASGI routes; this is not evidence of a deployed partner integration.
"""
import base64
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import uuid

from fastapi.testclient import TestClient
import exhibition
from server import app


def test_shipped_scene_contract_and_partner_callbacks(tmp_path, monkeypatch):
    client = TestClient(app)
    seen = []

    class Partner(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append({
                "path": self.path,
                "body": json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                "request_id": self.headers.get("X-NEF-Request-ID"),
                "authorization": self.headers.get("Authorization"),
                "content_type": self.headers.get("Content-Type"),
            })
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"received":true,"message":"accepted"}')

        def log_message(self, *args):
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Partner)
    worker = threading.Thread(target=upstream.serve_forever, daemon=True)
    worker.start()
    channel_id = None
    try:
        config = json.loads((Path(__file__).parents[1] / "config/bridge.example.json").read_text(encoding="utf-8"))
        base = f"http://127.0.0.1:{upstream.server_port}"
        for routes in config["scenes"].values():
            for route in routes.values():
                route["url"] = base + urlsplit(route["url"]).path
        config_path = tmp_path / "bridge.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        monkeypatch.setenv("NEF_BRIDGE_CONFIG", str(config_path))
        monkeypatch.setenv("NEF_INTERNAL_TOKEN", "local-test-internal-token")
        registered = client.post("/api/v1/register", json={"account": "handoff-" + uuid.uuid4().hex, "plan": "free"})
        assert registered.status_code == 200
        af = {"Authorization": "Bearer " + registered.json()["api_key"], "X-NEF-Execution": "live"}
        for scene in config["scenes"]:
            assert client.post(f"/api/v1/services/{scene}/subscribe", headers=af).status_code == 200
        channel = client.post("/api/v1/exhibition/channels", headers=af, json={"name": "handoff-test", "service_id": "robot_patrol"}).json()
        channel_id = channel["id"]
        writer = {"Authorization": "Bearer " + channel["receiver_key"]}
        feedback = channel["feedback_endpoint"]
        results = []
        intents = [("robot_patrol", "  巡检园区 A，返回现场画面\n"), ("traffic_flow_detection", "检测 A 路口车流"), ("collaborative_tracking", "  追踪指定目标并返回文字报告\n")]
        for scene, text in intents:
            response = client.post(f"/api/v1/services/{scene}/intent", headers=af, json={"text": text})
            assert response.status_code == 200
            results.append(response.json())
        args = {"device_id": "terminal-01", "video_source": "camera-01", "target": "指定移动目标"}
        response = client.post("/api/v1/services/collaborative_tracking/invoke", headers=af, json=args)
        assert response.status_code == 200
        results.append(response.json())
        response = client.post("/mcp", headers=af, json={"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "scene_collaborative_tracking", "arguments": args}})
        assert response.status_code == 200
        results.append(json.loads(response.json()["result"]["content"][0]["text"]))
        assert [r["path"] for r in seen] == ["/scenes/patrol", "/scenes/traffic", "/scenes/tracking/intent", "/scenes/tracking", "/scenes/tracking"]
        assert [r["body"] for r in seen[:3]] == [{"serviceId": scene, "text": text} for scene, text in intents]
        assert seen[3]["body"] == seen[4]["body"] == {"serviceId": "collaborative_tracking", "input": args}
        assert len({r["request_id"] for r in seen}) == 5
        for observed, result in zip(seen, results):
            assert observed["authorization"] == "Bearer local-test-internal-token" != af["Authorization"]
            assert observed["content_type"].startswith("application/json")
            assert observed["request_id"] == result["request_id"]
            assert result["data_source"] == "live" and result["status"] == "forwarded"
            assert result["upstream"] == {"http_status": 202, "body": {"received": True, "message": "accepted"}}
            assert "intent_id" not in result and "task_id" not in result

        event = {"kind": "status", "title": "巡检进行中", "source": "robot-patrol-service", "request_id": seen[0]["request_id"], "data": {"state": "running"}}
        first = client.post(feedback, headers=writer, json=event)
        assert first.status_code == 200 and first.json() == {"received": True, "event_id": 1}
        # Current contract intentionally does not promise request/event deduplication.
        assert client.post(feedback, headers=writer, json=event).json()["event_id"] == 2
        independent = {"kind": "data", "title": "车流观测", "data": {"vehicle_count": 18, "window_seconds": 60}}
        assert client.post(feedback, headers=writer, json=independent).status_code == 200
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
        upload = client.post(feedback, headers={**writer, "Content-Type": "image/png"}, content=png)
        assert upload.status_code == 200
        assert upload.json() == {"received": True, "event_id": 4}
        saved = client.get(channel["events_endpoint"], headers=af).json()["events"]
        assert saved[0]["request_id"] == seen[0]["request_id"]
        assert "request_id" not in saved[2] and saved[2]["data"] == independent["data"]
        asset = saved[3]["asset_id"]
        assert saved[3]["kind"] == "image"
        assert client.get(channel["events_endpoint"], headers=writer).status_code == 401
        assert client.post(channel["events_endpoint"], headers=af, json=event).status_code == 401
        assert client.get(channel["media_endpoint"] + "/" + asset, headers=af).content == png
    finally:
        if channel_id:
            exhibition.CHANNELS.pop(channel_id, None)
        upstream.shutdown()
        upstream.server_close()
        worker.join(timeout=2)
