"""The permission catalogue and the roles every install starts with (design §5.1).

A permission with scope "branch" applies only in the branches where the user holds a role
granting it. A "lab" permission applies everywhere once any of the user's roles grants it.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Permission:
    code: str
    label: str
    scope: Literal["branch", "lab"]


PERMISSIONS: dict[str, Permission] = {
    p.code: p
    for p in [
        Permission("branch.view", "See branch details", "branch"),
        Permission("branch.edit", "Add and change branches", "lab"),
        Permission("user.view", "See staff and their roles", "lab"),
        Permission("user.edit", "Add staff, change roles, reset passwords", "lab"),
        Permission("setting.view", "See settings", "branch"),
        Permission("setting.edit", "Change lab-wide settings", "lab"),
        Permission("setting.edit_branch", "Change a branch's own settings", "branch"),
        Permission("audit.view", "See the audit log", "lab"),
    ]
}


@dataclass(frozen=True)
class SystemRole:
    code: str
    name: str
    permissions: frozenset[str]


_EVERY_BRANCH_ROLE = frozenset({"branch.view"})

SYSTEM_ROLES: dict[str, SystemRole] = {
    r.code: r
    for r in [
        SystemRole("admin", "Administrator", frozenset(PERMISSIONS)),
        SystemRole(
            "branch_manager",
            "Branch manager",
            _EVERY_BRANCH_ROLE | {"setting.view", "setting.edit_branch"},
        ),
        SystemRole("front_desk", "Front desk", _EVERY_BRANCH_ROLE),
        SystemRole("phlebotomist", "Phlebotomist", _EVERY_BRANCH_ROLE),
        SystemRole("technician", "Technician", _EVERY_BRANCH_ROLE),
        SystemRole("signatory", "Signatory", _EVERY_BRANCH_ROLE),
    ]
}
