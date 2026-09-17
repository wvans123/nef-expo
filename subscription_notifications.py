"""Bounded demo purchase notifications. Credentials and destinations are operator-only."""
import copy
import json
import math
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException
from skills import CAP_INDEX

EVENTS = {}
LOCK = threading.RLock()
MAX_EVENTS = 1000


def _config(account):
    path = os.getenv("NEF_SUBSCRIPTION_CONFIG") or Path(__file__).parent / "config" / "subscription.local.json"
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, "not_configured"
    except (OSError, ValueError):
        return None, "invalid_config"
    try:
        if not isinstance(cfg, dict):
            raise ValueError()
        if not cfg.get("callback_url"):
            return None, "not_configured"
        accounts = cfg["account_ids"]
        if not isinstance(accounts, list) or not all(isinstance(a, str) for a in accounts):
            raise ValueError()
        if account not in accounts:
            return None, "account_not_enabled"
        raw_url = cfg["callback_url"]
        if not isinstance(raw_url, str) or any(char.isspace() or ord(char) < 32 for char in raw_url):
            raise ValueError()
        url = urlsplit(raw_url)
        if (url.scheme not in ("http", "https") or not url.hostname or url.username or url.password
                or url.query or url.fragment):
            raise ValueError()
        url.port
        token_env = cfg.get("token_env")
        if token_env is not None and (not isinstance(token_env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token_env)):
            raise ValueError()
        # Allow HTTP for explicitly configured same-day LAN peers, never with credentials.
        if token_env and url.scheme != "https" and url.hostname not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError()
        if not isinstance(cfg.get("plan_prices", {}), dict):
            raise ValueError()
        return cfg, None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, "invalid_config"


def _public(event):
    return {key: copy.deepcopy(event[key]) for key in
            ("event_id", "account_id", "plan_id", "status", "code", "attempts", "http_status", "last_attempt_at")}


def _valid_price(price):
    try:
        return type(price) in (int, float) and math.isfinite(price) and price >= 0
    except OverflowError:
        return False


def validate_capabilities(selected, allowed):
    if (len(selected) != len(set(selected))
            or any(cid not in allowed or cid not in CAP_INDEX or CAP_INDEX[cid].status != "available"
                   for cid in selected)):
        raise HTTPException(422, "网络能力须从当前套餐的可用能力中选择，不能重复")


def notify(snapshot, selections, network_capability_ids=()):
    account = snapshot["account_id"]
    results = []
    for plan in snapshot["purchased_packages"]:
        if (plan["kind"], plan["id"]) not in selections:
            continue
        results.append(_notify_plan(account, plan, network_capability_ids))
    if not results:
        return {"status": "not_applicable", "notifications": []}
    result = next((item for item in results if item["status"] != "delivered"), results[0])
    return {**result, "notifications": results}


def _notify_plan(account, plan, network_capability_ids):
    with LOCK:
        event_id = "sub_" + secrets.token_hex(12)
        plan_id = str(uuid5(NAMESPACE_URL, "urn:nef:service-plan:" + plan["kind"] + ":" + plan["id"]))
        definition = {"planId": plan_id, "showName": plan["name"], "description": plan["description"]}
        if network_capability_ids:
            definition["networkCapabilities"] = [
                {"capabilityName": cid, "showName": CAP_INDEX[cid].name, "description": CAP_INDEX[cid].description}
                for cid in network_capability_ids
            ]
        event = {
            "event_id": event_id, "account_id": account, "plan_id": plan_id, "status": "pending", "code": None,
            "attempts": 0, "http_status": None, "last_attempt_at": None,
            "price_key": plan["kind"] + ":" + plan["id"],
            "definition": definition,
            "payload": None,
        }
        if len(EVENTS) >= MAX_EVENTS:
            EVENTS.pop(next(iter(EVENTS)))
        EVENTS[event_id] = event
    return deliver(event_id, account)


def deliver(event_id, account):
    with LOCK:
        event = EVENTS.get(event_id)
        if not event or event["account_id"] != account:
            raise HTTPException(404, "订购通知不存在")
        if event["status"] == "sending":
            raise HTTPException(409, "订购通知正在发送")
        if event["status"] == "delivered":
            return _public(event)
        event["status"] = "sending"
        event["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
        payload = copy.deepcopy(event["payload"])
    cfg, code = _config(account)
    status, http_status = "not_configured" if code in ("not_configured", "account_not_enabled") else "failed", None
    if cfg is not None:
        price = cfg.get("plan_prices", {}).get(event["price_key"])
        if payload is None and not _valid_price(price):
            with LOCK:
                event.update(status="not_configured", code="price_not_configured")
                return _public(event)
        if payload is None:
            payload = {"subscriberId": account, "servicePlan": {**event["definition"], "price": float(price)}}
            with LOCK:
                event["payload"] = copy.deepcopy(payload)
        token = os.getenv(cfg["token_env"]) if cfg.get("token_env") else None
        if cfg.get("token_env") and not token:
            code = "callback_key_missing"
        else:
            headers = {"Idempotency-Key": event_id, "X-NEF-Event-ID": event_id}
            if token:
                headers["Authorization"] = "Bearer " + token
            with LOCK:
                event["attempts"] += 1
            try:
                started = time.monotonic()
                with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                    with client.stream("POST", cfg["callback_url"], json=payload, headers=headers) as response:
                        http_status = response.status_code
                        response.raise_for_status()
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 65536 or time.monotonic() - started > 5:
                                raise ValueError()
                # Only transport delivery is known until the partner defines business receipts.
                status, code = "delivered", None
            except (httpx.HTTPError, httpx.InvalidURL, ValueError):
                status, code = "failed", "callback_failed"
    with LOCK:
        event.update(status=status, code=code, http_status=http_status)
        return _public(event)


def list_for(account):
    with LOCK:
        return [_public(event) for event in reversed(list(EVENTS.values())) if event["account_id"] == account][:20]
