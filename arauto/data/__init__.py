"""Persistência: repositórios de produto e registro de consultas."""
from .repositories import build_repository
from .querylog import QueryLog

__all__ = ["build_repository", "QueryLog"]


