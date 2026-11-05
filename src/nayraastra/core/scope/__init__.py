"""Target normalization, scope guard, and task authorization."""

from nayraastra.core.scope.authorizer import AuthorizationDecision, TaskAuthorizer
from nayraastra.core.scope.guard import ScopeDecision, ScopeGuard, StaticResolver
from nayraastra.core.scope.normalize import normalize_target

__all__ = [
    "AuthorizationDecision",
    "ScopeDecision",
    "ScopeGuard",
    "StaticResolver",
    "TaskAuthorizer",
    "normalize_target",
]
