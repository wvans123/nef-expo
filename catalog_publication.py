"""Explicit, selected NEF metadata export; not an NRF NF registration protocol."""
import hashlib
import json
from copy import deepcopy

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from scene_services import SCENES, tool_definition
from skills import CAP_INDEX


class CatalogSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability_ids: list[str] = Field(default_factory=list, max_length=64)
    service_ids: list[str] = Field(default_factory=list, max_length=16)


def publication(selection: CatalogSelection, base_url: str | None) -> dict:
    capabilities, services = selection.capability_ids, selection.service_ids
    if not capabilities and not services:
        raise HTTPException(422, {"code": "empty_selection", "message": "请选择需要发布的能力或场景"})
    if len(set(capabilities)) != len(capabilities) or len(set(services)) != len(services):
        raise HTTPException(422, {"code": "duplicate_selection", "message": "不能重复选择同一目录项"})
    if (any(cid not in CAP_INDEX or CAP_INDEX[cid].status != "available" for cid in capabilities)
            or any(sid not in SCENES for sid in services)):
        raise HTTPException(422, {"code": "invalid_selection", "message": "只能发布当前已开放的本地能力或场景"})
    if not base_url:
        raise HTTPException(503, {"code": "gateway_not_configured", "message": "请配置网络可访问的 NEF 入口 nef_base_url"})
    base = base_url.rstrip("/")
    items = []
    for cid in sorted(capabilities):
        cap = CAP_INDEX[cid]
        tool = cap.mcp_tool()
        items.append({
            "kind": "capability", "id": cid, "name": cap.name, "description": cap.description,
            "status": cap.status, "source": "NEF", "category": cap.category,
            "inputSchema": tool["inputSchema"],
            "standard_basis": deepcopy(cap.to_dict()["standard_basis"]),
            "interfaces": [
                {"mode": "api", "method": "POST", "url": f"{base}/api/v1/capabilities/{cid}/invoke"},
                {"mode": "tool", "method": "POST", "url": f"{base}/mcp", "tool_name": tool["name"]},
            ],
        })
    for sid in sorted(services):
        scene = SCENES[sid]
        interfaces = [{
            "mode": "intent", "method": "POST", "url": f"{base}/api/v1/services/{sid}/intent",
            "inputSchema": {"type": "object", "properties": {
                "text": {"type": "string", "minLength": 1, "maxLength": 16000}},
                "required": ["text"], "additionalProperties": False},
        }]
        if "api" in scene["modes"]:
            interfaces.append({
                "mode": "api", "method": "POST", "url": f"{base}/api/v1/services/{sid}/invoke",
                "inputSchema": tool_definition(scene)["inputSchema"],
            })
        if "tool" in scene["modes"]:
            interfaces.append({
                "mode": "tool", "method": "POST", "url": f"{base}/mcp",
                "tool_name": scene["tool_name"], "inputSchema": tool_definition(scene)["inputSchema"],
            })
        items.append({
            "kind": "scene", "id": sid, "name": scene["name"], "description": scene["description"],
            "status": "available", "source": "NEF", "modes": list(scene["modes"]),
            "components": deepcopy(scene["provenance"]["components"]), "interfaces": interfaces,
        })
    result = {
        "type": "nef_catalog_publication", "schema_version": "1.0", "source": "NEF",
        "catalog_id": "nef_" + hashlib.sha256(base.encode()).hexdigest()[:16],
        "update_mode": "upsert_selected", "items": items,
        "access": {"authentication": "nef-account-bearer", "entitlements_required": True,
                   "execution_header": {"X-NEF-Execution": "live"}},
        "execution_readiness": "not_verified",
    }
    result["revision"] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result
