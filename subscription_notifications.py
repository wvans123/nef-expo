"""Bounded demo purchase notifications. Credentials and destinations are operator-only."""
import copy
import json
import math
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import HTTPException
from skills import CAP_INDEX
from integration_config import local_path, section as integration_section

EVENTS = {}
LOCK = threading.RLock()
MAX_EVENTS = 1000
SUBSCRIBER_ID = "subscriber-001"


def _settings():
    path = os.getenv("NEF_SUBSCRIPTION_CONFIG") or Path(__file__).parent / "config" / "subscription.local.json"
    try:
        cfg = (integration_section("subscriptions")
               if not os.getenv("NEF_SUBSCRIPTION_CONFIG") and local_path().exists()
               else json.loads(Path(path).read_text(encoding="utf-8-sig")))
    except FileNotFoundError:
        return None, "not_configured"
    except (OSError, ValueError):
        return None, "invalid_config"
    try:
        if not isinstance(cfg, dict):
            raise ValueError()
        accounts = cfg.get("account_ids")
        if accounts is not None and (not isinstance(accounts, list) or not all(isinstance(a, str) for a in accounts)):
            raise ValueError()
        plans = cfg.get("notify_plans")
        if plans is not None and (not isinstance(plans, list) or not all(isinstance(p, str) for p in plans)):
            raise ValueError()
        discount = cfg.get("discount")
        if discount is not None and (not _valid_price(discount) or not 0 < discount <= 1):
            raise ValueError()
        if type(cfg.get("reset_partner_plans_on_start", False)) is not bool:
            raise ValueError()
        if not isinstance(cfg.get("plan_prices", {}), dict):
            raise ValueError()
        raw_url = cfg.get("callback_url")
        if not raw_url:
            return cfg, None
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


def _config(account):
    cfg, code = _settings()
    if cfg is None:
        return cfg, code
    if not cfg.get("callback_url"):
        return None, "not_configured"
    if cfg.get("account_ids") is not None and account not in cfg["account_ids"]:
        return None, "account_not_enabled"
    return cfg, None


def _public(event):
    return {key: copy.deepcopy(event[key]) for key in
            ("event_id", "account_id", "plan_id", "status", "code", "attempts", "http_status", "last_attempt_at",
             "action", "request", "response", "price", "capability_ids")}


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


def unit_price(cid):
    match = re.search(r"\d+(?:\.\d+)?", str(CAP_INDEX[cid].unit_price))
    return Decimal(match[0]) if match else Decimal(0)


def quote(price_key, capability_ids, cfg=None):
    if cfg is None:
        cfg, _ = _settings()
    cfg = cfg or {}
    discount = cfg.get("discount")
    price = cfg.get("plan_prices", {}).get(price_key)
    if discount is not None:
        price = float((sum((unit_price(cid) for cid in capability_ids), Decimal(0))
                       * Decimal(str(discount))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {"price": float(price) if _valid_price(price) else None, "discount": discount}


def scene_plan_id(service_id):
    return str(uuid5(NAMESPACE_URL, "urn:nef:service-plan:scene:" + service_id))


def notify(snapshot, selections, network_capability_ids=None):
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


def _notify_plan(account, plan, network_capability_ids, action="create"):
    if network_capability_ids is None:
        network_capability_ids = [item["capability_id"] for item in plan["components"]
                                  if item["capability_id"] in CAP_INDEX
                                  and CAP_INDEX[item["capability_id"]].status == "available"]
    with LOCK:
        event_id = "sub_" + secrets.token_hex(12)
        plan_id = str(uuid5(NAMESPACE_URL, "urn:nef:service-plan:" + plan["kind"] + ":" + plan["id"]))
        definition = {"planId": plan_id, "showName": plan["name"], "description": plan["description"]}
        if network_capability_ids:
            definition["networkCapabilities"] = [
                {"capabilityName": cid, "showName": CAP_INDEX[cid].name, "description": CAP_INDEX[cid].description,
                 "price": float(unit_price(cid))}
                for cid in network_capability_ids
            ]
        event = {
            "event_id": event_id, "account_id": account, "plan_id": plan_id, "status": "pending", "code": None,
            "attempts": 0, "http_status": None, "last_attempt_at": None,
            "price_key": plan["kind"] + ":" + plan["id"],
            "definition": definition,
            "payload": None,
            "action": action, "request": None, "response": None, "price": None,
            "capability_ids": list(network_capability_ids),
        }
        if len(EVENTS) >= MAX_EVENTS:
            EVENTS.pop(next(iter(EVENTS)))
        EVENTS[event_id] = event
    return deliver(event_id, account)


def cancel(account, service_id):
    from scene_services import SCENES
    scene = SCENES[service_id]
    return _notify_plan(account, {"kind": "scene", "id": service_id, "name": scene["name"],
                                 "description": scene["description"], "components": []}, [], "delete")


def _redact(value, secrets_to_hide):
    if isinstance(value, dict):
        return {k: _redact(v, secrets_to_hide) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, secrets_to_hide) for v in value]
    if isinstance(value, str):
        for secret in secrets_to_hide:
            if secret:
                value = value.replace(secret, "[redacted]")
    return value


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
        if cfg.get("notify_plans") is not None and event["price_key"] not in cfg["notify_plans"]:
            with LOCK:
                event.update(status="not_applicable", code="plan_not_enabled")
                return _public(event)
        price = quote(event["price_key"], event["capability_ids"], cfg)["price"]
        if payload is None and event["action"] == "create":
            if price is None:
                with LOCK:
                    event.update(status="not_configured", code="price_not_configured")
                    return _public(event)
            payload = {"subscriberId": SUBSCRIBER_ID, "servicePlan": {**event["definition"], "price": float(price)}}
            with LOCK:
                event["payload"] = copy.deepcopy(payload)
                event["price"] = price
        token = os.getenv(cfg["token_env"]) if cfg.get("token_env") else None
        if cfg.get("token_env") and not token:
            code = "callback_key_missing"
        else:
            headers = {"Idempotency-Key": event_id, "X-NEF-Event-ID": event_id}
            if event["action"] == "create":
                headers["Content-Type"] = "application/json"
            if token:
                headers["Authorization"] = "Bearer " + token
            endpoint = cfg["callback_url"].rstrip("/")
            method = "POST"
            if event["action"] == "delete":
                method = "DELETE"
                endpoint += "/" + event["plan_id"] + "?subscriberId=" + SUBSCRIBER_ID
            parsed = urlsplit(endpoint)
            with LOCK:
                event["attempts"] += 1
                event["response"] = None
                event["request"] = {"method": method, "path": parsed.path + ("?" + parsed.query if parsed.query else ""),
                                    "headers": {k: v for k, v in headers.items() if k != "Authorization"},
                                    "body": copy.deepcopy(payload)}
            try:
                started = time.monotonic()
                with httpx.Client(timeout=5, trust_env=False, follow_redirects=False) as client:
                    with client.stream(method, endpoint, **({"json": payload} if method == "POST" else {}), headers=headers) as response:
                        http_status = response.status_code
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 65536 or time.monotonic() - started > 5:
                                raise ValueError()
                try:
                    reply = json.loads(raw) if raw else None
                except (ValueError, UnicodeDecodeError):
                    reply = raw.decode("utf-8", errors="replace")
                with LOCK:
                    event["response"] = {"http_status": http_status,
                                         "body": _redact(reply, [token, cfg["callback_url"], parsed.netloc])}
                error_code = reply.get("errorCode") if isinstance(reply, dict) else None
                if 200 <= http_status < 300:
                    status, code = "delivered", None
                elif method == "POST" and http_status == 400 and str(error_code) == "2053":
                    status, code = "delivered", "already_exists"
                elif method == "DELETE" and http_status == 404 and str(error_code) == "2051":
                    status, code = "delivered", "not_found"
                else:
                    status, code = "failed", "callback_failed"
            except (httpx.HTTPError, httpx.InvalidURL, ValueError):
                status, code = "failed", "callback_failed"
    with LOCK:
        event.update(status=status, code=code, http_status=http_status)
        return _public(event)


def list_for(account):
    with LOCK:
        return [_public(event) for event in reversed(list(EVENTS.values())) if event["account_id"] == account][:20]


def reset_partner_plans():
    """Explicit opt-in only: process startup must not silently delete remote state."""
    cfg, _ = _settings()
    if not cfg or not cfg.get("reset_partner_plans_on_start"):
        return []
    from scene_services import SCENES
    accounts = cfg.get("account_ids")
    account = accounts[0] if accounts else "1"
    results = [cancel(account, sid) for sid in SCENES]
    for sid, result in zip(SCENES, results):
        logging.getLogger("uvicorn.error").info("Partner plan reset scene:%s: HTTP %s (%s)", sid,
                                                result["http_status"], result["status"])
    return results
