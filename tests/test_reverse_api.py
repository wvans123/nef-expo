# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
import registry
from server import app

client = TestClient(app)


def setup_function():
    registry.THIRD_PARTY.clear()
    registry.THIRD_PARTY_META.clear()
    registry.REVERSE_CALLS.clear()


def _key(account="af_tester"):
    r = client.post("/api/v1/subscribe",
                    json={"account": account, "capability_ids": ["network_diagnosis"], "package_ids": []})
    return r.json()["api_key"]


def _hdr(key):
    return {"Authorization": f"Bearer {key}"}


def _register(key, name="工业缺陷识别模型", keywords=None):
    body = {"name": name, "cap_type": "ai_model", "description": "缺陷识别",
            "endpoint": "https://my-af.com/api/detect"}
    if keywords is not None:
        body["intent_keywords"] = keywords
    r = client.post("/api/v1/register-af", json=body, headers=_hdr(key))
    assert r.status_code == 200
    return r.json()["registration_id"]


def test_register_af_stores_keywords_and_owner():
    key = _key()
    cap_id = _register(key, keywords=["质检", "缺陷"])
    cap = next(c for c in registry.THIRD_PARTY if c.id == cap_id)
    assert cap.intent_keywords == ["质检", "缺陷"]
    meta = registry.THIRD_PARTY_META[cap_id]
    assert meta["owner"] == "af_tester"
    assert meta["cap_type"] == "ai_model"


def test_register_af_default_keywords_is_name():
    key = _key()
    cap_id = _register(key)  # 不传 keywords
    cap = next(c for c in registry.THIRD_PARTY if c.id == cap_id)
    assert cap.intent_keywords == ["工业缺陷识别模型"]


def test_registered_cap_visible_in_marketplace():
    key = _key()
    cap_id = _register(key)
    r = client.get("/api/v1/capabilities")
    ids = [c["id"] for c in r.json()["capabilities"]]
    assert cap_id in ids
