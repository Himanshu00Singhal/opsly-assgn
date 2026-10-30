"""Pydantic settings per service."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Neo4jSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="password", alias="NEO4J_PASSWORD")
    neo4j_database: str = Field(default="neo4j", alias="NEO4J_DATABASE")


class GroqSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model_synthesis: str = Field(default="qwen/qwen3.8-27b", alias="GROQ_MODEL_SYNTHESIS")
    groq_model_routing: str = Field(default="qwen/qwen3.8-27b", alias="GROQ_MODEL_ROUTING")


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "testing", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    fastapi_repo_path: str = Field(default="./data/repos/fastapi", alias="FASTAPI_REPO_PATH")
    fastapi_repo_url: str = Field(
        default="https://github.com/fastapi/fastapi.git", alias="FASTAPI_REPO_URL"
    )
    memory_db_path: str = Field(default="./data/memory/sessions.db", alias="MEMORY_DB_PATH")
    gateway_host: str = Field(default="0.0.0.0", alias="GATEWAY_HOST")
    gateway_port: int = Field(default=8000, alias="GATEWAY_PORT")
    gateway_api_key: str = Field(default="", alias="GATEWAY_API_KEY")
    agent_timeout_seconds: float = Field(default=60.0, alias="AGENT_TIMEOUT_SECONDS")
    agent_retry_count: int = Field(default=1, alias="AGENT_RETRY_COUNT")

    mcp_orchestrator_url: str = Field(
        default="http://127.0.0.1:9001/mcp", alias="MCP_ORCHESTRATOR_URL"
    )
    mcp_indexer_url: str = Field(default="http://127.0.0.1:9002/mcp", alias="MCP_INDEXER_URL")
    mcp_graph_query_url: str = Field(
        default="http://127.0.0.1:9003/mcp", alias="MCP_GRAPH_QUERY_URL"
    )
    mcp_code_analyst_url: str = Field(
        default="http://127.0.0.1:9004/mcp", alias="MCP_CODE_ANALYST_URL"
    )
    mcp_memory_url: str = Field(default="http://127.0.0.1:9005/mcp", alias="MCP_MEMORY_URL")


@lru_cache
def get_app_settings() -> AppSettings:
    return AppSettings()


@lru_cache
def get_neo4j_settings() -> Neo4jSettings:
    return Neo4jSettings()


@lru_cache
def get_groq_settings() -> GroqSettings:
    return GroqSettings()
