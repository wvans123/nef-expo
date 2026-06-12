# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient
from server import app

client = TestClient(app)


def test_capabilities_list():
    r = client.get("/api/v1/capabilities")
    assert r.status_code == 200
    assert r.json()["count"] >= 17


def test_v2_catalog_counts():
    r = client.get("/api/v1/capabilities")
    caps = r.json()["capabilities"]
    available = [c for c in caps if c["status"] == "available"]
    planned = [c for c in caps if c["status"] == "planned"]
    assert len(available) >= 23
    assert len(planned) == 9
    assert all(c.get("icon") for c in caps)


def test_v2_packages():
    r = client.get("/api/v1/packages")
    pkgs = r.json()["packages"]
    assert len(pkgs) == 9
    ids = {p["id"] for p in pkgs}
    assert {"live_offload", "robot_patrol", "xr_render", "uav_track", "traffic_forecast_pkg"} <= ids
    # 套餐内能力必须全部为 available（planned 不可进套餐）
    for p in pkgs:
        for c in p["capability_details"]:
            assert c["status"] == "available"
