"""Portable configuration and startup without contacting configured remote services."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi import HTTPException

import exhibition
import integration_config
import network_registry
import start
import subscription_notifications
import uvicorn


def test_start_initializes_templates_and_preserves_operator_changes(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in ("integration", "composer"):
        (config_dir / f"{name}.example.json").write_text('{"example": true}', encoding="utf-8")
    target = config_dir / "integration.local.json"
    monkeypatch.setattr(start, "ROOT", tmp_path)
    monkeypatch.setenv("NEF_INTEGRATION_CONFIG", str(target))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["start.py"])
    runs = []
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: runs.append((args, kwargs)))
    start.main()
    assert json.loads(target.read_text()) == {"example": True}
    assert (config_dir / "composer.local.json").exists()
    assert runs == [(("server:app",), {"host": "0.0.0.0", "port": 8069})]
    target.write_text('{"operator": true}', encoding="utf-8")
    start.prepare_configs()
    assert json.loads(target.read_text()) == {"operator": True}


def test_unified_config_is_hot_read_by_all_integration_modules(tmp_path, monkeypatch):
    path = tmp_path / "integration.json"
    monkeypatch.setenv("NEF_INTEGRATION_CONFIG", str(path))
    for name in ("NEF_BRIDGE_CONFIG", "NEF_REGISTRY_CONFIG", "NEF_SUBSCRIPTION_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    config = {
        "bridge": {"intent": {"url": "http://127.0.0.1:9876/intent"}},
        "registry": {"publish_url": "http://127.0.0.1:9876/register"},
        "subscriptions": {
            "callback_url": "http://127.0.0.1:9876/business/v1/service-plans",
            "account_ids": ["1"], "plan_prices": {"scene:robot_patrol": 0},
        },
    }
    path.write_text(json.dumps(config), encoding="utf-8-sig")
    assert exhibition.config() == config["bridge"]
    assert network_registry._load_config()["publish_url"] == config["registry"]["publish_url"]
    assert subscription_notifications._config("1") == (config["subscriptions"], None)
    config["subscriptions"]["callback_url"] = "http://127.0.0.1:9877/business/v1/service-plans"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert subscription_notifications._config("1")[0]["callback_url"] == config["subscriptions"]["callback_url"]
    assert subscription_notifications._config("2")[1] == "account_not_enabled"


def test_explicit_legacy_override_takes_precedence(tmp_path, monkeypatch):
    unified = tmp_path / "integration.json"
    unified.write_text('{"bridge": {}, "registry": {}, "subscriptions": {}}', encoding="utf-8")
    monkeypatch.setenv("NEF_INTEGRATION_CONFIG", str(unified))
    legacy = tmp_path / "legacy.json"
    config = {"callback_url": "http://127.0.0.1:9876/plans", "account_ids": ["1"],
              "publish_url": "http://127.0.0.1:9876/register"}
    legacy.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("NEF_SUBSCRIPTION_CONFIG", str(legacy))
    assert subscription_notifications._config("1") == (config, None)
    monkeypatch.setenv("NEF_BRIDGE_CONFIG", str(legacy))
    assert exhibition.config() == config
    monkeypatch.setenv("NEF_REGISTRY_CONFIG", str(legacy))
    assert network_registry._load_config()["publish_url"] == config["publish_url"]


def test_missing_unified_config_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("NEF_INTEGRATION_CONFIG", str(tmp_path / "missing.json"))
    assert integration_config.section("bridge") == {}


@pytest.mark.parametrize(
    "field,reply,content_type,expected",
    [
        ("intent", b'{"vendor_ack":{"code":7},"ticket":"r-42"}',
         "application/json", {"vendor_ack": {"code": 7}, "ticket": "r-42"}),
        ("goal", b"queued for patrol", "text/plain", "queued for patrol"),
    ],
)
def test_robot_template_maps_intent_and_preserves_unknown_reply(
    tmp_path, monkeypatch, field, reply, content_type, expected
):
    config = json.loads(
        (Path(__file__).parents[1] / "config/integration.example.json").read_text(encoding="utf-8")
    )
    path = tmp_path / "integration.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("NEF_INTEGRATION_CONFIG", str(path))
    monkeypatch.delenv("NEF_BRIDGE_CONFIG", raising=False)
    context = {"service_id": "robot_patrol", "text": "  Patrol sector A\n", "request_id": "robot-test"}
    seen = []

    class Partner(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(202)
            self.send_header("Content-Type", content_type)
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Partner) as upstream:
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        try:
            # An unfilled operator template must not send a request.
            with pytest.raises(HTTPException) as error:
                exhibition.forward("scene_intent", context)
            assert error.value.status_code == 503
            assert seen == []
            route = config["bridge"]["scenes"]["robot_patrol"]["intent"]
            route["url"] = f"http://127.0.0.1:{upstream.server_port}/robot/execute"
            route["body"] = {field: "$text"}
            path.write_text(json.dumps(config), encoding="utf-8")
            result = exhibition.forward("scene_intent", context)
            assert seen == [("/robot/execute", {field: context["text"]})]
            assert result["upstream"] == {"http_status": 202, "body": expected}
            assert result["status"] == "forwarded"
            assert "task_id" not in result and "intent_id" not in result
        finally:
            upstream.shutdown()
            thread.join(timeout=2)
