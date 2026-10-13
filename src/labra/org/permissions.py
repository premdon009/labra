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
        Permission("catalog.view", "See the test catalog and prices", "lab"),
        Permission("catalog.edit", "Change tests, parameters, ranges and packages", "lab"),
        Permission("price.edit", "Change prices", "lab"),
        Permission("range.approve", "Approve reference ranges", "lab"),
        Permission("patient.view", "Find patients", "branch"),
        Permission("patient.edit", "Register patients and change their details", "branch"),
        Permission("referrer.view", "See referring doctors", "lab"),
        Permission("referrer.edit", "Add and change referring doctors", "lab"),
        Permission("visit.create", "Book visits", "branch"),
        Permission("visit.view", "See visits", "branch"),
        Permission("bill.view", "See bills and receipts", "branch"),
        Permission("payment.take", "Take payments", "branch"),
        Permission("bill.cancel", "Cancel bills", "branch"),
    ]
}


@dataclass(frozen=True)
class SystemRole:
    code: str
    name: str
    permissions: frozenset[str]


_EVERY_BRANCH_ROLE = frozenset({"branch.view", "catalog.view"})
_FRONT_DESK = frozenset(
    {
        "patient.view",
        "patient.edit",
        "referrer.view",
        "referrer.edit",
        "visit.create",
        "visit.view",
        "bill.view",
        "payment.take",
    }
)
# Approving a range is a clinical sign-off (ISO 15189), so it belongs to the signatory alone.
_CLINICAL = frozenset({"range.approve"})

SYSTEM_ROLES: dict[str, SystemRole] = {
    r.code: r
    for r in [
        SystemRole("admin", "Administrator", frozenset(PERMISSIONS) - _CLINICAL),
        SystemRole(
            "branch_manager",
            "Branch manager",
            _EVERY_BRANCH_ROLE
            | _FRONT_DESK
            | {"setting.view", "setting.edit_branch", "bill.cancel"},
        ),
        SystemRole("front_desk", "Front desk", _EVERY_BRANCH_ROLE | _FRONT_DESK),
        SystemRole("phlebotomist", "Phlebotomist", _EVERY_BRANCH_ROLE),
        SystemRole("technician", "Technician", _EVERY_BRANCH_ROLE),
        SystemRole("signatory", "Signatory", _EVERY_BRANCH_ROLE | _CLINICAL),
    ]
}
