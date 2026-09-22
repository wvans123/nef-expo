"""Public response schema for the Access-protected demo subscription lookup."""
from typing import Any, Literal

from pydantic import BaseModel, Field


class SubscribedTool(BaseModel):
    capability_id: str
    name: str = Field(description="Exact MCP tools/call name.")
    display_name: str
    description: str
    inputSchema: dict[str, Any]
    grant_sources: list[str] = Field(
        description="direct, package:<id>, scene:<id>, or plan:<name>."
    )


class SubscribedPackage(BaseModel):
    id: str
    name: str
    capability_ids: list[str]


class SceneComponent(BaseModel):
    capability_id: str
    name: str
    standalone_entitled: bool


class SceneTool(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]


class SubscribedScene(BaseModel):
    service_id: str
    name: str
    modes: list[str]
    components: list[SceneComponent]
    tool: SceneTool | None


class PurchasedPackage(BaseModel):
    kind: Literal["scene", "capability_package"]
    id: str
    name: str
    description: str
    components: list[SceneComponent]
    modes: list[str] = Field(description="Scene entry modes; empty for a capability bundle.")
    intent_example: str | None
    tool: SceneTool | None


class ExternalToolSubscription(BaseModel):
    id: str
    server_id: str
    serverName: str
    name: str
    description: str
    inputSchema: dict[str, Any]
    mcp_name: str
    toolType: Literal["third-party tool"]
    price: Literal[0] = 0
    billing: Literal["demo_free"] = "demo_free"
    available: bool


class SubscriptionSnapshot(BaseModel):
    schema_version: Literal["1.1"] = "1.1"
    account_id: str = Field(description="Exact NEF demo account name, e.g. the string '1'.")
    generated_at: str = Field(description="UTC snapshot time, not last subscription change.")
    storage: Literal["memory"] = "memory"
    plan: str
    direct_subscriptions: list[str]
    subscribed_capabilities: list[str] = Field(
        description="Direct plus legacy package and selected scene capability grants."
    )
    entitled_capabilities: list[str] = Field(description="Available atomic tools with subscription or plan grants; excludes unsubscribed pay-per-call tools.")
    packages: list[SubscribedPackage]
    scene_subscriptions: list[str]
    tools: list[SubscribedTool]
    scene_services: list[SubscribedScene]
    purchased_packages: list[PurchasedPackage] = Field(
        description="Purchased scene services and legacy capability bundles with details; "
        "excludes unsold catalog entries, composition drafts and plan-only atomic grants."
    )
    external_tool_subscriptions: list[ExternalToolSubscription] = Field(
        default_factory=list,
        description="Explicit account subscriptions to individually published external MCP tools.",
    )
