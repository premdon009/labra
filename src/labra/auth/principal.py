"""Who is acting, and what they may do where. Decided here, never by an identity provider."""

import uuid
from dataclasses import dataclass, field

from labra.org.permissions import PERMISSIONS


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    username: str
    full_name: str
    # The branch the user is working at; branch-scoped checks default to it.
    branch_id: uuid.UUID | None
    grants: dict[uuid.UUID, frozenset[str]] = field(default_factory=dict)
    # "B2 · Branch 2" labels for the branches in `grants`, for the branch switcher.
    branch_labels: dict[uuid.UUID, str] = field(default_factory=dict)

    def can(self, permission: str, branch_id: uuid.UUID | None = None) -> bool:
        """Deny by default: unknown permissions, and branches without a grant, are refused."""
        p = PERMISSIONS.get(permission)
        if p is None:
            return False
        if p.scope == "lab":
            return any(permission in perms for perms in self.grants.values())
        target = branch_id or self.branch_id
        return target is not None and permission in self.grants.get(target, frozenset())

    def branches_with(self, permission: str) -> set[uuid.UUID]:
        p = PERMISSIONS.get(permission)
        if p is None:
            return set()
        held = {b for b, perms in self.grants.items() if permission in perms}
        if p.scope == "lab" and held:
            return set(self.grants)
        return held
