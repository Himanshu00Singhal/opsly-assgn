"""Gateway request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(default="default")
    message: str
    stream: bool = False


class ChatResponse(BaseModel):
    session_id: str
    response: str
    meta: dict[str, Any] = Field(default_factory=dict)


class IndexRequest(BaseModel):
    mode: Literal["full", "incremental"] = "full"


class IndexResponse(BaseModel):
    job_id: str


class HealthResponse(BaseModel):
    status: str
    agents: dict[str, str]
