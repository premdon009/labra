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
        Permission("sample.collect", "Mark samples as collected", "branch"),
        Permission("sample.receive", "Scan samples in at the lab", "branch"),
        Permission("result.enter", "See the lab worklist and enter results", "branch"),
        Permission("result.verify", "Verify results", "branch"),
        Permission("test.route", "Send a test to an external lab or keep it in house", "branch"),
        Permission("extlab.view", "See external labs and their rates", "lab"),
        Permission("extlab.edit", "Add and change external labs and their rates", "lab"),
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
        "sample.collect",
    }
)
# Approving a range and verifying a result are clinical sign-offs (ISO 15189), so they
# belong to the signatory alone.
_CLINICAL = frozenset({"range.approve", "result.verify"})
# Work done at the bench. The administrator sets the lab up but doesn't do it.
_BENCH = frozenset({"result.enter", "sample.receive"})
_EXTERNAL_LABS = frozenset({"test.route", "extlab.view"})

SYSTEM_ROLES: dict[str, SystemRole] = {
    r.code: r
    for r in [
        SystemRole("admin", "Administrator", frozenset(PERMISSIONS) - _CLINICAL - _BENCH),
        SystemRole(
            "branch_manager",
            "Branch manager",
            _EVERY_BRANCH_ROLE
            | _FRONT_DESK
            | _EXTERNAL_LABS
            | {"setting.view", "setting.edit_branch", "bill.cancel"},
        ),
        SystemRole("front_desk", "Front desk", _EVERY_BRANCH_ROLE | _FRONT_DESK),
        SystemRole(
            "phlebotomist",
            "Phlebotomist",
            _EVERY_BRANCH_ROLE | {"sample.collect", "sample.receive"},
        ),
        SystemRole("technician", "Technician", _EVERY_BRANCH_ROLE | _BENCH | _EXTERNAL_LABS),
        SystemRole("signatory", "Signatory", _EVERY_BRANCH_ROLE | _CLINICAL | {"result.enter"}),
    ]
}
