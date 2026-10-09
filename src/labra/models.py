"""Every table, in one import. Alembic's env and the app import this module."""

from labra.adapters.identity_local import LocalCredential
from labra.auth.models import LoginAttempt, UserSession
from labra.core.db import Base
from labra.core.models import AuditLog, Consent, EventOutbox, NumberSeries, Setting, StoredFile
from labra.org.models import AppUser, Branch, Role, RolePermission, UserBranchRole

__all__ = [
    "AppUser",
    "AuditLog",
    "Base",
    "Branch",
    "Consent",
    "EventOutbox",
    "LocalCredential",
    "LoginAttempt",
    "NumberSeries",
    "Role",
    "RolePermission",
    "Setting",
    "StoredFile",
    "UserBranchRole",
    "UserSession",
]
