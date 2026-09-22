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
import hashlib
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
from urllib.parse import quote, urlsplit

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
_TRF_SERVER_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TRF_FIELDS = (
    "serverName",
    "serverType",
    "toolType",
    "description",
    "url",
    "serverStatus",
)
_TRF_OPTIONAL_FIELDS = ("isThirdParty",)
_TRF_RESERVED_SERVER_PREFIX = "nef-cap-"


class _ConfigError(Exception):
    """Operator configuration is absent, malformed, or unsafe."""


class _RemoteFailure(Exception):
    """A bounded upstream request failed without retaining upstream content."""

    def __init__(self, code: str, *, method: str | None = None, http_status: int | None = None):
        super().__init__(code)
        self.code = code
        self.method = method
        self.http_status = http_status


class _RemoteSchemaFailure(_RemoteFailure):
    """A remote response was reachable but did not match its contract."""


def _trf_error_detail(exc: _RemoteFailure) -> dict[str, Any]:
    detail: dict[str, Any] = {"code": exc.code}
    if exc.method:
        detail["method"] = exc.method
    if exc.http_status is not None:
        detail["http_status"] = exc.http_status
    return detail


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
_MARKET_SUBSCRIPTIONS: dict[str, dict[str, dict[str, Any]]] = {}


def reset_state_for_tests() -> None:
    """Reset the in-memory projection; intended only for isolated tests."""
    with _STATE_LOCK:
        _CATALOGS.clear()
        _ACCOUNTS.clear()
        _MARKET_SUBSCRIPTIONS.clear()


def _http_error(status_code: int, code: str, message: str) -> None:
    # Only fixed, non-sensitive messages reach the caller. Do not include
    # URLs, response bodies, exception strings, or token values.
    raise HTTPException(status_code=status_code,
                        detail={"code": code, "message": message})


def _public_record(record: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(record)
    result.pop("gateway_busy", None)
    result.pop("_server_name_explicit", None)
    result.pop("_trf_target_url", None)
    result.pop("_trf_target_name", None)
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
    for name in (
        "catalog_url",
        "publish_url",
        "withdraw_url",
        "trf_mcp_servers_url",
        "nef_base_url",
    ):
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
    trf_collection = normalized.get("trf_mcp_servers_url")
    if trf_collection and (
        urlsplit(trf_collection).query or urlsplit(trf_collection).fragment
    ):
        raise _ConfigError("invalid_config")
    if trf_collection:
        normalized["trf_mcp_servers_url"] = trf_collection.rstrip("/")
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
            request_args: dict[str, Any] = {"headers": request_headers}
            if payload is not None:
                request_args["json"] = payload
            async with client.stream(method, url, **request_args) as response:
                body = await _read_response_body(response)
                content_type = response.headers.get("content-type", "")
                response_headers = {
                    str(key).lower(): str(value)
                    for key, value in response.headers.items()
                }
                if not 200 <= response.status_code < 300:
                    if 300 <= response.status_code < 400:
                        raise _RemoteFailure("redirect_not_allowed", http_status=response.status_code)
                    raise _RemoteFailure("upstream_http_error", http_status=response.status_code)
                return _RemoteResponse(
                    status_code=response.status_code,
                    content_type=content_type.split(";", 1)[0].strip().lower(),
                    body=body,
                    headers=response_headers,
                )
    except _RemoteFailure as exc:
        exc.method = method
        raise
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise _RemoteFailure("upstream_timeout", method=method) from exc
    except (httpx.HTTPError, OSError) as exc:
        raise _RemoteFailure("upstream_request_failed", method=method) from exc
    except Exception as exc:
        # Keep transport failures honest without exposing exception text.
        raise _RemoteFailure("upstream_request_failed", method=method) from exc


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


def _require_trf_server_name(value: Any, field: str = "serverName") -> str:
    name = _require_text(value, field, MAX_NAME_LENGTH)
    if not _TRF_SERVER_NAME.fullmatch(name):
        _http_error(
            422,
            "invalid_request",
            f"{field} 必须匹配 [a-zA-Z0-9][a-zA-Z0-9._-]{{0,127}}",
        )
    return name


def _trf_publication(server: dict[str, Any]) -> dict[str, Any]:
    server_name = server.get("serverName", server.get("name"))
    if not isinstance(server_name, str) or not _TRF_SERVER_NAME.fullmatch(server_name):
        _http_error(
            422,
            "invalid_server_name",
            "serverName 必须匹配 [a-zA-Z0-9][a-zA-Z0-9._-]{0,127}",
        )
    return {
        "serverName": server_name,
        "serverType": "Streamable HTTP",
        "toolType": "third-party tool",
        "description": server.get("description", ""),
        "url": server["url"],
        "serverStatus": "active",
        "isThirdParty": True,
    }


def _decode_json_value(response: _RemoteResponse) -> Any:
    if response.content_type and not (
        response.content_type == "application/json"
        or response.content_type.endswith("+json")
    ):
        raise _RemoteFailure("unsupported_transport")
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _RemoteFailure("invalid_json") from exc


def _validate_trf_servers(value: Any) -> list[dict[str, Any]]:
    envelopes: list[dict[str, Any]] = []
    # Only unwrap known collection shapes; never interpret an error as an empty list.
    for _ in range(2):
        if not isinstance(value, dict):
            break
        envelopes.append(value)
        if value.get("success") is False or value.get("error"):
            raise _RemoteSchemaFailure("trf_response_rejected")
        if value.get("code") not in (None, 0, "0", 200, "200"):
            raise _RemoteSchemaFailure("trf_response_rejected")
        keys = [key for key in ("data", "items", "servers", "records") if key in value]
        if len(keys) != 1:
            raise _RemoteSchemaFailure("trf_schema_invalid")
        value = value[keys[0]]
    if isinstance(value, list):
        items = value
    else:
        raise _RemoteSchemaFailure("trf_schema_invalid")
    for envelope in envelopes:
        if any(envelope.get(key) for key in ("nextCursor", "next_cursor", "next", "hasMore", "has_more", "pagination")):
            raise _RemoteSchemaFailure("trf_incomplete_list")
        for key in ("total", "totalCount", "totalElements"):
            if key in envelope:
                total = envelope[key]
                if type(total) is not int or total != len(items):
                    raise _RemoteSchemaFailure("trf_incomplete_list")
        for key in ("totalPages", "pages"):
            if key in envelope and (type(envelope[key]) is not int or envelope[key] > 1):
                raise _RemoteSchemaFailure("trf_incomplete_list")
    if len(items) > MAX_CATALOG_ITEMS:
        raise _RemoteSchemaFailure("trf_too_many_servers")
    result: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or any(field not in item for field in _TRF_FIELDS)
        ):
            raise _RemoteSchemaFailure("trf_schema_invalid")
        try:
            server_name = item["serverName"]
            if not isinstance(server_name, str) or not _TRF_SERVER_NAME.fullmatch(server_name):
                raise ValueError("serverName")
            server_type = _checked_catalog_text(item["serverType"], MAX_NAME_LENGTH)
            tool_type = _checked_catalog_text(item["toolType"], MAX_NAME_LENGTH)
            description = _checked_catalog_text(item["description"], MAX_DESCRIPTION_LENGTH)
            url = _checked_url(item["url"])
            server_status = _checked_catalog_text(item["serverStatus"], MAX_NAME_LENGTH)
            if not server_type or not tool_type or not server_status:
                raise ValueError("empty")
            is_third_party = item.get("isThirdParty")
            if "isThirdParty" in item and type(is_third_party) is not bool:
                raise ValueError("isThirdParty")
            if server_name in names:
                raise ValueError("duplicate serverName")
        except (KeyError, TypeError, ValueError) as exc:
            raise _RemoteSchemaFailure("trf_schema_invalid") from exc
        names.add(server_name)
        # The known categories are nf/computing/sensing/third-party tool.
        # Bounded unknown values are preserved rather than misclassified.
        parsed = {
            "serverName": server_name,
            "serverType": server_type,
            "toolType": tool_type,
            "description": description,
            "url": url,
            "serverStatus": server_status,
        }
        if "isThirdParty" in item:
            parsed["isThirdParty"] = is_third_party
        result.append(parsed)
    return result


async def _read_trf_servers(
    collection_url: str,
    *,
    token_env: str | None,
) -> list[dict[str, Any]]:
    response = None
    try:
        response = await _remote_request("GET", collection_url, token_env=token_env)
        return _validate_trf_servers(_decode_json_value(response))
    except _RemoteFailure as exc:
        exc.method = "GET"
        if response is not None:
            exc.http_status = response.status_code
        raise


def _same_trf_server(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not all(left.get(field) == right.get(field) for field in _TRF_FIELDS):
        return False
    if "isThirdParty" in left:
        return left["isThirdParty"] == right.get("isThirdParty", False)
    return True


def _trf_delete_url(collection_url: str, server_name: str) -> str:
    return collection_url.rstrip("/") + "/" + quote(server_name, safe="")


async def _delete_trf_server(
    collection_url: str,
    server_name: str,
    *,
    token_env: str | None,
) -> int:
    url = _trf_delete_url(collection_url, server_name)
    request_headers = {"Accept": "application/json", **_token_header(token_env)}
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
            async with client.stream("DELETE", url, headers=request_headers) as response:
                await _read_response_body(response)
                if 200 <= response.status_code < 300 or response.status_code == 404:
                    return response.status_code
                if 300 <= response.status_code < 400:
                    raise _RemoteFailure("redirect_not_allowed", http_status=response.status_code)
                raise _RemoteFailure("upstream_http_error", http_status=response.status_code)
    except _RemoteFailure as exc:
        exc.method = "DELETE"
        raise
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise _RemoteFailure("upstream_timeout", method="DELETE") from exc
    except (httpx.HTTPError, OSError) as exc:
        raise _RemoteFailure("upstream_request_failed", method="DELETE") from exc
    except Exception as exc:
        raise _RemoteFailure("upstream_request_failed", method="DELETE") from exc


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
    allowed = (
        _existing_capability_keys()
        | _synced_catalog_ids(account)
        | _owned_tool_refs(account)
        | _subscribed_external_tool_refs(account)
    )
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


def _uses_trf_server_contract(config: dict, server: dict) -> bool:
    return bool(
        config.get("trf_mcp_servers_url")
        or server.get("_trf_target_url")
        or (
            server.get("_server_name_explicit")
            and not config.get("publish_url")
        )
    )


def _publication(config: dict, account: str, server: dict) -> dict:
    if _uses_trf_server_contract(config, server):
        return _trf_publication(server)
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


def _external_tool_ref(server_id: str, tool_name: str) -> str:
    return f"{server_id}:{tool_name}"


def _external_mcp_name(server_id: str, tool_name: str) -> str:
    digest = hashlib.sha256(tool_name.encode("utf-8")).hexdigest()[:10]
    return f"external_{server_id}_{digest}"


def _find_server_locked(server_id: str) -> dict[str, Any] | None:
    for state in _ACCOUNTS.values():
        server = state["servers"].get(server_id)
        if server is not None:
            return server
    return None


def _find_tool_locked(
    server_id: str,
    tool_name: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    server = _find_server_locked(server_id)
    if server is None:
        return None
    tool = next(
        (
            item
            for item in server.get("tools", [])
            if isinstance(item, dict) and item.get("name") == tool_name
        ),
        None,
    )
    if tool is None:
        return None
    return server, tool


def _market_tool_snapshot(
    server: dict[str, Any],
    tool: dict[str, Any],
    *,
    available: bool,
) -> dict[str, Any]:
    tool_id = _external_tool_ref(server["id"], tool["name"])
    return {
        "id": tool_id,
        "server_id": server["id"],
        "serverName": server.get("serverName", server["name"]),
        "name": tool["name"],
        "description": tool.get("description", ""),
        "inputSchema": copy.deepcopy(tool["inputSchema"]),
        "mcp_name": _external_mcp_name(server["id"], tool["name"]),
        "toolType": "third-party tool",
        "price": 0,
        "billing": "demo_free",
        "available": bool(available),
    }


def _market_trf_registration_status(server: dict[str, Any]) -> str:
    """Project only the new TRF collection state; legacy publishing stays unknown."""
    if not server.get("_trf_target_url"):
        return (
            "unregistered"
            if server.get("publication_status") != "published"
            else "unknown"
        )
    if not server.get("trf_may_exist"):
        return "unregistered"
    sync_status = server.get("sync_status")
    if sync_status == "synced":
        return "registered"
    if sync_status in {"syncing", "submitted"}:
        return "submitted"
    if sync_status == "failed":
        return "failed"
    return "unknown"


def _all_market_tools_locked(*, published_only: bool) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for state in _ACCOUNTS.values():
        for server in state["servers"].values():
            if published_only and server.get("publication_status") != "published":
                continue
            for tool in server.get("tools", []):
                if isinstance(tool, dict) and isinstance(tool.get("name"), str):
                    items.append(
                        _market_tool_snapshot(
                            server,
                            tool,
                            available=server.get("publication_status") == "published",
                        )
                    )
    return items


def market_tools() -> list[dict[str, Any]]:
    """Return the secret-free projection of all published external tools."""
    with _STATE_LOCK:
        return copy.deepcopy(_all_market_tools_locked(published_only=True))


def market_tool_by_mcp_name(mcp_name: str) -> dict[str, Any] | None:
    with _STATE_LOCK:
        item = next(
            (
                candidate
                for candidate in _all_market_tools_locked(published_only=False)
                if candidate["mcp_name"] == mcp_name
            ),
            None,
        )
        return copy.deepcopy(item) if item is not None else None


def _subscription_snapshot_locked(
    account: str,
    tool_id: str,
) -> dict[str, Any] | None:
    stored = _MARKET_SUBSCRIPTIONS.get(account, {}).get(tool_id)
    if stored is None:
        return None
    try:
        server_id, tool_name = tool_id.split(":", 1)
    except ValueError:
        result = copy.deepcopy(stored)
        result["available"] = False
        return result
    found = _find_tool_locked(server_id, tool_name)
    if found is None:
        result = copy.deepcopy(stored)
        result["available"] = False
        return result
    server, tool = found
    return _market_tool_snapshot(
        server,
        tool,
        available=server.get("publication_status") == "published",
    )


def market_subscriptions(account: str) -> list[dict[str, Any]]:
    with _STATE_LOCK:
        return [
            snapshot
            for tool_id in sorted(_MARKET_SUBSCRIPTIONS.get(account, {}))
            if (snapshot := _subscription_snapshot_locked(account, tool_id)) is not None
        ]


def market_subscription(account: str, tool_id: str) -> dict[str, Any] | None:
    with _STATE_LOCK:
        return _subscription_snapshot_locked(account, tool_id)


def subscribe_market_tool(account: str, tool_id: str) -> dict[str, Any]:
    with _STATE_LOCK:
        try:
            server_id, tool_name = tool_id.split(":", 1)
        except ValueError:
            _http_error(422, "invalid_tool_id", "tool_id 必须是 server_id:toolName")
        found = _find_tool_locked(server_id, tool_name)
        if found is None:
            _http_error(404, "tool_not_found", "外部工具不存在")
        server, tool = found
        if server.get("publication_status") != "published":
            _http_error(409, "tool_unavailable", "外部工具当前未发布")
        record = _market_tool_snapshot(server, tool, available=True)
        _MARKET_SUBSCRIPTIONS.setdefault(account, {})[tool_id] = record
        return copy.deepcopy(record)


def unsubscribe_market_tool(account: str, tool_id: str) -> None:
    with _STATE_LOCK:
        _MARKET_SUBSCRIPTIONS.get(account, {}).pop(tool_id, None)


def _subscribed_external_tool_refs(account: str) -> set[str]:
    with _STATE_LOCK:
        return {
            tool_id
            for tool_id in _MARKET_SUBSCRIPTIONS.get(account, {})
            if (
                (snapshot := _subscription_snapshot_locked(account, tool_id))
                is not None
                and snapshot.get("available") is True
            )
        }


def _remove_market_subscriptions_for_server_locked(server_id: str) -> None:
    prefix = f"{server_id}:"
    for subscriptions in _MARKET_SUBSCRIPTIONS.values():
        for tool_id in list(subscriptions):
            if tool_id.startswith(prefix):
                subscriptions.pop(tool_id, None)


async def call_external_tool(
    account: str,
    mcp_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    with _STATE_LOCK:
        tool_item = next(
            (
                item
                for item in _all_market_tools_locked(published_only=False)
                if item["mcp_name"] == mcp_name
            ),
            None,
        )
        if tool_item is None:
            _http_error(404, "tool_not_found", "外部工具不存在")
        subscription = _subscription_snapshot_locked(account, tool_item["id"])
        if subscription is None:
            _http_error(403, "subscription_required", "请先订阅该外部工具")
        if not subscription.get("available"):
            _http_error(409, "tool_unavailable", "外部工具当前未发布")
        server_id, tool_name = tool_item["id"].split(":", 1)
        found = _find_tool_locked(server_id, tool_name)
        if found is None:
            _http_error(404, "tool_not_found", "外部工具不存在")
        server, tool = found
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "网络调用配置无效")
        approved = _approved_server(config, server["url"])
        if approved is None:
            _http_error(
                403,
                "not_approved",
                "外部 MCP 服务器不在 registry.mcp_servers allowlist 中",
            )
        if not _local_schema_only(tool["inputSchema"]):
            _http_error(422, "unsupported_schema", "外部工具 schema 含不支持的外部引用")
        try:
            Draft202012Validator(tool["inputSchema"]).validate(arguments)
        except Exception:
            _http_error(422, "invalid_arguments", "arguments 不符合外部工具 inputSchema")
        current = _find_server_locked(server_id)
        if current is None or current.get("publication_status") != "published":
            _http_error(409, "tool_unavailable", "外部工具当前未发布")
        if current.get("gateway_busy"):
            _http_error(409, "busy", "外部工具正在处理另一项调用")
        server_url = current["url"]
        token_env = approved.get("token_env")
        current["gateway_busy"] = True
        current["last_call"] = {
            "caller": f"account:{account}",
            "tool": tool_name,
            "status": "calling",
            "via": "NEF northbound MCP",
        }
    started = time.monotonic()
    outcome = "failed"
    try:
        async with asyncio.timeout(30):
            session = await _start_mcp(server_url, token_env)
            response, _ = await _mcp_request(
                server_url,
                token_env,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": tool_name, "arguments": arguments},
                },
                expected_id=2,
                session_id=session,
            )
            result = _result_from_message(response)
            if not isinstance(result.get("content"), list):
                raise _RemoteSchemaFailure("invalid_call_result")
            if "isError" in result and not isinstance(result["isError"], bool):
                raise _RemoteSchemaFailure("invalid_call_result")
            outcome = "tool_error" if result.get("isError") else "returned"
            return copy.deepcopy(result)
    except _RemoteFailure as exc:
        status, message = _upstream_failure_status(exc.code)
        _http_error(status, exc.code, message)
    except _RemoteSchemaFailure as exc:
        _http_error(502, exc.code, "外部 MCP 服务器响应未通过协议或调用结果校验")
    except TimeoutError:
        _http_error(504, "upstream_timeout", "外部 MCP 工具调用超时，执行结果可能未知")
    finally:
        with _STATE_LOCK:
            current = _find_server_locked(server_id)
            if current is not None:
                current["gateway_busy"] = False
                last_call = current.get("last_call")
                if isinstance(last_call, dict):
                    last_call.update(
                        status=outcome,
                        elapsed_ms=round((time.monotonic() - started) * 1000),
                    )


def call_external_tool_sync(
    account: str,
    mcp_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    return asyncio.run(call_external_tool(account, mcp_name, arguments))


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

    @router.get("/api/v1/network/trf/servers")
    async def list_trf_servers(authorization: str | None = Header(default=None)):
        auth(authorization, "af:register")
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "网络登记配置无效")
        collection_url = config.get("trf_mcp_servers_url")
        if not collection_url:
            return {"status": "not_configured", "servers": []}
        try:
            servers = await _read_trf_servers(
                collection_url,
                token_env=config.get("token_env"),
            )
        except _RemoteSchemaFailure as exc:
            _http_error(502, exc.code, "TRF MCP 服务器列表响应未通过 schema 校验")
        except _RemoteFailure as exc:
            status, message = _upstream_failure_status(exc.code)
            _http_error(status, exc.code, message)
        return {"status": "loaded", "servers": servers}

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
                        market = _market_tool_snapshot(server, tool, available=True)
                        items.append({
                            "id": server["id"] + ":" + tool["name"],
                            "name": tool["name"], "description": tool.get("description", ""),
                            "kind": "tool", "source": "AF", "provider": server["name"],
                            "server_id": server["id"], "inputSchema": copy.deepcopy(tool["inputSchema"]),
                            "serverName": server.get("serverName", server["name"]),
                            "toolType": "third-party tool",
                            "registration_status": _market_trf_registration_status(server),
                            "mcp_name": market["mcp_name"],
                            "price": 0,
                            "billing": "demo_free",
                        })
                for package in state["packages"].values():
                    if package.get("publication_status") == "published":
                        items.append({
                            "id": package["id"], "name": package["name"],
                            "description": package["description"], "kind": "package",
                            "source": "local", "steps": copy.deepcopy(package["steps"]),
                        })
            return {"items": items}

    @router.get("/api/v1/network/market/subscriptions")
    async def list_market_subscriptions(
        authorization: str | None = Header(default=None),
    ):
        _, identity = auth(authorization, None)
        account = _account_from_record(identity)
        return {"subscriptions": market_subscriptions(account)}

    @router.post("/api/v1/network/market/subscriptions")
    async def subscribe_market(
        payload: dict[str, Any] = Body(...),
        authorization: str | None = Header(default=None),
    ):
        _, identity = auth(authorization, "capabilities:invoke")
        if not isinstance(payload, dict) or set(payload) != {"tool_id"}:
            _http_error(422, "invalid_request", "请求仅允许 tool_id 字段")
        tool_id = _require_text(payload.get("tool_id"), "tool_id", MAX_ID_LENGTH)
        account = _account_from_record(identity)
        subscribe_market_tool(account, tool_id)
        return {"subscribed": True, "tool_id": tool_id, "billing": "demo_free"}

    @router.delete("/api/v1/network/market/subscriptions")
    async def unsubscribe_market(
        payload: dict[str, Any] = Body(...),
        authorization: str | None = Header(default=None),
    ):
        _, identity = auth(authorization, "capabilities:invoke")
        if not isinstance(payload, dict) or set(payload) != {"tool_id"}:
            _http_error(422, "invalid_request", "请求仅允许 tool_id 字段")
        tool_id = _require_text(payload.get("tool_id"), "tool_id", MAX_ID_LENGTH)
        account = _account_from_record(identity)
        unsubscribe_market_tool(account, tool_id)
        return {"subscribed": False, "tool_id": tool_id, "billing": "demo_free"}

    @router.post("/api/v1/network/servers")
    async def register_network_server(
        payload: dict[str, Any] = Body(...),
        authorization: str | None = Header(default=None),
    ):
        _key, record = auth(authorization, "af:register")
        account = _account_from_record(record)
        return register_server(payload, account)

    def register_server(payload, account, opened=False):
        explicit_server_name = "serverName" in payload
        if explicit_server_name:
            server_name = _require_trf_server_name(payload.get("serverName"))
            if "name" in payload:
                alias = _require_text(payload.get("name"), "name", MAX_NAME_LENGTH)
                if alias != server_name:
                    _http_error(422, "invalid_request", "name 与 serverName 必须一致")
        else:
            server_name = _require_text(payload.get("name"), "name", MAX_NAME_LENGTH)
        if server_name.startswith(_TRF_RESERVED_SERVER_PREFIX):
            _http_error(
                422,
                "reserved_server_name",
                "serverName 的 nef-cap- 前缀保留给 NEF 内置能力",
            )
        name = server_name
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
            enforce_global_name = (
                explicit_server_name
                or bool(_TRF_SERVER_NAME.fullmatch(server_name))
                or bool(existing and existing.get("_server_name_explicit"))
            )
            if enforce_global_name:
                if not _TRF_SERVER_NAME.fullmatch(server_name):
                    _http_error(
                        422,
                        "invalid_server_name",
                        "serverName 必须匹配 [a-zA-Z0-9][a-zA-Z0-9._-]{0,127}",
                    )
                conflict = next(
                    (
                        candidate
                        for owner_state in _ACCOUNTS.values()
                        for candidate in owner_state["servers"].values()
                        if candidate is not existing
                        and candidate.get("serverName", candidate.get("name")) == server_name
                    ),
                    None,
                )
                if conflict is not None:
                    _http_error(409, "server_name_conflict", "serverName 已由其他 MCP URL 使用")
            if existing:
                if existing.get("discovery_status") == "discovering" or existing.get("sync_status") == "syncing" or existing.get("gateway_busy"):
                    _http_error(409, "busy", "服务正在处理另一项操作")
                if existing.get("publication_status") == "published":
                    _http_error(409, "already_published", "请先取消发布，再更新服务")
                if existing.get("trf_may_exist"):
                    _http_error(409, "withdraw_required", "请先重试撤回 TRF 记录，再更新服务")
                if (
                    existing.get("_trf_target_name")
                    and existing["_trf_target_name"] != server_name
                ):
                    _http_error(
                        409,
                        "server_name_locked",
                        "首次 TRF 发布名称已锁定，不能在该记录上改名",
                    )
                existing.update(
                    name=name,
                    serverName=server_name,
                    description=description,
                    _server_name_explicit=bool(
                        explicit_server_name or existing.get("_server_name_explicit")
                    ),
                )
                return {**_public_record(existing), "created": False}
            if len(state["servers"]) >= MAX_SERVERS_PER_ACCOUNT:
                _http_error(409, "limit_exceeded", "每个账号最多注册 64 个网络服务器")
            server_id = _new_id("srv", state["servers"])
            server = {
                "id": server_id,
                "name": name,
                "serverName": server_name,
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
                "_server_name_explicit": explicit_server_name,
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
                _http_error(
                    503,
                    "not_configured",
                    "请在配置中填写 registry.mcp_servers allowlist",
                )
            _mark_discovery_failure(account, server_id)
            _http_error(
                403,
                "not_approved",
                "该 MCP 服务器 URL 不在 registry.mcp_servers allowlist 中",
            )

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

    async def change_trf_server_publication(account, record_id, publish, config):
        with _STATE_LOCK:
            record = _ACCOUNTS[account]["servers"][record_id]
            if (
                record.get("sync_status") == "syncing"
                or record.get("discovery_status") == "discovering"
                or record.get("gateway_busy")
            ):
                _http_error(409, "busy", "服务正在处理另一项操作")
            record["publication_status"] = "published" if publish else "unpublished"
            record["sync_status"] = "pending"
            record.pop("sync_error", None)
            record.pop("sync_note", None)

            if not publish and not record.get("trf_may_exist"):
                record.update(
                    sync_status="not_required",
                    sync_note="已从首页下架，未向 TRF 发布过",
                )
                return _public_record(record)

            if publish:
                try:
                    payload = _trf_publication(record)
                except HTTPException as exc:
                    record.update(
                        sync_status="failed",
                        sync_error=exc.detail,
                        sync_note="已在首页发布，但 serverName 不符合 TRF 契约",
                    )
                    return _public_record(record)
                target_url = record.get("_trf_target_url") or config.get(
                    "trf_mcp_servers_url"
                )
                target_name = record.get("_trf_target_name") or payload["serverName"]
                if not target_url:
                    record["sync_note"] = "已在首页发布，TRF MCP 服务器集合地址待配置"
                    return _public_record(record)
                payload["serverName"] = target_name
                conflict = next(
                    (
                        candidate
                        for owner_state in _ACCOUNTS.values()
                        for candidate in owner_state["servers"].values()
                        if candidate is not record
                        and candidate.get("_trf_target_url") == target_url
                        and candidate.get("_trf_target_name") == target_name
                        and (
                            candidate.get("trf_may_exist")
                            or candidate.get("sync_status") == "syncing"
                        )
                    ),
                    None,
                )
                if conflict is not None:
                    _http_error(
                        409,
                        "server_name_conflict",
                        "该 TRF 集合中已有同名 MCP 服务器发布任务",
                    )
                record["_trf_target_url"] = target_url
                record["_trf_target_name"] = target_name
                # POST 超时也可能已经送达，必须保留撤回责任。
                record["trf_may_exist"] = True
            else:
                target_url = record.get("_trf_target_url")
                target_name = record.get("_trf_target_name")
                if not target_url or not target_name:
                    record.update(
                        sync_status="failed",
                        sync_error="trf_target_unknown",
                        sync_note="已从首页下架，但首次 TRF 发布目标不可用",
                    )
                    return _public_record(record)
                payload = None
            record["sync_status"] = "syncing"

        if publish:
            try:
                await _remote_request(
                    "POST",
                    target_url,
                    token_env=config.get("token_env"),
                    payload=payload,
                )
            except _RemoteFailure as exc:
                with _STATE_LOCK:
                    record.update(
                        sync_status="failed",
                        sync_error=exc.code,
                        sync_note="首页已发布，TRF POST 失败或结果未知，可重试",
                    )
                    return _public_record(record)
            with _STATE_LOCK:
                record.update(
                    sync_status="syncing",
                    sync_note="已提交 TRF，正在以集合 GET 结果确认",
                )
            try:
                remote_servers = await _read_trf_servers(
                    target_url,
                    token_env=config.get("token_env"),
                )
            except _RemoteSchemaFailure as exc:
                with _STATE_LOCK:
                    record.update(
                        sync_status="failed",
                        sync_error=exc.code,
                        sync_note="TRF POST 已提交，但集合 GET schema 无法用于确认",
                    )
                    return _public_record(record)
            except _RemoteFailure as exc:
                with _STATE_LOCK:
                    record.update(
                        sync_status="submitted",
                        sync_error=exc.code,
                        sync_note="TRF POST 已提交，但集合 GET 暂时无法确认",
                    )
                    return _public_record(record)
            confirmed = any(
                _same_trf_server(candidate, payload) for candidate in remote_servers
            )
            with _STATE_LOCK:
                if confirmed:
                    record.update(sync_status="synced", sync_note="TRF 集合已读回确认")
                    record.pop("sync_error", None)
                else:
                    record.update(
                        sync_status="submitted",
                        sync_error="trf_confirmation_unknown",
                        sync_note="TRF POST 已提交，但集合 GET 未读回匹配的契约记录",
                    )
                return _public_record(record)

        try:
            await _delete_trf_server(
                target_url,
                target_name,
                token_env=config.get("token_env"),
            )
        except _RemoteFailure as exc:
            with _STATE_LOCK:
                record.update(
                    sync_status="failed",
                    sync_error=exc.code,
                    sync_note="首页已下架，TRF DELETE 失败或结果未知，可重试",
                )
                return _public_record(record)
        with _STATE_LOCK:
            record.update(
                sync_status="syncing",
                sync_note="已提交 TRF DELETE，正在以集合 GET 结果确认",
            )
        try:
            remote_servers = await _read_trf_servers(
                target_url,
                token_env=config.get("token_env"),
            )
        except _RemoteSchemaFailure as exc:
            with _STATE_LOCK:
                record.update(
                    sync_status="failed",
                    sync_error=exc.code,
                    sync_note="TRF DELETE 已提交，但集合 GET schema 无法用于确认",
                )
                return _public_record(record)
        except _RemoteFailure as exc:
            with _STATE_LOCK:
                record.update(
                    sync_status="submitted",
                    sync_error=exc.code,
                    sync_note="TRF DELETE 已提交，但集合 GET 暂时无法确认",
                )
                return _public_record(record)
        still_present = any(
            candidate["serverName"] == target_name for candidate in remote_servers
        )
        with _STATE_LOCK:
            if still_present:
                record.update(
                    sync_status="submitted",
                    sync_error="trf_confirmation_unknown",
                    sync_note="TRF DELETE 已提交，但集合 GET 仍发现同名记录",
                )
            else:
                record.update(
                    sync_status="synced",
                    sync_note="TRF 集合已确认同名记录缺席",
                    trf_may_exist=False,
                )
                record.pop("sync_error", None)
            return _public_record(record)

    async def change_publication(account, collection, record_id, publish):
        try:
            config = _load_config()
        except _ConfigError:
            _http_error(503, "invalid_config", "NEF_REGISTRY_CONFIG 无效")
        with _STATE_LOCK:
            current = _ACCOUNTS[account][collection][record_id]
            use_new_trf = (
                collection == "servers"
                and (
                    (publish and _uses_trf_server_contract(config, current))
                    or (not publish and bool(current.get("_trf_target_url")))
                )
            )
        if use_new_trf:
            return await change_trf_server_publication(
                account,
                record_id,
                publish,
                config,
            )
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
            if (
                collection == "packages"
                and publish
                and (
                    config.get("trf_mcp_servers_url")
                    or not config.get("publish_url")
                )
            ):
                record.update(
                    sync_status="not_required",
                    sync_note="自助套餐仅在本地发布，不同步到 TRF MCP 服务器集合",
                )
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

    @router.delete("/api/v1/network/servers/{server_id}")
    async def delete_network_server(
        server_id: str,
        authorization: str | None = Header(default=None),
    ):
        _, identity = auth(authorization, "af:register")
        account = _account_from_record(identity)
        owned = _get_owned_server(account, server_id)
        source_account = owned["source_account"]
        with _STATE_LOCK:
            state = _ACCOUNTS.get(source_account, {})
            record = state.get("servers", {}).get(server_id)
            if record is None:
                _http_error(404, "not_found", "网络服务器不存在")
            if (
                record.get("sync_status") == "syncing"
                or record.get("discovery_status") == "discovering"
                or record.get("gateway_busy")
            ):
                _http_error(409, "busy", "服务正在处理另一项操作，暂不能删除")
            if record.get("publication_status") == "published":
                _http_error(409, "unpublish_required", "请先取消发布，再删除本地记录")
            if record.get("trf_may_exist"):
                _http_error(
                    409,
                    "withdraw_required",
                    "TRF 记录可能仍存在，请先重试撤回并确认缺席",
                )
            _remove_market_subscriptions_for_server_locked(server_id)
            del state["servers"][server_id]
        return {"deleted": True, "id": server_id}

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
