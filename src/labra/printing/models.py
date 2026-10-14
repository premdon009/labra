"""Letterhead layouts (design §7.2).

A branch has at most one draft per document kind, edited freely. Publishing copies the draft
into a new numbered version, which the database then refuses to change or delete, so a
released report or an issued bill always reprints on the layout it was made with.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from labra.core.db import Base, TrackedMixin

DOC_KINDS = ("report_a4", "bill_a4")
LAYOUT_STATUSES = ("draft", "published")
FILE_TYPES = ("svg", "pdf", "raster")
APPLY_ON = ("all", "first")


class LetterheadLayout(TrackedMixin, Base):
    """The letterhead file and the content box for one branch and document kind. A layout
    without a file prints the built-in header inside the same margins."""

    __tablename__ = "letterhead_layout"
    __table_args__ = (
        CheckConstraint("doc_kind in ('report_a4', 'bill_a4')", name="doc_kind"),
        CheckConstraint("status in ('draft', 'published')", name="status"),
        CheckConstraint(
            "(status = 'published') = (version is not null and published_at is not null"
            " and published_by is not null)",
            name="published",
        ),
        CheckConstraint(
            "file_type is null or file_type in ('svg', 'pdf', 'raster')", name="file_type"
        ),
        CheckConstraint(
            "(file_type is null) = (letterhead_file_id is null)"
            " and (file_type is null) = (original_file_id is null)",
            name="file",
        ),
        CheckConstraint(
            "converted_from in ('none', 'pdf', 'raster_traced')", name="converted_from"
        ),
        CheckConstraint("apply_on in ('all', 'first')", name="apply_on"),
        CheckConstraint(
            "margin_top_mm between 0 and 120 and margin_bottom_mm between 0 and 120"
            " and margin_left_mm between 0 and 60 and margin_right_mm between 0 and 60",
            name="margins",
        ),
        CheckConstraint("signature_area_mm between 0 and 80", name="signature_area"),
        CheckConstraint("font_size_pt between 7 and 14", name="font_size"),
        Index(
            "uq_letterhead_layout_draft",
            "branch_id",
            "doc_kind",
            unique=True,
            postgresql_where=text("status = 'draft'"),
        ),
        Index("uq_letterhead_layout_version", "branch_id", "doc_kind", "version", unique=True),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("branch.id"))
    doc_kind: Mapped[str] = mapped_column(String(10))
    version: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(10), default="draft")
    published_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id"))
    published_at: Mapped[datetime | None]
    original_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stored_file.id"))
    # The optimised file actually drawn: sanitised SVG, the vector PDF, or a re-encoded image.
    letterhead_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stored_file.id"))
    file_type: Mapped[str | None] = mapped_column(String(6))
    raster_dpi: Mapped[int | None] = mapped_column(SmallInteger)
    original_bytes: Mapped[int] = mapped_column(default=0)
    optimised_bytes: Mapped[int] = mapped_column(default=0)
    converted_from: Mapped[str] = mapped_column(String(14), default="none")
    apply_on: Mapped[str] = mapped_column(String(5), default="all")
    margin_top_mm: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal(40))
    margin_bottom_mm: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal(25))
    margin_left_mm: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal(15))
    margin_right_mm: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal(15))
    # Kept clear above the bottom margin on the last page for the signatory block.
    signature_area_mm: Mapped[Decimal] = mapped_column(Numeric(5, 1), default=Decimal(30))
    font_size_pt: Mapped[Decimal] = mapped_column(Numeric(4, 1), default=Decimal(10))
