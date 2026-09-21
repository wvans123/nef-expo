# -*- coding: utf-8 -*-
"""Bounded, memory-only network registry routes for the NEF showcase.

The module deliberately keeps the boundary small: NEF records MCP servers and
network package declarations, while an operator-configured catalog and an
operator-configured TRF publisher remain outside NEF. Nothing here invents an
orchestration plan. Internal callers reach AF tools through a scoped NEF MCP gateway.
"""
from __future__ import annotations

import copy
import asyncio
import secrets
import time
import json
import os
import re
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from integration_config import section as integration_section
from composition import check_composition, recommend, load_llm_config
from catalog_publication import CatalogSelection, publication as catalog_publication
from jsonschema import Draft202012Validator, SchemaError
from fastapi import APIRouter, Body, Header, HTTPException, Request, Response

try:
    # The current project source of truth is skills.py/CAP_INDEX.
    from skills import CAP_INDEX as CAPABILITIES
except ImportError:  # pragma: no cover - only useful for isolated imports.
    CAPABILITIES = {}

MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_ACCEPT = "application/json, text/event-stream"
MAX_RESPONSE_BYTES = 1_048_576
MAX_CATALOG_ITEMS = 1_000
MAX_TOOLS = 1_000
MAX_SERVERS_PER_ACCOUNT = 64
MAX_PACKAGES_PER_ACCOUNT = 64
MAX_PACKAGE_STEPS = 12
MAX_NAME_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 2_000
MAX_URL_LENGTH = 2_048
MAX_ID_LENGTH = 256
MAX_TOOL_NAME_LENGTH = 256
MAX_CURSOR_LENGTH = 1_024
REQUEST_TIMEOUT_SECONDS = 10.0

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class _ConfigError(Exception):
    """Operator configuration is absent, malformed, or unsafe."""


class _RemoteFailure(Exception):
    """A bounded upstream request failed without retaining upstream content."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class _RemoteSchemaFailure(Exception):
    """A remote response was reachable but did not match its contract."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _RemoteResponse:
    status_code: int
    content_type: str
    body: bytes
    headers: dict[str, str]


_STATE_LOCK = threading.RLock()
# Catalog snapshots are account-scoped. The operator URL/config is shared, but
# fetched items and status belong to the authenticated account.
_CATALOGS: dict[str, dict[str, Any]] = {}
_ACCOUNTS: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}


def reset_state_for_tests() -> None:
    """Reset the in-memory projection; intended only for isolated tests."""
    with _STATE_LOCK:
        _CATALOGS.clear()
        _ACCOUNTS.clear()


def _http_error(status_code: int, code: str, message: str) -> None:
    # Only fixed, non-sensitive messages reach the caller. Do not include
    # URLs, response bodies, exception strings, or token values.
    raise HTTPException(status_code=status_code,
                        detail={"code": code, "message": message})


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(record)
    result.pop("gateway_busy", None)
    if result.get("source") == "AF":
        result["gateway_path"] = _gateway_path(result["id"])
        result["access_via"] = "NEF"
    return result


def _account_from_record(record: dict[str, Any]) -> str:
    account = record.get("account") if isinstance(record, dict) else None
    if not isinstance(account, str) or not account:
        _http_error(500, "invalid_auth_identity", "认证记录缺少账号")
    return account


def _require_text(value: Any, field: str, maximum: int, *, required: bool = True) -> str:
    if not isinstance(value, str):
        _http_error(422, "invalid_request", f"{field} 必须是字符串")
    value = value.strip()
    if required and not value:
        _http_error(422, "invalid_request", f"{field} 不能为空")
    if len(value) > maximum:
        _http_error(422, "invalid_request", f"{field} 超出长度限制")
    return value


def _checked_url(value: Any) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("url")
    if len(value) > MAX_URL_LENGTH or any(ord(ch) < 0x20 for ch in value):
        raise ValueError("url")
    if "#" in value:
        raise ValueError("url")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("url") from exc
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("url")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("url")
    parsed.port
    return value


def _require_url(value: Any, field: str = "url") -> str:
    try:
        return _checked_url(value)
    except ValueError:
        _http_error(422, "invalid_request", f"{field} 必须是无凭据的 http(s) URL")


def _valid_env_name(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _ENV_NAME.fullmatch(value):
        raise _ConfigError("invalid_config")
    return value


def _load_config() -> dict[str, Any]:
    raw = os.getenv("NEF_REGISTRY_CONFIG")
    try:
        source = (raw or "").strip()
        if not source:
            data = integration_section("registry")
        elif source.startswith("{"):
            data = json.loads(source)
        else:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
    except Exception as exc:
        # No path/content is returned to the caller.
        raise _ConfigError("invalid_config") from exc
    if not isinstance(data, dict):
        raise _ConfigError("invalid_config")

    normalized: dict[str, Any] = {"mcp_servers": {}}
    account = data.get("open_registration_account", "1")
    if not isinstance(account, str) or not 1 <= len(account) <= 128:
        raise _ConfigError("invalid_config")
    unlisted = data.get("allow_unlisted_mcp_servers", False)
    if type(unlisted) is not bool:
        raise _ConfigError("invalid_config")
    normalized.update(open_registration_account=account, allow_unlisted_mcp_servers=unlisted)
    for name in ("catalog_url", "publish_url", "withdraw_url", "nef_base_url"):
        value = data.get(name)
        if value in (None, ""):
            normalized[name] = None
            continue
        try:
            normalized[name] = _checked_url(value)
        except ValueError as exc:
            raise _ConfigError("invalid_config") from exc

    base = normalized.get("nef_base_url")
    if base and (urlsplit(base).query or urlsplit(base).fragment):
        raise _ConfigError("invalid_config")
    clients = data.get("network_clients", {})
    if not isinstance(clients, dict):
        raise _ConfigError("invalid_config")
    normalized["network_clients"] = {}
    for name, client in clients.items():
        if not isinstance(name, str) or not isinstance(client, dict):
            raise _ConfigError("invalid_config")
        accounts = client.get("af_accounts", [])
        if not isinstance(accounts, list) or not all(isinstance(a, str) and a for a in accounts):
            raise _ConfigError("invalid_config")
        token_env = _valid_env_name(client.get("token_env"))
        if not token_env:
            raise _ConfigError("invalid_config")
        normalized["network_clients"][name] = {"token_env": token_env, "af_accounts": accounts}
    normalized["token_env"] = _valid_env_name(data.get("token_env"))
    mcp_servers = data.get("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        raise _ConfigError("invalid_config")
    for server_url, server_config in mcp_servers.items():
        try:
            approved_url = _checked_url(server_url)
        except (TypeError, ValueError) as exc:
            raise _ConfigError("invalid_config") from exc
        if not isinstance(server_config, dict):
            raise _ConfigError("invalid_config")
        normalized["mcp_servers"][approved_url] = {
            "token_env": _valid_env_name(server_config.get("token_env")),
        }
    return normalized


def _token_header(token_env: str | None) -> dict[str, str]:
    if not token_env:
        return {}
    token = os.getenv(token_env)
    if not token:
        raise _RemoteFailure("missing_operator_token")
    return {"Authorization": f"Bearer {token}"}


async def _read_response_body(response: httpx.Response) -> bytes:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_RESPONSE_BYTES:
                raise _RemoteFailure("response_too_large")
        except ValueError:
            pass
    chunks: list[bytes] = []
    total = 0
    try:
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise _RemoteFailure("response_too_large")
            chunks.append(chunk)
    except _RemoteFailure:
        raise
    except Exception as exc:
        raise _RemoteFailure("upstream_read_failed") from exc
    return b"".join(chunks)


async def _remote_request(
    method: str,
    url: str,
    *,
    token_env: str | None = None,
    payload: Any = None,
    headers: dict[str, str] | None = None,
) -> _RemoteResponse:
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(_token_header(token_env))
    if headers:
        request_headers.update(headers)

    timeout = httpx.Timeout(
        connect=REQUEST_TIMEOUT_SECONDS,
        read=REQUEST_TIMEOUT_SECONDS,
        write=REQUEST_TIMEOUT_SECONDS,
        pool=REQUEST_TIMEOUT_SECONDS,
    )
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS), httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(
                method,
                url,
                json=payload,
                headers=request_headers,
            ) as response:
                body = await _read_response_body(response)
                content_type = response.headers.get("content-type", "")
                response_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                }
                if not 200 <= response.status_code < 300:
                    if 300 <= response.status_code < 400:
                        raise _RemoteFailure("redirect_not_allowed")
                    raise _RemoteFailure("upstream_http_error")
                return _RemoteResponse(
                    status_code=response.status_code,
                    content_type=content_type.split(";", 1)[0].strip().lower(),
                    body=body,
                    headers=response_headers,
                )
    except _RemoteFailure:
        raise
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise _RemoteFailure("upstream_timeout") from exc
    except (httpx.HTTPError, OSError) as exc:
        raise _RemoteFailure("upstream_request_failed") from exc
    except Exception as exc:
        # Keep transport failures honest without exposing exception text.
        raise _RemoteFailure("upstream_request_failed") from exc


def _sse_messages(body: bytes) -> list[dict[str, Any]]:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _RemoteFailure("invalid_sse") from exc

    events: list[str] = []
    data_lines: list[str] = []

    def flush() -> None:
        if data_lines:
            events.append("\n".join(data_lines))
            data_lines.clear()

    for line in text.splitlines():
        if not line:
            flush()
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            value = line[5:]
            data_lines.append(value[1:] if value.startswith(" ") else value)
    flush()
    if not events:
        raise _RemoteFailure("invalid_sse")

    messages: list[dict[str, Any]] = []
    for event in events:
        try:
            value = json.loads(event)
        except (TypeError, json.JSONDecodeError) as exc:
            raise _RemoteFailure("invalid_sse") from exc
        values = value if isinstance(value, list) else [value]
        if not all(isinstance(item, dict) for item in values):
            raise _RemoteFailure("invalid_sse")
        messages.extend(values)
    return messages


def _json_messages(response: _RemoteResponse, *, allow_sse: bool = True) -> list[dict[str, Any]]:
    if response.content_type == "text/event-stream":
        if not allow_sse:
            raise _RemoteFailure("unsupported_transport")
        return _sse_messages(response.body)
    if response.content_type and not (
        response.content_type == "application/json"
        or response.content_type.endswith("+json")
    ):
        raise _RemoteFailure("unsupported_transport")
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _RemoteFailure("invalid_json") from exc
    values = value if isinstance(value, list) else [value]
    if not values or not all(isinstance(item, dict) for item in values):
        raise _RemoteFailure("invalid_json")
    return values


def _same_jsonrpc_id(actual: Any, expected: Any) -> bool:
    return type(actual) is type(expected) and actual == expected


def _message_for_id(response: _RemoteResponse, expected_id: Any) -> dict[str, Any]:
    messages = _json_messages(response)
    for message in messages:
        if _same_jsonrpc_id(message.get("id"), expected_id):
            return message
    raise _RemoteSchemaFailure("jsonrpc_id_mismatch")


def _result_from_message(message: dict[str, Any]) -> dict[str, Any]:
    if message.get("jsonrpc") != "2.0":
        raise _RemoteSchemaFailure("invalid_jsonrpc")
    if "error" in message:
        raise _RemoteSchemaFailure("mcp_error")
    result = message.get("result")
    if not isinstance(result, dict):
        raise _RemoteSchemaFailure("invalid_result")
    return result


async def _mcp_request(
    url: str,
    token_env: str | None,
    message: dict[str, Any],
    *,
    expected_id: Any,
    session_id: str | None = None,
) -> tuple[dict[str, Any], _RemoteResponse]:
    headers = {
        "Accept": MCP_ACCEPT,
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    response = await _remote_request(
        "POST",
        url,
        token_env=token_env,
        payload=message,
        headers=headers,
    )
    return _message_for_id(response, expected_id), response


async def _mcp_notification(
    url: str,
    token_env: str | None,
    message: dict[str, Any],
    *,
    session_id: str | None = None,
) -> None:
    headers = {
        "Accept": MCP_ACCEPT,
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    await _remote_request(
        "POST",
        url,
        token_env=token_env,
        payload=message,
        headers=headers,
    )


def _validate_tool(tool: Any) -> dict[str, Any]:
    if not isinstance(tool, dict):
        raise _RemoteSchemaFailure("invalid_tool")
    name = tool.get("name")
    if not isinstance(name, str) or not name or len(name) > MAX_TOOL_NAME_LENGTH:
        raise _RemoteSchemaFailure("invalid_tool")
    description = tool.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_LENGTH:
        raise _RemoteSchemaFailure("invalid_tool")
    input_schema = tool.get("inputSchema")
    if not isinstance(input_schema, dict):
        raise _RemoteSchemaFailure("invalid_tool")
    if "type" in input_schema and not isinstance(input_schema["type"], str):
        raise _RemoteSchemaFailure("invalid_tool")
    if "properties" in input_schema and not isinstance(input_schema["properties"], dict):
        raise _RemoteSchemaFailure("invalid_tool")
    required = input_schema.get("required")
    if required is not None and (
        not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
    ):
        raise _RemoteSchemaFailure("invalid_tool")
    try:
        Draft202012Validator.check_schema(input_schema)
    except SchemaError as exc:
        raise _RemoteSchemaFailure("invalid_tool_schema") from exc
    return copy.deepcopy(tool)


async def _start_mcp(url: str, token_env: str | None, metadata: dict | None = None) -> str | None:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {
                "name": "nef-network-registry",
                "version": "1.0.0",
            },
        },
    }
    initialize_response, raw_response = await _mcp_request(
        url,
        token_env,
        initialize,
        expected_id=1,
    )
    init_result = _result_from_message(initialize_response)
    if init_result.get("protocolVersion") != MCP_PROTOCOL_VERSION:
        raise _RemoteSchemaFailure("protocol_version_mismatch")
    capabilities = init_result.get("capabilities")
    tools_capability = capabilities.get("tools") if isinstance(capabilities, dict) else None
    if not isinstance(tools_capability, dict):
        raise _RemoteSchemaFailure("tools_capability_missing")
    server_info = init_result.get("serverInfo")
    if not isinstance(server_info, dict):
        raise _RemoteSchemaFailure("server_info_missing")
    if not isinstance(server_info.get("name"), str) or not isinstance(server_info.get("version"), str):
        raise _RemoteSchemaFailure("server_info_invalid")

    if metadata is not None:
        metadata["origin_server_info"] = {"name": server_info["name"], "version": server_info["version"]}
    session_id = raw_response.headers.get("mcp-session-id")
    if session_id is not None:
        if not session_id or any(ord(ch) < 0x21 or ord(ch) > 0x7E for ch in session_id):
            raise _RemoteSchemaFailure("invalid_session_id")
        if len(session_id) > MAX_CURSOR_LENGTH:
            raise _RemoteSchemaFailure("invalid_session_id")

    await _mcp_notification(
        url,
        token_env,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        session_id=session_id,
    )

    return session_id


async def _discover_mcp(url: str, token_env: str | None, metadata: dict | None = None) -> list[dict[str, Any]]:
    session_id = await _start_mcp(url, token_env, metadata)
    tools: list[dict[str, Any]] = []
    names: set[str] = set()
    cursor: str | None = None
    seen_cursors: set[str] = set()
    request_id = 2
    page_count = 0
    while True:
        page_count += 1
        if page_count > 20:
            raise _RemoteSchemaFailure("too_many_pages")
        params: dict[str, Any] = {}
        if cursor is not None:
            params["cursor"] = cursor
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/list",
            "params": params,
        }
        response, _ = await _mcp_request(
            url,
            token_env,
            request,
            expected_id=request_id,
            session_id=session_id,
        )
        result = _result_from_message(response)
        page = result.get("tools")
        if not isinstance(page, list):
            raise _RemoteSchemaFailure("tools_list_invalid")
        for item in page:
            normalized = _validate_tool(item)
            name = normalized["name"]
            if name in names:
                raise _RemoteSchemaFailure("duplicate_tool")
            names.add(name)
            tools.append(normalized)
            if len(tools) > MAX_TOOLS:
                raise _RemoteSchemaFailure("too_many_tools")

        next_cursor = result.get("nextCursor")
        if next_cursor is None:
            break
        if (
            not isinstance(next_cursor, str)
            or not next_cursor
            or len(next_cursor) > MAX_CURSOR_LENGTH
            or next_cursor == cursor
            or next_cursor in seen_cursors
        ):
            raise _RemoteSchemaFailure("cursor_loop")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        request_id += 1
    return tools


def _catalog_state(account: str) -> dict[str, Any]:
    with _STATE_LOCK:
        return _CATALOGS.setdefault(
            account,
            {"items": [], "status": "not_configured", "error": None},
        )


def _set_catalog_failure(account: str, code: str) -> None:
    with _STATE_LOCK:
        state = _catalog_state(account)
        state["status"] = "failed"
        state["error"] = code


def _catalog_payload(account: str, *, status_override: str | None = None,
                     error_override: str | None = None) -> dict[str, Any]:
    with _STATE_LOCK:
        state = _catalog_state(account)
        result = {
            "items": copy.deepcopy(state["items"]),
            "status": state["status"],
        }
        error = state.get("error")
    if status_override is not None:
        result["status"] = status_override
    if error_override is not None:
        error = error_override
    if error:
        result["error"] = error
    return result


def _validate_catalog_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise _RemoteSchemaFailure("catalog_schema_invalid")
    items = value["items"]
    if len(items) > MAX_CATALOG_ITEMS:
        raise _RemoteSchemaFailure("catalog_too_large")
    result: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise _RemoteSchemaFailure("catalog_schema_invalid")
        try:
            item_id = _checked_catalog_id(item["id"])
            name = _checked_catalog_text(item["name"], MAX_NAME_LENGTH)
            description = _checked_catalog_text(item["description"], MAX_DESCRIPTION_LENGTH)
            kind = item["kind"]
        except (KeyError, ValueError, TypeError) as exc:
            raise _RemoteSchemaFailure("catalog_schema_invalid") from exc
        if kind not in {"tool", "package"}:
            raise _RemoteSchemaFailure("catalog_schema_invalid")
        if item_id in ids:
            raise _RemoteSchemaFailure("catalog_duplicate_id")
        ids.add(item_id)
        normalized = copy.deepcopy(item)
        normalized.update({
            "id": item_id,
            "name": name,
            "description": description,
            "kind": kind,
        })
        if "url" in normalized:
            try:
                normalized["url"] = _checked_url(normalized["url"])
            except (TypeError, ValueError) as exc:
                raise _RemoteSchemaFailure("catalog_schema_invalid") from exc
        result.append(normalized)
    return result


def _checked_catalog_id(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_ID_LENGTH:
        raise ValueError("id")
    return value.strip()


def _checked_catalog_text(value: Any, maximum: int) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError("text")
    return value.strip()


def _set_account_state(account: str) -> dict[str, dict[str, dict[str, Any]]]:
    return _ACCOUNTS.setdefault(account, {"servers": {}, "packages": {}})


def _get_owned_server(account: str, server_id: str) -> dict[str, Any]:
    with _STATE_LOCK:
        record = _ACCOUNTS.get(account, {}).get("servers", {}).get(server_id)
        if record is None:
            record = next((s for state in _ACCOUNTS.values() for s in state["servers"].values()
                           if s["id"] == server_id and s.get("registered_via") == "open"), None)
        if record is None:
            _http_error(404, "not_found", "网络服务器不存在")
        return record


def _approved_server(config, url):
    approved = config.get("mcp_servers", {}).get(url)
    if approved is None and config.get("allow_unlisted_mcp_servers"):
        return {}
    return approved


def _get_owned_package(account: str, package_id: str) -> dict[str, Any]:
    with _STATE_LOCK:
        record = _ACCOUNTS.get(account, {}).get("packages", {}).get(package_id)
        if record is None:
            _http_error(404, "not_found", "网络套餐不存在")
        return record


def _new_id(prefix: str, records: dict[str, Any]) -> str:
    for _ in range(8):
        value = f"{prefix}_{uuid.uuid4().hex[:12]}"
        if value not in records:
            return value
    raise RuntimeError("id allocation failed")


def _iter_capability_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        keys.update(str(key) for key in value.keys())
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            if isinstance(item, str):
                keys.add(item)
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                keys.add(item["id"])
            elif isinstance(getattr(item, "id", None), str):
                keys.add(item.id)
    return keys


def _existing_capability_keys() -> set[str]:
    # CAPABILITIES is deliberately skills.CAP_INDEX, as used by server.py.
    return _iter_capability_keys(CAPABILITIES)


def _synced_catalog_ids(account: str) -> set[str]:
    with _STATE_LOCK:
        state = _CATALOGS.get(account)
        if not state or state.get("status") != "synced":
            return set()
        return {item["id"] for item in state.get("items", [])}


def _owned_tool_refs(account: str) -> set[str]:
    refs: set[str] = set()
    with _STATE_LOCK:
        servers = {s["id"]: s for owner, state in _ACCOUNTS.items() for s in state["servers"].values()
                   if owner == account or s.get("registered_via") == "open"}
        for server_id, server in servers.items():
            if server.get("discovery_status") != "discovered":
                continue
            for tool in server.get("tools", []):
                name = tool.get("name") if isinstance(tool, dict) else None
                if isinstance(name, str):
                    refs.add(f"{server_id}:{name}")
    return refs


def _validate_package_steps(account: str, value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_PACKAGE_STEPS:
        _http_error(422, "invalid_request", "steps 数量必须在 1 到 12 之间")
    allowed = _existing_capability_keys() | _synced_catalog_ids(account) | _owned_tool_refs(account)
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for step in value:
        if not isinstance(step, dict) or set(step) - {"capability_id", "params"}:
            _http_error(422, "invalid_request", "每个 step 仅支持 capability_id 和 params")
        capability_id = _require_text(step.get("capability_id"), "capability_id", MAX_ID_LENGTH)
        if capability_id in seen:
            _http_error(422, "invalid_request", "steps 中 capability_id 不能重复")
        if capability_id not in allowed:
            _http_error(422, "invalid_request", "capability_id 不在当前能力注册表中")
        seen.add(capability_id)
        result.append({"capability_id": capability_id, **({"params": step["params"]} if "params" in step else {})})
    return result


def _upstream_failure_status(code: str) -> tuple[int, str]:
    if code == "upstream_timeout":
        return 504, "上游请求超时"
    if code == "unsupported_transport":
        return 502, "上游传输类型不受支持"
    if code == "redirect_not_allowed":
        return 502, "上游重定向被拒绝"
    if code in {"invalid_json", "invalid_sse", "response_too_large"}:
        return 502, "上游响应不符合受支持的 JSON 传输边界"
    if code in {
        "invalid_jsonrpc", "jsonrpc_id_mismatch", "mcp_error", "invalid_result",
        "protocol_version_mismatch", "tools_capability_missing", "server_info_missing",
        "server_info_invalid", "invalid_session_id", "invalid_tool", "tools_list_invalid",
        "duplicate_tool", "too_many_tools", "cursor_loop",
    }:
        return 502, "MCP 服务器响应未通过协议或工具校验"
    return 502, "上游请求失败"


def _mark_discovery_failure(account: str, server_id: str) -> None:
    with _STATE_LOCK:
        server = _ACCOUNTS.get(account, {}).get("servers", {}).get(server_id)
        if server is not None:
            server["tools"] = []
            server.pop("origin_server_info", None)
            server["discovery_status"] = "failed"
            server["sync_status"] = "pending"


def _mark_sync_status(account: str, collection: str, record_id: str, status: str) -> dict[str, Any]:
    with _STATE_LOCK:
        record = _ACCOUNTS.get(account, {}).get(collection, {}).get(record_id)
        if record is None:
            _http_error(404, "not_found", "网络注册对象不存在")
        record["sync_status"] = status
        return copy.deepcopy(record)


async def _publish(cfg: dict[str, Any], payload: dict[str, Any]) -> bool:
    publish_url = cfg.get("publish_url")
    if not publish_url:
        _http_error(503, "not_configured", "TRF 发布地址未配置")
    response = await _remote_request(
        "POST",
        publish_url,
        token_env=cfg.get("token_env"),
        payload=payload,
    )
    if not response.body:
        return False
    try:
        messages = _json_messages(response)
    except _RemoteFailure as exc:
        # A successful response without a parseable acknowledgement is still
        # only submitted; it cannot become synced on status code alone.
        if exc.code in {"unsupported_transport", "invalid_json", "invalid_sse"}:
            return False
        raise
    return len(messages) == 1 and messages[0].get("accepted") is True


def _gateway_path(server_id: str) -> str:
    return f"/api/v1/network/af-servers/{server_id}/mcp"


def _publication(config: dict, account: str, server: dict) -> dict:
    base = config.get("nef_base_url")
    if not base:
        _http_error(503, "gateway_not_configured", "请配置网络可访问的 NEF 入口 nef_base_url")
    endpoint = base.rstrip("/") + _gateway_path(server["id"])
    # AF URL and AF credential configuration stay inside NEF, never become a bypass route.
    descriptor = {k: copy.deepcopy(server[k]) for k in (
        "id", "name", "description", "tools", "discovery_status", "source", "source_account",
        "registration_status", "origin_server_info") if k in server}
    descriptor.update({"url": endpoint, "transport": "streamable-http", "access_via": "NEF",
                       "protocol_version": MCP_PROTOCOL_VERSION,
                       "authentication": "network-client-bearer",
                       "serverInfo": {"name": "nef-af-" + server["id"], "version": "1.0.0"}})
    return {"type": "mcp_server_registration", "registration_id": server["id"],
            "source": "AF", "source_account": account, "account": account, "server": descriptor}


def _network_access(config: dict, authorization: str | None, server_id: str) -> tuple[str, str, dict]:
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 512:
        _http_error(401, "network_unauthorized", "需要网络调用方凭证")
    token = authorization[7:]
    identity = None
    for name, client in config.get("network_clients", {}).items():
        secret = os.environ.get(client["token_env"], "")
        if secret and secrets.compare_digest(token.encode(), secret.encode()):
            identity = (name, client)
            break
    if identity is None:
        _http_error(401, "network_unauthorized", "无效的网络调用方凭证")
    name, client = identity
    with _STATE_LOCK:
        for account in client["af_accounts"]:
            server = _ACCOUNTS.get(account, {}).get("servers", {}).get(server_id)
            if server is not None:
                return name, account, copy.deepcopy(server)
    _http_error(404, "not_found", "未找到获准访问的 AF 服务")


def _local_schema_only(value: Any) -> bool:
    # Do not retrieve remote $ref URLs from AF-supplied schemas.
    if isinstance(value, dict):
        if any(k in value and (not isinstance(value[k], str) or not value[k].startswith("#"))
               for k in ("$ref", "$dynamicRef")):
            return False
        if "$id" in value:  # nested base URIs can turn fragment references into external references
            return False
        return all(_local_schema_only(v) for v in value.values())
    return not isinstance(value, list) or all(_local_schema_only(v) for v in value)


def build_router(auth: Callable[[str | None, str | None], tuple[str, dict]]) -> APIRouter:
    """Build the isolated router using the host application's auth function."""
    router = APIRouter()

    def selected_catalog(payload):
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "NEF_REGISTRY_CONFIG 无效")
        return config, catalog_publication(payload, config.get("nef_base_url"))

    @router.post("/api/v1/network/catalog/publication")
    async def preview_catalog(payload: CatalogSelection, authorization: str | None = Header(default=None)):
        auth(authorization, "af:register")
        _, publication = selected_catalog(payload)
        return publication

    @router.post("/api/v1/network/catalog/publish")
    async def publish_catalog(payload: CatalogSelection, authorization: str | None = Header(default=None)):
        auth(authorization, "af:register")
        config, publication = selected_catalog(payload)
        try:
            accepted = await _publish(config, publication)
        except _RemoteFailure as exc:
            status, message = _upstream_failure_status(exc.code)
            _http_error(status, exc.code, message)
        return {"catalog_id": publication["catalog_id"], "revision": publication["revision"],
                "item_count": len(publication["items"]), "accepted": accepted,
                "sync_status": "synced" if accepted else "submitted"}

    @router.get("/api/v1/network/catalog")
    async def get_network_catalog(authorization: str | None = Header(default=None)):
        _key, record = auth(authorization, None)
        account = _account_from_record(record)
        try:
            config = _load_config()
        except _ConfigError:
            _set_catalog_failure(account, "invalid_config")
            return _catalog_payload(account, status_override="failed", error_override="invalid_config")
        if not config.get("catalog_url"):
            with _STATE_LOCK:
                state = _catalog_state(account)
                state["status"] = "not_configured"
                state["error"] = None
            return _catalog_payload(account, status_override="not_configured")
        return _catalog_payload(account)

    @router.post("/api/v1/network/catalog/refresh")
    async def refresh_network_catalog(authorization: str | None = Header(default=None)):
        _key, record = auth(authorization, "af:register")
        account = _account_from_record(record)
        del _key
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "NEF_REGISTRY_CONFIG 无效")
        catalog_url = config.get("catalog_url")
        if not catalog_url:
            _http_error(503, "not_configured", "网络目录地址未配置")
        try:
            response = await _remote_request("GET", catalog_url,
                                             token_env=config.get("token_env"))
            items = _validate_catalog_items(json.loads(response.body.decode("utf-8")))
        except _RemoteSchemaFailure as exc:
            _set_catalog_failure(account, exc.code)
            _http_error(502, exc.code, "网络目录响应未通过 schema 校验")
        except _RemoteFailure as exc:
            _set_catalog_failure(account, exc.code)
            status, message = _upstream_failure_status(exc.code)
            _http_error(status, exc.code, message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            _set_catalog_failure(account, "catalog_schema_invalid")
            _http_error(502, "catalog_schema_invalid", "网络目录响应未通过 schema 校验")

        with _STATE_LOCK:
            state = _catalog_state(account)
            state["items"] = copy.deepcopy(items)
            state["status"] = "synced"
            state["error"] = None
        return _catalog_payload(account)

    @router.get("/api/v1/network/servers")
    async def list_network_servers(authorization: str | None = Header(default=None)):
        _key, record = auth(authorization, None)
        account = _account_from_record(record)
        with _STATE_LOCK:
            servers = [s for owner, state in _ACCOUNTS.items() for s in state["servers"].values()
                       if owner == account or s.get("registered_via") == "open"]
            return {"servers": [_public_record(item) for item in servers]}

    @router.get("/api/v1/network/market")
    async def published_market():
        # Customer-facing projection: no AF addresses, credentials, or account IDs.
        with _STATE_LOCK:
            items = []
            for state in _ACCOUNTS.values():
                for server in state["servers"].values():
                    if server.get("publication_status") != "published":
                        continue
                    for tool in server["tools"]:
                        items.append({
                            "id": server["id"] + ":" + tool["name"],
                            "name": tool["name"], "description": tool.get("description", ""),
                            "kind": "tool", "source": "AF", "provider": server["name"],
                            "server_id": server["id"], "inputSchema": copy.deepcopy(tool["inputSchema"]),
                        })
                for package in state["packages"].values():
                    if package.get("publication_status") == "published":
                        items.append({
                            "id": package["id"], "name": package["name"],
                            "description": package["description"], "kind": "package",
                            "source": "local", "steps": copy.deepcopy(package["steps"]),
                        })
            return {"items": items}

    @router.post("/api/v1/network/servers")
    async def register_network_server(
        payload: dict[str, Any] = Body(...),
        authorization: str | None = Header(default=None),
    ):
        _key, record = auth(authorization, "af:register")
        account = _account_from_record(record)
        return register_server(payload, account)

    def register_server(payload, account, opened=False):
        name = _require_text(payload.get("name"), "name", MAX_NAME_LENGTH)
        url = _require_url(payload.get("url"))
        description = _require_text(
            payload.get("description", ""),
            "description",
            MAX_DESCRIPTION_LENGTH,
            required=False,
        )
        with _STATE_LOCK:
            state = _set_account_state(account)
            existing = next((s for s in state["servers"].values()
                             if s["url"] == url and s.get("registered_via") == ("open" if opened else "account")), None)
            if existing:
                if existing.get("discovery_status") == "discovering" or existing.get("sync_status") == "syncing" or existing.get("gateway_busy"):
                    _http_error(409, "busy", "服务正在处理另一项操作")
                if existing.get("publication_status") == "published":
                    _http_error(409, "already_published", "请先取消发布，再更新服务")
                existing.update(name=name, description=description)
                return {**_public_record(existing), "created": False}
            if len(state["servers"]) >= MAX_SERVERS_PER_ACCOUNT:
                _http_error(409, "limit_exceeded", "每个账号最多注册 64 个网络服务器")
            server_id = _new_id("srv", state["servers"])
            server = {
                "id": server_id,
                "name": name,
                "url": url,
                "description": description,
                "tools": [],
                "source": "AF",
                "source_account": account,
                "registration_status": "registered",
                "discovery_status": "not_discovered",
                "sync_status": "pending",
                "publication_status": "draft",
                "trf_may_exist": False,
                "registered_via": "open" if opened else "account",
            }
            state["servers"][server_id] = server
            return {**_public_record(server), **({"created": True} if opened else {})}

    @router.post("/api/v1/af/mcp-servers")
    async def register_open_server(payload: dict[str, Any] = Body(...)):
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "网络登记配置无效")
        account = config["open_registration_account"]
        record = register_server(payload, account, opened=True)
        sid, created = record["id"], record["created"]
        try:
            record = await discover_server(sid, account)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": exc.detail}
            raise HTTPException(exc.status_code, {**detail, **_public_record(_get_owned_server(account, sid)),
                                                "created": created, "discovery_status": "failed"}) from exc
        record.update(created=created, discovery_status="ok")
        return {**record, "sync_status": "pending", "sync_note": "已发现工具，等待显式发布"}

    @router.post("/api/v1/network/servers/{server_id}/discover")
    async def discover_network_server(
        server_id: str,
        authorization: str | None = Header(default=None),
    ):
        _key, record = auth(authorization, "af:register")
        account = _account_from_record(record)
        return await discover_server(server_id, account)

    async def discover_server(server_id, account):
        server = _get_owned_server(account, server_id)
        account = server["source_account"]
        if server.get("publication_status") == "published":
            _http_error(409, "already_published", "请先取消发布，再重新发现工具")
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "NEF_REGISTRY_CONFIG 无效")
        approved = _approved_server(config, server["url"])
        if approved is None:
            if not config or not (
                config.get("catalog_url")
                or config.get("publish_url")
                or config.get("mcp_servers")
            ):
                _mark_discovery_failure(account, server_id)
                _http_error(503, "not_configured", "MCP 服务器 allowlist 未配置")
            _mark_discovery_failure(account, server_id)
            _http_error(403, "not_approved", "MCP 服务器 URL 未获运营方批准")

        with _STATE_LOCK:
            current = _ACCOUNTS[account]["servers"].get(server_id)
            if current is None:
                _http_error(404, "not_found", "网络服务器不存在")
            if current.get("discovery_status") == "discovering" or current.get("sync_status") == "syncing" or current.get("gateway_busy"):
                _http_error(409, "busy", "服务正在处理另一项操作")
            if current.get("publication_status") == "published":
                _http_error(409, "already_published", "请先取消发布，再重新发现工具")
            current["tools"] = []
            current["discovery_status"] = "discovering"
            current["sync_status"] = "pending"
        try:
            metadata = {}
            tools = await _discover_mcp(server["url"], approved.get("token_env"), metadata)
        except (_RemoteFailure, _RemoteSchemaFailure) as exc:
            _mark_discovery_failure(account, server_id)
            if isinstance(exc, _RemoteFailure):
                status, message = _upstream_failure_status(exc.code)
                _http_error(status, exc.code, message)
            _http_error(502, exc.code, "MCP 服务器响应未通过协议或工具校验")

        with _STATE_LOCK:
            current = _ACCOUNTS[account]["servers"].get(server_id)
            if current is None:
                _http_error(404, "not_found", "网络服务器不存在")
            current["tools"] = copy.deepcopy(tools)
            current.update(metadata)
            current["discovery_status"] = "discovered"
            current["sync_status"] = "pending"
            return _public_record(current)

    @router.get("/api/v1/network/servers/{server_id}/publication")
    async def preview_server_publication(server_id: str, authorization: str | None = Header(default=None)):
        _, record = auth(authorization, "af:register")
        account = _account_from_record(record)
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "网络发布配置无效")
        with _STATE_LOCK:
            server = copy.deepcopy(_get_owned_server(account, server_id))
        return _publication(config, server["source_account"], server)

    @router.post("/api/v1/network/servers/{server_id}/publish")
    @router.post("/api/v1/network/servers/{server_id}/sync")
    async def sync_network_server(
        server_id: str,
        authorization: str | None = Header(default=None),
    ):
        _key, record = auth(authorization, "af:register")
        account = _account_from_record(record)
        return await sync_server(server_id, account)

    async def sync_server(server_id, account):
        server = _get_owned_server(account, server_id)
        account = server["source_account"]
        with _STATE_LOCK:
            if server.get("sync_status") == "syncing" or server.get("discovery_status") == "discovering" or server.get("gateway_busy"):
                _http_error(409, "busy", "服务正在更新")
            if server.get("discovery_status") != "discovered" or not server.get("tools"):
                _http_error(409, "not_discovered", "请先连接并发现至少一个工具")
        return await change_publication(account, "servers", server_id, True)

    async def change_publication(account, collection, record_id, publish):
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "NEF_REGISTRY_CONFIG 无效")
        with _STATE_LOCK:
            record = _ACCOUNTS[account][collection][record_id]
            if record.get("sync_status") == "syncing" or record.get("discovery_status") == "discovering" or record.get("gateway_busy"):
                _http_error(409, "busy", "服务正在处理另一项操作")
            record["publication_status"] = "published" if publish else "unpublished"
            record["sync_status"] = "pending"
            record.pop("sync_error", None)
            record.pop("sync_note", None)
            if not publish and not record.get("trf_may_exist"):
                record.update(sync_status="not_required", sync_note="已从首页下架，未向 TRF 发布过")
                return _public_record(record)
            url = config.get("publish_url" if publish else "withdraw_url")
            if not url:
                record["sync_note"] = ("已在首页发布，TRF 发布地址待配置" if publish
                                       else "已从首页下架，TRF 撤回地址待配置")
                return _public_record(record)
            if publish:
                try:
                    payload = (_publication(config, account, record) if collection == "servers" else
                               {"type": "network_package_declaration", "account": account,
                                "package": _public_record(record)})
                except HTTPException as exc:
                    record.update(sync_status="failed", sync_error=exc.detail,
                                  sync_note="已在首页发布，TRF 同步配置不完整")
                    return _public_record(record)
                # Even a timeout may have reached TRF. Preserve this until withdrawal is acknowledged.
                record["trf_may_exist"] = True
            else:
                payload = {"type": "mcp_server_withdrawal" if collection == "servers" else "network_package_withdrawal",
                           "registration_id": record_id, "account": account}
            record["sync_status"] = "syncing"
        try:
            accepted = await _publish({**config, "publish_url": url}, payload)
        except _RemoteFailure as exc:
            with _STATE_LOCK:
                record.update(sync_status="failed", sync_error=exc.code,
                              sync_note="首页状态已更新，TRF 请求失败，可重试")
                return _public_record(record)
        with _STATE_LOCK:
            record["sync_status"] = "synced" if accepted else "submitted"
            record["sync_note"] = "TRF 已确认" if accepted else "已提交 TRF，等待确认"
            if not publish and accepted:
                record["trf_may_exist"] = False
            return {**_public_record(record), "accepted": accepted}

    @router.post("/api/v1/network/servers/{server_id}/unpublish")
    async def unpublish_server(server_id: str, authorization: str | None = Header(default=None)):
        _, identity = auth(authorization, "af:register")
        record = _get_owned_server(_account_from_record(identity), server_id)
        return await change_publication(record["source_account"], "servers", server_id, False)

    @router.post("/api/v1/network/af-servers/{server_id}/mcp")
    async def af_tool_gateway(server_id: str, request: Request,
                              authorization: str | None = Header(default=None)):
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "网络调用配置无效")
        caller, account, server = _network_access(config, authorization, server_id)
        if server.get("publication_status") != "published":
            _http_error(409, "not_published", "服务尚未发布或已取消发布")
        approved = _approved_server(config, server["url"])
        if approved is None:
            _http_error(403, "not_approved", "AF 服务未获连接许可")
        if server.get("discovery_status") != "discovered":
            _http_error(409, "not_discovered", "请先在 NEF 完成工具发现")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_RESPONSE_BYTES:
                _http_error(413, "request_too_large", "调用请求过大")
        try:
            message = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
                or not isinstance(message.get("method"), str)
                or ("id" in message and (isinstance(message["id"], bool) or not isinstance(message["id"], (str, int))))):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        method, rid = message["method"], message.get("id")
        def error(code, text):
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": text}}
        if "id" not in message:
            # Notifications never execute tools.
            return Response(status_code=202)
        params = message.get("params", {})
        if not isinstance(params, dict):
            return error(-32602, "Invalid params")
        if method == "initialize":
            result = {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {"tools": {}},
                      "serverInfo": {"name": "nef-af-" + server_id, "version": "1.0.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": server["tools"]}
        elif method == "tools/call":
            tool = next((t for t in server["tools"] if t["name"] == params.get("name")), None)
            arguments = params.get("arguments", {})
            if tool is None or not isinstance(arguments, dict):
                return error(-32602, "Unknown tool or invalid arguments")
            if not _local_schema_only(tool["inputSchema"]):
                return error(-32602, "Schema requires unsupported external references")
            try:
                Draft202012Validator(tool["inputSchema"]).validate(arguments)
            except Exception:
                # No user arguments/schema internals in the error or the audit record.
                return error(-32602, "Arguments do not match the discovered inputSchema")
            with _STATE_LOCK:
                current = _ACCOUNTS[account]["servers"][server_id]
                if current.get("gateway_busy") or current.get("discovery_status") != "discovered" or current.get("publication_status") != "published":
                    return error(-32001, "AF service is busy")
                current["gateway_busy"] = True
                current["last_call"] = {"caller": caller, "tool": tool["name"], "status": "calling", "via": "NEF"}
            started = time.monotonic()
            outcome = "failed"
            try:
                async with asyncio.timeout(30):
                    session = await _start_mcp(server["url"], approved.get("token_env"))
                    response, _ = await _mcp_request(server["url"], approved.get("token_env"),
                        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool["name"], "arguments": arguments}},
                        expected_id=2, session_id=session)
                    result = _result_from_message(response)
                    if not isinstance(result.get("content"), list) or ("isError" in result and not isinstance(result["isError"], bool)):
                        raise _RemoteSchemaFailure("invalid_call_result")
                    outcome = "tool_error" if result.get("isError") else "returned"
            except (_RemoteFailure, _RemoteSchemaFailure, TimeoutError):
                return error(-32002, "AF response unavailable; execution outcome may be unknown. Do not retry blindly.")
            finally:
                with _STATE_LOCK:
                    current["gateway_busy"] = False
                    current["last_call"].update(status=outcome, elapsed_ms=round((time.monotonic()-started)*1000))
            # Preserve the actual AF CallToolResult including isError; do not invent business completion.
        else:
            return error(-32601, "Method not found")
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    @router.get("/api/v1/network/packages")
    async def list_network_packages(authorization: str | None = Header(default=None)):
        _key, record = auth(authorization, None)
        account = _account_from_record(record)
        with _STATE_LOCK:
            packages = list(_ACCOUNTS.get(account, {}).get("packages", {}).values())
            return {"packages": [_public_record(item) for item in packages]}

    composer_busy: set[str] = set()

    @router.get("/api/v1/composer/status")
    async def composer_status(authorization: str | None = Header(default=None)):
        auth(authorization, "pipeline:manage")
        try:
            load_llm_config()
            return {"configured": True, "code": "configured", "message": "模型已配置",
                    "connectivity": "not_checked"}
        except HTTPException as exc:
            return {"configured": False, **exc.detail, "connectivity": "not_checked"}

    @router.post("/api/v1/composer/validate")
    async def validate_composer(payload: dict = Body(...), authorization: str | None = Header(default=None)):
        _, record = auth(authorization, "pipeline:manage")
        steps = _validate_package_steps(_account_from_record(record), payload.get("steps"))
        return check_composition(steps, payload.get("context", {}))

    @router.post("/api/v1/composer/recommend")
    async def recommend_composer(payload: dict = Body(...), authorization: str | None = Header(default=None)):
        _, record = auth(authorization, "pipeline:manage")
        account = _account_from_record(record)
        # One request per account, bounded globally; no key, prompt or response retained.
        if account in composer_busy or len(composer_busy) >= 4:
            _http_error(429, "busy", "智能推荐繁忙，请稍后重试")
        composer_busy.add(account)
        try:
            return await recommend(payload.get("text"), payload.get("context", {}))
        finally:
            composer_busy.discard(account)

    @router.post("/api/v1/network/packages")
    async def register_network_package(
        payload: dict[str, Any] = Body(...),
        authorization: str | None = Header(default=None),
    ):
        _key, record = auth(authorization, "pipeline:manage")
        account = _account_from_record(record)
        name = _require_text(payload.get("name"), "name", MAX_NAME_LENGTH)
        description = _require_text(
            payload.get("description", ""),
            "description",
            MAX_DESCRIPTION_LENGTH,
            required=False,
        )
        if payload.get("execution_target") != "network":
            _http_error(422, "invalid_request", "execution_target 必须是 network")
        steps = _validate_package_steps(account, payload.get("steps"))
        validation = check_composition(steps, payload.get("context", {}))
        if not validation["valid"]:
            raise HTTPException(422, {"message": "套餐存在冲突", "validation": validation})
        with _STATE_LOCK:
            state = _set_account_state(account)
            if len(state["packages"]) >= MAX_PACKAGES_PER_ACCOUNT:
                _http_error(409, "limit_exceeded", "每个账号最多注册 64 个网络套餐")
            package_id = _new_id("pkg", state["packages"])
            package = {
                "id": package_id,
                "name": name,
                "description": description,
                "steps": steps,
                "context": validation["context"],
                "execution_target": "network",
                "sync_status": "pending",
                "publication_status": "draft",
                "trf_may_exist": False,
            }
            state["packages"][package_id] = package
            return _public_record(package)

    @router.post("/api/v1/network/packages/{package_id}/publish")
    @router.post("/api/v1/network/packages/{package_id}/sync")
    async def sync_network_package(
        package_id: str,
        authorization: str | None = Header(default=None),
    ):
        _key, record = auth(authorization, "pipeline:manage")
        account = _account_from_record(record)
        _get_owned_package(account, package_id)
        return await change_publication(account, "packages", package_id, True)

    @router.post("/api/v1/network/packages/{package_id}/unpublish")
    async def unpublish_package(package_id: str, authorization: str | None = Header(default=None)):
        _, identity = auth(authorization, "pipeline:manage")
        account = _account_from_record(identity)
        _get_owned_package(account, package_id)
        return await change_publication(account, "packages", package_id, False)

    return router


__all__ = [
    "CAPABILITIES",
    "MCP_PROTOCOL_VERSION",
    "build_router",
    "reset_state_for_tests",
]
