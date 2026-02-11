"""
Gateway Pydantic Models
=======================

Shared request / response models used across Gateway endpoints.
Matches the contract from ARCHITECTURE_V2.md §4 and §6.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


# ───────────────────────── Auth ─────────────────────────


class UserCreate(BaseModel):
    email: EmailStr
    password: str          # min 8 chars enforced in auth.py
    display_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    id: str
    email: str
    display_name: str
    created_at: datetime
    is_active: bool


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    user: User
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ───────────────────────── Graph ────────────────────────


class AgentBrief(BaseModel):
    id: str
    display_name: str


class GraphListItem(BaseModel):
    graph_id: str
    display_name: str
    description: str
    version: str
    task_types: list[str]
    agents: list[AgentBrief]
    features: list[str]


class GraphListResponse(BaseModel):
    graphs: list[GraphListItem]


class AgentConfig(BaseModel):
    model: str
    temperature: float
    fallback_model: Optional[str] = None
    endpoint: str = "default"


class PromptInfo(BaseModel):
    system: str              # First 500 chars of system prompt
    templates: list[str]     # Template names


class GraphTopologyResponse(BaseModel):
    graph_id: str
    topology: dict
    agents: dict[str, AgentConfig]
    prompts: dict[str, PromptInfo]
    manifest: dict


class GraphConfigResponse(BaseModel):
    graph_id: str
    agents: dict[str, AgentConfig]


# ────────────────────── Run / Task ──────────────────────


class CreateRunRequest(BaseModel):
    thread_id: Optional[str] = None
    task: str
    repository: Optional[str] = None
    context: Optional[str] = None
    graph_id: Optional[str] = None        # None → Switch-Agent auto-selects
    execution_mode: str = "auto"           # "auto" | "internal" | "cli"


class TaskClassification(BaseModel):
    graph_id: str
    complexity: int          # 1-10
    reasoning: str


class RunResponse(BaseModel):
    thread_id: str
    run_id: str
    graph_id: str
    classification: Optional[TaskClassification] = None
