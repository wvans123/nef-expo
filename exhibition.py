# -*- coding: utf-8 -*-
"""Live forwarding with bounded shared scene and private exhibition channels.
No intent planning, fabricated partner task IDs, or timed business statuses.
"""
import hashlib
import json
import os
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from integration_config import section as integration_section
from fastapi import Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from scene_services import SCENES

CHANNELS = {}
LOCK = threading.RLock()
MAX_JSON = 64 * 1024
MAX_UPLOAD = 16 * 1024 * 1024
MAX_MEDIA_TOTAL = 64 * 1024 * 1024
MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm"}


def config():
    path = os.environ.get("NEF_BRIDGE_CONFIG")
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8-sig")) if path else integration_section("bridge")
        if not isinstance(cfg, dict) or not isinstance(cfg.get("capabilities", {}), dict) or not isinstance(cfg.get("scenes", {}), dict):
            raise ValueError()
        return cfg
    except (OSError, ValueError):
        raise HTTPException(503, "内部接口配置无法读取，请联系对接人员")


def live_requested(value):
    # Existing workbench retains its explicit demo default. New portal always sends live.
    if value not in (None, "demo", "live"):
        raise HTTPException(422, "X-NEF-Execution 仅支持 live / demo")
    return value == "live"


def _template(value, context):
    if isinstance(value, dict):
        return {k: _template(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_template(v, context) for v in value]
    if isinstance(value, str) and value.startswith("$"):
        if value[1:] not in context:
            raise ValueError("unknown placeholder")
        return context[value[1:]]
    return value


def result_configured(service_id):
    scene = config().get("scenes", {}).get(service_id, {})
    route = scene.get("result") if isinstance(scene, dict) else None
    return isinstance(route, dict) and bool(route.get("url"))


def forward(kind, context):
    cfg = config()
    if kind in ("scene_intent", "scene_invoke", "scene_result"):
        routes = cfg.get("scenes", {}).get(context["service_id"], {})
        if not isinstance(routes, dict):
            raise HTTPException(503, "场景接口配置不完整")
        route = routes.get({"scene_intent": "intent", "scene_invoke": "invoke", "scene_result": "result"}[kind])
    else:
        route = cfg.get(kind) if kind in ("intent", "package_invoke") else cfg.get("capabilities", {}).get(context["capability_id"])
    if not route:
        raise HTTPException(503, {"status": "not_configured", "message": "内部接口待对接，未发送请求"})
    try:
        endpoint = route["url"]
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
        method = route.get("method", "GET" if kind == "scene_result" else "POST").upper()
        body = _template(route.get("body", {"text": "$text"} if kind in ("intent", "scene_intent", "scene_result") else "$arguments"), context) if method != "GET" else None
        if method not in (("GET", "POST") if kind == "scene_result" else ("POST", "PUT", "PATCH")):
            raise ValueError()
        headers = {"X-NEF-Request-ID": context["request_id"]}
        content_type = route.get("content_type", "application/json").split(";")[0].strip().lower()
        if content_type not in ("application/json", "text/plain") or (content_type == "text/plain" and method != "GET" and not isinstance(body, str)):
            raise ValueError()
        options = {} if method == "GET" else ({"content": body.encode("utf-8")} if content_type == "text/plain" else {"json": body})
        if method != "GET":
            headers["Content-Type"] = content_type + ("; charset=utf-8" if content_type == "text/plain" else "")
        token_env = route.get("token_env")
        if token_env:
            token = os.environ.get(token_env)
            if not token:
                raise ValueError()
            headers["Authorization"] = "Bearer " + token
        timeout = max(1, min(30, float(route.get("timeout_seconds", 8))))
        delay = max(0, min(5, float(route.get("delay_seconds", 0)))) if kind == "scene_result" else 0
    except (KeyError, TypeError, ValueError, AttributeError):
        raise HTTPException(503, "内部接口配置不完整，未发送请求")
    try:
        if delay:
            time.sleep(delay)
        # Operator-controlled routes only; never inherit a workstation proxy or follow redirects.
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=timeout) as client:
            with client.stream(method, endpoint, **options, headers=headers) as response:
                if not 200 <= response.status_code < 300:
                    raise HTTPException(502, {"status": "upstream_error", "http_status": response.status_code,
                                              "message": "网络侧返回非成功响应，未判定业务完成"})
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1024 * 1024:
                        raise HTTPException(502, "网络侧响应过大，请通过场景数据通道传输")
                status_code = response.status_code
    except httpx.TimeoutException:
        raise HTTPException(504, {"status": "unknown", "message": "网络侧响应超时，是否已受理未知；请勿盲目重发"})
    except httpx.HTTPError:
        raise HTTPException(502, {"status": "unknown", "message": "网络侧连接异常，未收到可确认的回执"})
    try:
        payload = json.loads(raw) if raw else None
    except (ValueError, UnicodeDecodeError):
        payload = raw.decode("utf-8", errors="replace")
    return {"request_id": context["request_id"], "status": "forwarded", "data_source": "live",
            "summary": "已收到网络侧响应", "upstream": {"http_status": status_code, "body": payload}}


async def bounded_body(request, limit):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, "内容超过接收限制")
    return bytes(data)


def receiver(channel_id, authorization):
    with LOCK:
        channel = CHANNELS.get(channel_id)
        token = (authorization or "").removeprefix("Bearer ")
        digest = hashlib.sha256(token.encode()).hexdigest()
        if not channel or not authorization or not authorization.startswith("Bearer ") or not secrets.compare_digest(digest, channel["receiver_hash"]):
            raise HTTPException(401, "无效的场景接收凭证")
        return channel


def owner(channel_id, account):
    with LOCK:
        channel = CHANNELS.get(channel_id)
        if not channel or channel["owner"] not in (None, account):
            raise HTTPException(404, "场景接收通道不存在")
        return channel


def feedback_receiver(authorization):
    """Resolve a write-only key; caller-supplied scene/channel never selects a target."""
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 512:
        raise HTTPException(401, "无效的场景接收凭证")
    digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
    with LOCK:
        for channel in CHANNELS.values():
            if secrets.compare_digest(digest, channel["receiver_hash"]):
                return channel
    raise HTTPException(401, "无效的场景接收凭证")


async def read_event(request):
    try:
        event = json.loads((await bounded_body(request, MAX_JSON)).decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(422, '需要 UTF-8 编码的 JSON 对象。PowerShell 请用 JSON 字符串管道传给 curl.exe -d "@-"，避免 -d 内双引号丢失。')
    return event


def shared_channel(service_id):
    if service_id not in SCENES:
        raise HTTPException(404, {"message": "场景服务不存在", "available": list(SCENES)})
    cid = "scene_" + service_id
    with LOCK:
        if cid not in CHANNELS:
            key = "recv_" + secrets.token_hex(24)
            CHANNELS[cid] = {"name": SCENES[service_id]["name"], "owner": None, "service_id": service_id,
                             "access_key": key, "receiver_hash": hashlib.sha256(key.encode()).hexdigest(),
                             "events": [], "media": {}, "sequence": 0}
        return CHANNELS[cid]


def channel_events(channel_id, channel, after=0, request_id=None):
    with LOCK:
        reset = after > channel["sequence"]
        cursor = 0 if reset else after
        retained = channel["events"]
        selected = [dict(event) for event in retained if event["id"] > cursor
                    and (request_id is None or event.get("request_id") == request_id)]
        return {"channel_id": channel_id, "service_id": channel.get("service_id"), "name": channel["name"],
                "events": selected, "next_cursor": channel["sequence"], "reset_required": reset,
                "history_truncated": bool(retained and retained[0]["id"] > cursor + 1)}


def pull_result(service_id, context):
    channel = shared_channel(service_id)
    try:
        result = forward("scene_result", {"service_id": service_id, "text": "", **context})
        payload = result["upstream"]["body"]
        if result["upstream"]["http_status"] == 204 or payload in (None, "", {}, []):
            return {"status": "empty"}
        signature = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if isinstance(payload, dict) and isinstance(payload.get("final_result"), str):
            event = {"kind": "status", "text": payload["final_result"]}
        elif isinstance(payload, (dict, list)):
            event = {"kind": "data", "data": payload}
        else:
            event = {"kind": "status", "text": str(payload)}
        with LOCK:
            if channel.get("pull_signature") == signature:
                return {"status": "unchanged"}
            saved = save_event(channel, event)
            channel["pull_signature"] = signature
        return {"status": "stored", **saved}
    except HTTPException as exc:
        return {"status": "unavailable", "detail": exc.detail}


def save_event(channel, event):
    if not isinstance(event, dict) or event.get("kind") not in ("status", "data", "image", "video"):
        raise HTTPException(422, "kind 需为 status / data / image / video")
    for field in ("title", "text", "source", "request_id"):
        maximum = 16000 if field == "text" else 1000
        if field in event and (not isinstance(event[field], str) or len(event[field]) > maximum):
            raise HTTPException(422, f"{field} 需要长度不超过 {maximum} 的字符串")
    if "data" in event and not isinstance(event["data"], (dict, list)):
        raise HTTPException(422, "data 需要对象或数组")
    with LOCK:
        if event["kind"] in ("image", "video"):
            asset_id = event.get("asset_id")
            if not isinstance(asset_id, str):
                raise HTTPException(422, "请先上传媒体并提供 asset_id")
            asset = channel["media"].get(asset_id)
            if not asset or not asset["type"].startswith(event["kind"] + "/"):
                raise HTTPException(422, "媒体不存在或类型不匹配")
        channel["sequence"] += 1
        saved = {k: event[k] for k in ("kind", "title", "text", "source", "request_id", "data", "asset_id") if k in event}
        saved.update({"id": channel["sequence"], "received_at": time.time()})
        channel["events"].append(saved)
        channel["events"] = channel["events"][-100:]
    return {"received": True, "event_id": saved["id"]}


async def read_media(request):
    mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime not in MEDIA_TYPES:
        raise HTTPException(415, "支持 PNG / JPEG / WebP 图片和 MP4 / WebM 视频文件")
    data = await bounded_body(request, MAX_UPLOAD)
    signatures = {"image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
                  "image/jpeg": data.startswith(b"\xff\xd8\xff"),
                  "image/webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
                  "video/mp4": data[4:8] == b"ftyp", "video/webm": data.startswith(b"\x1aE\xdf\xa3")}
    if not signatures[mime]:
        raise HTTPException(415, "文件头与声明的媒体类型不匹配")
    return mime, data


def save_media(channel, mime, data):
    with LOCK:
        size = sum(len(a["bytes"]) for c in CHANNELS.values() for a in c["media"].values())
        if size + len(data) > MAX_MEDIA_TOTAL:
            raise HTTPException(507, "演示媒体存储已满，请由管理员安排服务重启清理")
        aid = "media_" + secrets.token_hex(10)
        channel["media"][aid] = {"bytes": data, "type": mime}
    return {"asset_id": aid, "content_type": mime, "size": len(data)}


class ChannelReq(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    service_id: str | None = None


def mount_routes(app, auth):
    @app.get("/api/v1/exhibition/info")
    def info():
        cfg = config()
        return {"intent_configured": bool(cfg.get("intent")),
                "configured_capabilities": sorted(cfg.get("capabilities", {})),
                "max_upload_bytes": MAX_UPLOAD,
                "media_types": sorted(MEDIA_TYPES), "storage": "memory"}

    @app.get("/api/v1/exhibition/channels")
    def channels(authorization: str = Header(None)):
        _, rec = auth(authorization)
        with LOCK:
            return {"channels": [{"id": cid, "name": c["name"], "event_count": len(c["events"]), "service_id": c.get("service_id")}
                                  for cid, c in CHANNELS.items() if c["owner"] in (None, rec["account"])]}

    @app.post("/api/v1/exhibition/channels")
    def create_channel(req: ChannelReq, response: Response, authorization: str = Header(None)):
        _, rec = auth(authorization)
        response.headers["Cache-Control"] = "no-store"
        if req.service_id is not None and req.service_id not in SCENES:
            raise HTTPException(422, "场景服务不存在")
        name = req.name.strip()
        if not name:
            raise HTTPException(422, "通道名称不能为空")
        with LOCK:
            if len(CHANNELS) >= 64 or sum(c["owner"] == rec["account"] for c in CHANNELS.values()) >= 8:
                raise HTTPException(429, "场景通道已达上限")
            cid, key = "scene_" + secrets.token_hex(8), "recv_" + secrets.token_hex(24)
            CHANNELS[cid] = {"name": name, "owner": rec["account"], "service_id": req.service_id,
                             "receiver_hash": hashlib.sha256(key.encode()).hexdigest(),
                             "events": [], "media": {}, "sequence": 0}
        return {"id": cid, "name": name, "service_id": req.service_id, "receiver_key": key,
                "feedback_endpoint": "/api/v1/scene-feedback",
                "events_endpoint": f"/api/v1/exhibition/channels/{cid}/events",
                "media_endpoint": f"/api/v1/exhibition/channels/{cid}/media"}

    @app.post("/api/v1/services/{service_id}/feedback-access")
    def feedback_access(service_id: str, response: Response, authorization: str = Header(None)):
        """Shared scene access; general and manually created channels remain private."""
        _, rec = auth(authorization)
        response.headers["Cache-Control"] = "no-store"
        if service_id not in SCENES and service_id != "general":
            raise HTTPException(404, "场景服务不存在")
        if service_id in SCENES:
            channel = shared_channel(service_id)
            return {"id": "scene_" + service_id, "name": channel["name"], "service_id": service_id,
                    "receiver_key": channel["access_key"], "feedback_endpoint": "/api/v1/scene-feedback",
                    "open_endpoint": "/api/v1/scene-feedback/" + service_id}
        scene_id = None if service_id == "general" else service_id
        with LOCK:
            for cid, channel in CHANNELS.items():
                if (channel["owner"] == rec["account"] and channel.get("service_id") == scene_id
                        and channel.get("access_key")):
                    break
            else:
                if len(CHANNELS) >= 64 or sum(c["owner"] == rec["account"] for c in CHANNELS.values()) >= 8:
                    raise HTTPException(429, "场景接口已达上限")
                cid, key = "scene_" + secrets.token_hex(8), "recv_" + secrets.token_hex(24)
                channel = {"name": SCENES[service_id]["name"] if scene_id else "能力调用",
                           "owner": rec["account"], "service_id": scene_id,
                           "access_key": key, "receiver_hash": hashlib.sha256(key.encode()).hexdigest(),
                           "events": [], "media": {}, "sequence": 0}
                CHANNELS[cid] = channel
            return {"id": cid, "name": channel["name"], "service_id": scene_id,
                    "receiver_key": channel["access_key"], "feedback_endpoint": "/api/v1/scene-feedback"}

    @app.post("/api/v1/exhibition/channels/{channel_id}/events")
    async def receive_event(channel_id: str, request: Request, authorization: str = Header(None)):
        channel = receiver(channel_id, authorization)
        return save_event(channel, await read_event(request))

    @app.get("/api/v1/exhibition/channels/{channel_id}/events")
    def events(channel_id: str, authorization: str = Header(None),
               after: int = Query(0, ge=0), request_id: str | None = Query(None, min_length=1, max_length=1000)):
        _, rec = auth(authorization)
        channel = owner(channel_id, rec["account"])
        return channel_events(channel_id, channel, after, request_id)

    @app.post("/api/v1/exhibition/channels/{channel_id}/media")
    async def upload(channel_id: str, request: Request, authorization: str = Header(None)):
        channel = receiver(channel_id, authorization)
        mime, data = await read_media(request)
        return save_media(channel, mime, data)

    @app.post("/api/v1/scene-feedback")
    async def scene_feedback(request: Request, authorization: str = Header(None)):
        channel = feedback_receiver(authorization)
        return await receive_feedback(channel, request)

    @app.post("/api/v1/scene-feedback/{service_id}")
    async def open_scene_feedback(service_id: str, request: Request):
        return await receive_feedback(shared_channel(service_id), request)

    @app.get("/api/v1/scene-feedback/{service_id}")
    def open_scene_events(service_id: str, response: Response, after: int = Query(0, ge=0)):
        response.headers["Cache-Control"] = "no-store"
        return channel_events("scene_" + service_id, shared_channel(service_id), after)

    async def receive_feedback(channel, request):
        mime = request.headers.get("content-type", "").split(";")[0].strip().lower()
        request_id = request.headers.get("x-nef-request-id")
        if request_id is not None and not 1 <= len(request_id) <= 1000:
            raise HTTPException(422, "X-NEF-Request-ID 需要 1 到 1000 字符")
        if mime == "application/json":
            event = await read_event(request)
            if isinstance(event, dict) and "final_result" in event:
                result = event["final_result"]
                if set(event) - {"final_result", "request_id"} or not isinstance(result, str) or not result.strip():
                    raise HTTPException(422, "final_result 需为非空文字结果")
                event = {"kind": "status", "text": result,
                         **({"request_id": event["request_id"]} if "request_id" in event else {})}
            if request_id is not None and isinstance(event, dict):
                if "request_id" in event and event["request_id"] != request_id:
                    raise HTTPException(422, "请求头与正文 request_id 不一致")
                event["request_id"] = request_id
            return save_event(channel, event)
        mime, data = await read_media(request)
        event = {"kind": mime.split("/")[0], "source": channel["name"]}
        if request_id is not None:
            event["request_id"] = request_id
        # Single atomic write: a rejected upload must never publish an event.
        with LOCK:
            asset = save_media(channel, mime, data)
            event["asset_id"] = asset["asset_id"]
            return save_event(channel, event)

    @app.get("/api/v1/exhibition/channels/{channel_id}/media/{asset_id}")
    def media(channel_id: str, asset_id: str, authorization: str = Header(None)):
        _, rec = auth(authorization)
        channel = owner(channel_id, rec["account"])
        with LOCK:
            asset = channel["media"].get(asset_id)
            if not asset:
                raise HTTPException(404, "媒体不存在")
            return Response(asset["bytes"], media_type=asset["type"],
                            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})
