import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, TrackedMixin

BRANCH_KINDS = ("main_lab", "collection_centre")


class Branch(TrackedMixin, Base):
    __tablename__ = "branch"

    code: Mapped[str] = mapped_column(String(4), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))
    address: Mapped[str] = mapped_column(Text, default="")
    state_code: Mapped[str] = mapped_column(String(2), default="")
    phone: Mapped[str] = mapped_column(String(15), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    gstin: Mapped[str] = mapped_column(String(15), default="")
    is_active: Mapped[bool] = mapped_column(default=True)


class AppUser(TrackedMixin, Base):
    """A member of staff. `can_login=false` is for staff who appear on records (a
    phlebotomist, a signatory) but never sign in."""

    __tablename__ = "app_user"

    username: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(15), default="")
    email: Mapped[str] = mapped_column(String(120), default="")
    can_login: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    last_login_at: Mapped[datetime | None]


class Role(TrackedMixin, Base):
    __tablename__ = "role"

    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    is_system: Mapped[bool] = mapped_column(default=False)


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(String(60), primary_key=True)


class UserBranchRole(Base):
    __tablename__ = "user_branch_role"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("role.id"), primary_key=True)
