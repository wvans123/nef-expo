# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_capabilities_list():
    r = client.get("/api/v1/capabilities")
    assert r.status_code == 200
    assert r.json()["count"] >= 17
