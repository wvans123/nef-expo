# -*- coding: utf-8 -*-
"""Explicit, bounded synchronization of NEF built-in capabilities to TRF."""
from __future__ import annotations

import copy
import hashlib
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import APIRouter, Header, Response

import network_registry as registry
from skills import (
    CAP_INDEX,
    TRF_TOOL_TYPES,
    capability_tool_type,
    trf_catalog_capabilities,
)


_STATE_LOCK = threading.RLock()
_STATES: dict[tuple[str, str], dict[str, Any]] = {}
_MANAGED: dict[tuple[str, str], dict[str, Any]] = {}
_BUSY = False
_GROUPS = {
    "nf": ("nf tool", "网络功能能力"),
    "computing": ("computing tool", "计算能力"),
    "sensing": ("sensing tool", "感知能力"),
}


def reset_state_for_tests() -> None:
    global _BUSY
    with _STATE_LOCK:
        _STATES.clear()
        _MANAGED.clear()
        _BUSY = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _context() -> dict[str, Any]:
    try:
        config = registry._load_config()
    except registry._ConfigError:
        return {
            "valid": False,
            "target": None,
            "base": None,
            "token_env": None,
            "key": ("", ""),
        }
    target = config.get("trf_mcp_servers_url")
    base = config.get("nef_base_url")
    if base:
        base = base.rstrip("/")
    return {
        "valid": True,
        "target": target,
        "base": base,
        "token_env": config.get("token_env"),
        "key": (target or "", base or ""),
    }


def _capabilities() -> list[Any]:
    # Resolve through the canonical index so this module never creates a second catalog.
    return [
        CAP_INDEX[cap.id]
        for cap in trf_catalog_capabilities()
        if cap.id in CAP_INDEX
    ]


def _server_name(base: str | None, group_id: str) -> str:
    digest = hashlib.sha256((base or "").encode("utf-8")).hexdigest()[:8]
    return f"nef-group-{digest}-{group_id}"


def _group_capabilities() -> dict[str, list[Any]]:
    capabilities = _capabilities()
    return {
        group_id: [cap for cap in capabilities if capability_tool_type(cap) == tool_type]
        for group_id, (tool_type, _name) in _GROUPS.items()
    }


def _payloads(base: str | None) -> dict[str, dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {}
    for group_id, caps in _group_capabilities().items():
        if not caps:
            continue
        tool_type, name = _GROUPS[group_id]
        values[group_id] = {
            "serverName": _server_name(base, group_id),
            "serverType": "Streamable HTTP",
            "toolType": tool_type,
            "description": f"NEF {name}，包括：" + "、".join(cap.name for cap in caps),
            "url": base or "",
            "serverStatus": "active",
            "isThirdParty": False,
        }
    return values


def _legacy_payloads(base: str | None) -> dict[str, dict[str, Any]]:
    """Recognize the previous release only for explicit withdrawal, never POST it."""
    if not base:
        return {}
    digest = hashlib.sha256(base.encode("utf-8")).hexdigest()[:8]
    return {
        "legacy:" + cap.id: {
            "serverName": f"nef-cap-{digest}-{cap.id}",
            "toolType": capability_tool_type(cap),
            "url": f"{base}/mcp/capabilities/{cap.id}",
            "isThirdParty": False,
        }
        for cap in _capabilities()
    }


def _new_state(context: dict[str, Any]) -> dict[str, Any]:
    if not context["valid"]:
        status = "failed"
    elif not context["target"]:
        status = "not_configured"
    else:
        status = "unknown"
    return {
        "status": status,
        "last_checked": None,
        "items": {},
        "remote_items": [],
        "ignored_count": 0,
    }


def _state_for(context: dict[str, Any]) -> dict[str, Any]:
    return _STATES.setdefault(context["key"], _new_state(context))


def _set_item(
    state: dict[str, Any],
    entry_id: str,
    registration_status: str,
    sync_error: str | registry._RemoteFailure | None = None,
) -> None:
    item = {"registration_status": registration_status}
    if isinstance(sync_error, registry._RemoteFailure):
        item["sync_error"] = sync_error.code
        item["sync_diagnostic"] = registry._trf_error_detail(sync_error)
    elif sync_error:
        item["sync_error"] = sync_error
    state["items"][entry_id] = item


def _remote_projection(
    servers: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    projected: list[dict[str, Any]] = []
    ignored = 0
    for server in servers:
        if server["toolType"] not in TRF_TOOL_TYPES:
            ignored += 1
            continue
        item = {
            "id": "trf:" + server["serverName"],
            "name": server["serverName"],
            "description": server["description"],
            "toolType": server["toolType"],
            "serverStatus": server["serverStatus"],
            "serverType": server["serverType"],
        }
        if "isThirdParty" in server:
            item["isThirdParty"] = server["isThirdParty"]
        projected.append(item)
    return projected, ignored


def _matching(
    remote: list[dict[str, Any]],
    payload: dict[str, Any],
) -> tuple[bool, bool]:
    same_name = [
        item for item in remote
        if item["serverName"] == payload["serverName"]
    ]
    return (
        any(registry._same_trf_server(item, payload) for item in same_name),
        bool(same_name),
    )


def _remember(
    state_key: tuple[str, str],
    target: str,
    token_env: str | None,
    entry_id: str,
    payload: dict[str, Any],
) -> None:
    _MANAGED[(target, payload["serverName"])] = {
        "state_key": state_key,
        "target": target,
        "token_env": token_env,
        "entry_id": entry_id,
        "payload": copy.deepcopy(payload),
    }


def _forget(target: str, server_name: str) -> None:
    _MANAGED.pop((target, server_name), None)


def _managed_state(record: dict[str, Any]) -> dict[str, Any]:
    state_key = tuple(record["state_key"])
    state = _STATES.get(state_key)
    if state is None:
        state = _new_state({
            "valid": True,
            "target": state_key[0] or None,
        })
        _STATES[state_key] = state
    return state


def _apply_remote(
    context: dict[str, Any],
    state: dict[str, Any],
    remote: list[dict[str, Any]],
    *,
    recover: bool,
    absent_overrides: dict[str, tuple[str, str | registry._RemoteFailure | None]] | None = None,
) -> None:
    payloads = _payloads(context["base"])
    projected, ignored = _remote_projection(remote)
    state["remote_items"] = projected
    state["ignored_count"] = ignored
    state["last_checked"] = _now()
    for entry_id, payload in payloads.items():
        if not context["base"]:
            _set_item(state, entry_id, "unknown", "nef_base_not_configured")
            continue
        exact, same_name = _matching(remote, payload)
        if exact:
            _set_item(state, entry_id, "registered")
            candidate = next(item for item in remote if item["serverName"] == payload["serverName"])
            differences = [
                field for field in ("description", "serverType", "serverStatus")
                if candidate.get(field) != payload[field]
            ]
            if differences:
                state["items"][entry_id]["metadata_differences"] = differences
            if recover and context["target"]:
                _remember(
                    context["key"],
                    context["target"],
                    context["token_env"],
                    entry_id,
                    payload,
                )
        elif same_name:
            _set_item(state, entry_id, "conflict", "trf_name_conflict")
        elif absent_overrides and entry_id in absent_overrides:
            status, error = absent_overrides[entry_id]
            _set_item(state, entry_id, status, error)
        else:
            _set_item(state, entry_id, "unregistered")
    if recover and context["target"]:
        for entry_id, payload in _legacy_payloads(context["base"]).items():
            exact, _same_name = _matching(remote, payload)
            if exact:
                _set_item(state, entry_id, "registered")
                _remember(context["key"], context["target"], context["token_env"], entry_id, payload)
            elif not any(item["serverName"] == payload["serverName"] for item in remote):
                state["items"].pop(entry_id, None)
                _forget(context["target"], payload["serverName"])


def _mark_read_failure(
    context: dict[str, Any],
    failure: registry._RemoteFailure,
    *,
    preserve_submissions: bool = False,
) -> None:
    with _STATE_LOCK:
        state = _state_for(context)
        state["status"] = "stale" if state["last_checked"] else "failed"
        for entry_id in _payloads(context["base"]):
            previous = state["items"].get(entry_id, {})
            if (
                preserve_submissions
                and previous.get("registration_status") in {"submitted", "failed"}
            ):
                if not previous.get("sync_error"):
                    _set_item(state, entry_id, previous["registration_status"], failure)
            else:
                _set_item(state, entry_id, "unknown", failure)


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    statuses = [item["registration_status"] for item in items]
    return {
        "registered": statuses.count("registered"),
        "unregistered": statuses.count("unregistered"),
        "unknown": sum(status in {"unknown", "submitted"} for status in statuses),
        "submitted": statuses.count("submitted"),
        "failed": sum(status in {"failed", "conflict"} for status in statuses),
        "total": len(statuses),
    }


def _response(
    context: dict[str, Any],
    *,
    state: dict[str, Any] | None = None,
    busy_override: bool | None = None,
) -> dict[str, Any]:
    with _STATE_LOCK:
        current = copy.deepcopy(state or _state_for(context))
        busy = _BUSY if busy_override is None else busy_override
        can_withdraw = bool(_MANAGED)
    payloads = _payloads(context["base"])
    groups: list[dict[str, Any]] = []
    members = _group_capabilities()
    for group_id, payload in payloads.items():
        stored = current["items"].get(
            group_id,
            {"registration_status": "unknown"},
        )
        item = {
            "group_id": group_id,
            "name": _GROUPS[group_id][1],
            "capability_ids": [cap.id for cap in members[group_id]],
            "serverName": payload["serverName"],
            "toolType": payload["toolType"],
            "registration_status": stored["registration_status"],
        }
        if stored.get("sync_error"):
            item["sync_error"] = stored["sync_error"]
        if stored.get("sync_diagnostic"):
            item["sync_diagnostic"] = stored["sync_diagnostic"]
        if stored.get("metadata_differences"):
            item["metadata_differences"] = stored["metadata_differences"]
        groups.append(item)
    items = [
        {**{key: value for key, value in group.items() if key not in {"name", "capability_ids"}},
         "capability_id": capability_id}
        for group in groups
        for capability_id in group["capability_ids"]
    ]
    legacy_items = [
        {"serverName": payload["serverName"], **current["items"][entry_id]}
        for entry_id, payload in _legacy_payloads(context["base"]).items()
        if entry_id in current["items"]
        and current["items"][entry_id]["registration_status"] != "unregistered"
    ]
    return {
        "configured": bool(context["valid"] and context["target"]),
        "base_configured": bool(context["valid"] and context["base"]),
        "busy": busy,
        "status": current["status"],
        "last_checked": current["last_checked"],
        "items": items,
        "groups": groups,
        "legacy_items": legacy_items,
        "remote_items": current["remote_items"],
        "ignored_count": current["ignored_count"],
        "can_withdraw": can_withdraw,
        "summary": _summary(groups),
        "capability_summary": _summary(items),
    }


def _begin_operation() -> None:
    global _BUSY
    with _STATE_LOCK:
        if _BUSY:
            registry._http_error(409, "busy", "TRF 目录正在执行另一项操作")
        _BUSY = True


def _end_operation() -> None:
    global _BUSY
    with _STATE_LOCK:
        _BUSY = False


async def _read_remote(
    target: str,
    token_env: str | None,
) -> list[dict[str, Any]]:
    return await registry._read_trf_servers(target, token_env=token_env)


def _finish_status(state: dict[str, Any], *, withdrawing: bool = False) -> None:
    statuses = [
        value.get("registration_status")
        for value in state["items"].values()
    ]
    desired = "unregistered" if withdrawing else "registered"
    if any(
        item.get("registration_status") == "unknown" and item.get("sync_error")
        for item in state["items"].values()
    ):
        state["status"] = "stale" if state["last_checked"] else "failed"
    elif statuses and all(status == desired for status in statuses):
        state["status"] = "synced"
    elif statuses and all(status in {"failed", "conflict"} for status in statuses):
        state["status"] = "failed"
    elif any(status in {"failed", "conflict", "submitted"} for status in statuses):
        state["status"] = "partial"
    else:
        state["status"] = "loaded"


def build_router(
    auth: Callable[[str | None, str | None], tuple[str, dict]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/v1/network/trf/catalog")
    async def get_catalog(response: Response):
        response.headers["Cache-Control"] = "no-store"
        context = _context()
        return _response(context)

    @router.post("/api/v1/network/trf/catalog/refresh")
    async def refresh_catalog(
        authorization: str | None = Header(default=None),
    ):
        auth(authorization, "af:register")
        _begin_operation()
        context = _context()
        try:
            with _STATE_LOCK:
                state = _state_for(context)
                if not context["valid"]:
                    state["status"] = "failed"
                    for entry_id in _payloads(None):
                        _set_item(state, entry_id, "unknown", "invalid_config")
                    return _response(context, state=state, busy_override=False)
                if not context["target"]:
                    state["status"] = "not_configured"
                    return _response(context, state=state, busy_override=False)
            try:
                remote = await _read_remote(
                    context["target"],
                    context["token_env"],
                )
            except registry._RemoteSchemaFailure as exc:
                _mark_read_failure(context, exc)
                return _response(context, busy_override=False)
            except registry._RemoteFailure as exc:
                _mark_read_failure(context, exc)
                return _response(context, busy_override=False)
            with _STATE_LOCK:
                state = _state_for(context)
                _apply_remote(context, state, remote, recover=True)
                state["status"] = "loaded"
                return _response(context, state=state, busy_override=False)
        finally:
            _end_operation()

    @router.post("/api/v1/network/trf/catalog/publish")
    async def publish_catalog(
        authorization: str | None = Header(default=None),
    ):
        auth(authorization, "af:register")
        _begin_operation()
        context = _context()
        try:
            with _STATE_LOCK:
                state = _state_for(context)
                payloads = _payloads(context["base"])
                if not context["valid"]:
                    state["status"] = "failed"
                    for entry_id in payloads:
                        _set_item(state, entry_id, "failed", "invalid_config")
                    return _response(context, state=state, busy_override=False)
                if not context["target"] or not context["base"]:
                    state["status"] = "not_configured"
                    error = (
                        "trf_not_configured"
                        if not context["target"]
                        else "nef_base_not_configured"
                    )
                    for entry_id in payloads:
                        _set_item(state, entry_id, "failed", error)
                    return _response(context, state=state, busy_override=False)

            try:
                initial = await _read_remote(
                    context["target"],
                    context["token_env"],
                )
            except registry._RemoteSchemaFailure as exc:
                _mark_read_failure(context, exc)
                return _response(context, busy_override=False)
            except registry._RemoteFailure as exc:
                _mark_read_failure(context, exc)
                return _response(context, busy_override=False)

            with _STATE_LOCK:
                state = _state_for(context)
                _apply_remote(context, state, initial, recover=True)
                state["status"] = "loaded"

            attempted: dict[str, tuple[str, str | registry._RemoteFailure | None]] = {}
            for entry_id, payload in payloads.items():
                with _STATE_LOCK:
                    current = _state_for(context)["items"][entry_id]
                    if current["registration_status"] in {"registered", "conflict"}:
                        continue
                    _remember(
                        context["key"],
                        context["target"],
                        context["token_env"],
                        entry_id,
                        payload,
                    )
                    _set_item(
                        _state_for(context),
                        entry_id,
                        "submitted",
                    )
                try:
                    await registry._remote_request(
                        "POST",
                        context["target"],
                        token_env=context["token_env"],
                        payload=payload,
                    )
                except registry._RemoteFailure as exc:
                    attempted[entry_id] = ("failed", exc)
                    with _STATE_LOCK:
                        _set_item(
                            _state_for(context),
                            entry_id,
                            "failed",
                            exc,
                        )
                else:
                    attempted[entry_id] = (
                        "submitted",
                        "trf_confirmation_unknown",
                    )

            try:
                confirmed = await _read_remote(
                    context["target"],
                    context["token_env"],
                )
            except registry._RemoteSchemaFailure as exc:
                _mark_read_failure(
                    context,
                    exc,
                    preserve_submissions=True,
                )
                return _response(context, busy_override=False)
            except registry._RemoteFailure as exc:
                _mark_read_failure(
                    context,
                    exc,
                    preserve_submissions=True,
                )
                return _response(context, busy_override=False)

            with _STATE_LOCK:
                state = _state_for(context)
                _apply_remote(
                    context,
                    state,
                    confirmed,
                    recover=True,
                    absent_overrides=attempted,
                )
                _finish_status(state)
                return _response(context, state=state, busy_override=False)
        finally:
            _end_operation()

    @router.post("/api/v1/network/trf/catalog/unpublish")
    async def unpublish_catalog(
        authorization: str | None = Header(default=None),
    ):
        auth(authorization, "af:register")
        _begin_operation()
        context = _context()
        try:
            with _STATE_LOCK:
                state = _state_for(context)
                if not context["valid"] and not _MANAGED:
                    state["status"] = "failed"
                    return _response(context, state=state, busy_override=False)

            current_remote: list[dict[str, Any]] | None = None
            if context["target"]:
                try:
                    current_remote = await _read_remote(
                        context["target"],
                        context["token_env"],
                    )
                except registry._RemoteSchemaFailure as exc:
                    _mark_read_failure(context, exc)
                except registry._RemoteFailure as exc:
                    _mark_read_failure(context, exc)
                else:
                    with _STATE_LOCK:
                        state = _state_for(context)
                        _apply_remote(
                            context,
                            state,
                            current_remote,
                            recover=True,
                        )
                        state["status"] = "loaded"

            with _STATE_LOCK:
                managed = copy.deepcopy(list(_MANAGED.values()))
            if not managed:
                with _STATE_LOCK:
                    state = _state_for(context)
                    if not context["target"]:
                        state["status"] = "not_configured"
                    else:
                        _finish_status(state, withdrawing=True)
                    return _response(
                        context,
                        state=state,
                        busy_override=False,
                    )

            groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
            for record in managed:
                groups.setdefault(
                    (record["target"], record["token_env"]),
                    [],
                ).append(record)

            for (target, token_env), records in groups.items():
                if target == context["target"] and current_remote is not None:
                    before = current_remote
                else:
                    try:
                        before = await _read_remote(target, token_env)
                    except (
                        registry._RemoteSchemaFailure,
                        registry._RemoteFailure,
                    ) as exc:
                        with _STATE_LOCK:
                            for record in records:
                                state = _managed_state(record)
                                _set_item(
                                    state,
                                    record["entry_id"],
                                    "unknown",
                                    exc,
                                )
                                state["status"] = (
                                    "stale"
                                    if state["last_checked"]
                                    else "failed"
                                )
                        continue

                deleted: list[dict[str, Any]] = []
                for record in records:
                    exact, same_name = _matching(before, record["payload"])
                    entry_id = record["entry_id"]
                    if not exact:
                        with _STATE_LOCK:
                            state = _managed_state(record)
                            if same_name:
                                _set_item(
                                    state,
                                    entry_id,
                                    "conflict",
                                    "trf_name_conflict",
                                )
                            else:
                                _set_item(state, entry_id, "unregistered")
                                _forget(
                                    record["target"],
                                    record["payload"]["serverName"],
                                )
                        continue
                    try:
                        await registry._delete_trf_server(
                            record["target"],
                            record["payload"]["serverName"],
                            token_env=record["token_env"],
                        )
                    except registry._RemoteFailure as exc:
                        with _STATE_LOCK:
                            state = _managed_state(record)
                            _set_item(
                                state,
                                entry_id,
                                "failed",
                                exc,
                            )
                            state["status"] = "failed"
                    else:
                        deleted.append(record)
                        with _STATE_LOCK:
                            _set_item(
                                _managed_state(record),
                                entry_id,
                                "submitted",
                                "trf_confirmation_unknown",
                            )

                if not deleted:
                    continue
                try:
                    after = await _read_remote(target, token_env)
                except (
                    registry._RemoteSchemaFailure,
                    registry._RemoteFailure,
                ) as exc:
                    with _STATE_LOCK:
                        for record in deleted:
                            state = _managed_state(record)
                            _set_item(
                                state,
                                record["entry_id"],
                                "submitted",
                                exc,
                            )
                            state["status"] = (
                                "stale"
                                if state["last_checked"]
                                else "failed"
                            )
                    continue

                if target == context["target"]:
                    current_remote = after
                    with _STATE_LOCK:
                        state = _state_for(context)
                        projected, ignored = _remote_projection(after)
                        state["remote_items"] = projected
                        state["ignored_count"] = ignored
                        state["last_checked"] = _now()
                for record in deleted:
                    exact, same_name = _matching(after, record["payload"])
                    with _STATE_LOCK:
                        state = _managed_state(record)
                        if exact:
                            _set_item(
                                state,
                                record["entry_id"],
                                "submitted",
                                "trf_confirmation_unknown",
                            )
                        elif same_name:
                            _set_item(
                                state,
                                record["entry_id"],
                                "conflict",
                                "trf_name_conflict",
                            )
                        else:
                            _set_item(
                                state,
                                record["entry_id"],
                                "unregistered",
                            )
                            _forget(
                                record["target"],
                                record["payload"]["serverName"],
                            )

            with _STATE_LOCK:
                state = _state_for(context)
                _finish_status(state, withdrawing=True)
                return _response(context, state=state, busy_override=False)
        finally:
            _end_operation()

    return router


__all__ = ["build_router", "reset_state_for_tests"]
