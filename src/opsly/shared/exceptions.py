"""Agent and infrastructure exceptions."""

from __future__ import annotations


class AgentError(Exception):
    """Base error for agent boundaries."""

    def __init__(self, message: str, *, agent: str | None = None) -> None:
        super().__init__(message)
        self.agent = agent


class OrchestratorError(AgentError):
    pass


class IndexingError(AgentError):
    pass


class GraphQueryError(AgentError):
    pass


class AnalysisError(AgentError):
    pass


class MemoryError(AgentError):
    pass
