"""Front desk: patients, referrers, visits, orders, samples, bills, payments and refunds.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Lines, payments and refunds are never changed once written (refuse_change() comes from
# 0003). An issued bill may only take payments, move to paid, or be cancelled; once
# cancelled it is final.
MONEY_GUARD = """
CREATE TRIGGER bill_line_no_change BEFORE UPDATE OR DELETE ON bill_line
    FOR EACH ROW EXECUTE FUNCTION refuse_change();
CREATE TRIGGER bill_line_no_truncate BEFORE TRUNCATE ON bill_line
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_change();
CREATE TRIGGER payment_no_change BEFORE UPDATE OR DELETE ON payment
    FOR EACH ROW EXECUTE FUNCTION refuse_change();
CREATE TRIGGER payment_no_truncate BEFORE TRUNCATE ON payment
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_change();
CREATE TRIGGER refund_no_change BEFORE UPDATE OR DELETE ON refund
    FOR EACH ROW EXECUTE FUNCTION refuse_change();
CREATE TRIGGER refund_no_truncate BEFORE TRUNCATE ON refund
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_change();
CREATE TRIGGER bill_no_delete BEFORE DELETE ON bill
    FOR EACH ROW EXECUTE FUNCTION refuse_change();
CREATE TRIGGER bill_no_truncate BEFORE TRUNCATE ON bill
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_change();

CREATE FUNCTION bill_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'cancelled' THEN
        RAISE EXCEPTION 'bill % is cancelled and is final', OLD.bill_no
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF (NEW.bill_no, NEW.fin_year, NEW.doc_type, NEW.branch_id, NEW.visit_id, NEW.bill_date,
        NEW.issued_at, NEW.recipient_name, NEW.gross, NEW.discount, NEW.discount_reason,
        NEW.round_off, NEW.round_off_unit, NEW.net, NEW.place_of_supply_state,
        NEW.print_snapshot, NEW.extra, NEW.client_ref)
       IS DISTINCT FROM
       (OLD.bill_no, OLD.fin_year, OLD.doc_type, OLD.branch_id, OLD.visit_id, OLD.bill_date,
        OLD.issued_at, OLD.recipient_name, OLD.gross, OLD.discount, OLD.discount_reason,
        OLD.round_off, OLD.round_off_unit, OLD.net, OLD.place_of_supply_state,
        OLD.print_snapshot, OLD.extra, OLD.client_ref) THEN
        RAISE EXCEPTION 'bill % is issued: its figures can''t change', OLD.bill_no
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.paid < OLD.paid THEN
        RAISE EXCEPTION 'bill % can''t have less paid than before', OLD.bill_no
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER bill_issued_guard BEFORE UPDATE ON bill
    FOR EACH ROW EXECUTE FUNCTION bill_guard();
"""


def upgrade() -> None:
    op.create_table(
        "referrer",
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("qualification", sa.String(length=80), nullable=False),
        sa.Column("council_reg_no", sa.String(length=40), nullable=False),
        sa.Column("phone", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "kind in ('doctor', 'clinic', 'hospital', 'corporate', 'self')",
            name=op.f("ck_referrer_kind"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_referrer")),
    )
    op.create_index(
        "ix_referrer_name_trgm",
        "referrer",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_table(
        "patient",
        sa.Column("patient_no", sa.String(length=30), nullable=False),
        sa.Column("registered_branch_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=10), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("sex", sa.String(length=1), nullable=False),
        sa.Column("dob", sa.Date(), nullable=False),
        sa.Column("dob_is_estimated", sa.Boolean(), nullable=False),
        sa.Column("phone", sa.String(length=10), nullable=False),
        sa.Column("alt_phone", sa.String(length=10), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("city", sa.String(length=60), nullable=False),
        sa.Column("pincode", sa.String(length=6), nullable=False),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "alt_phone ~ '^[0-9]{10}$' or alt_phone = ''", name=op.f("ck_patient_alt_phone")
        ),
        sa.CheckConstraint("phone ~ '^[0-9]{10}$' or phone = ''", name=op.f("ck_patient_phone")),
        sa.CheckConstraint(
            "pincode ~ '^[0-9]{6}$' or pincode = ''", name=op.f("ck_patient_pincode")
        ),
        sa.CheckConstraint("sex in ('M', 'F', 'O')", name=op.f("ck_patient_sex")),
        sa.CheckConstraint("length(btrim(full_name)) > 0", name=op.f("ck_patient_full_name")),
        sa.ForeignKeyConstraint(
            ["registered_branch_id"],
            ["branch.id"],
            name=op.f("fk_patient_registered_branch_id_branch"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_patient")),
        sa.UniqueConstraint("patient_no", name=op.f("uq_patient_patient_no")),
    )
    op.create_index(
        "ix_patient_branch_created", "patient", ["registered_branch_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_patient_full_name_trgm",
        "patient",
        ["full_name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.create_index(op.f("ix_patient_phone"), "patient", ["phone"], unique=False)
    op.create_table(
        "visit",
        sa.Column("visit_no", sa.String(length=30), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("referrer_id", sa.Uuid(), nullable=True),
        sa.Column("visited_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collection_mode", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("promised_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("footer_note", sa.String(length=200), nullable=False),
        sa.Column("internal_note", sa.Text(), nullable=False),
        sa.Column("manual_receipt_ref", sa.String(length=30), nullable=False),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("origin_device_id", sa.String(length=40), nullable=True),
        sa.Column("client_ref", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "collection_mode in ('walk_in', 'home')", name=op.f("ck_visit_collection_mode")
        ),
        sa.CheckConstraint(
            "status in ('open', 'completed', 'cancelled')", name=op.f("ck_visit_status")
        ),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_visit_branch_id_branch")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patient.id"], name=op.f("fk_visit_patient_id_patient")
        ),
        sa.ForeignKeyConstraint(
            ["referrer_id"], ["referrer.id"], name=op.f("fk_visit_referrer_id_referrer")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_visit")),
        sa.UniqueConstraint("client_ref", name=op.f("uq_visit_client_ref")),
        sa.UniqueConstraint("visit_no", name=op.f("uq_visit_visit_no")),
    )
    op.create_index(
        "ix_visit_branch_visited",
        "visit",
        ["branch_id", sa.literal_column("visited_at DESC")],
        unique=False,
    )
    op.create_index(op.f("ix_visit_patient_id"), "visit", ["patient_id"], unique=False)
    op.create_table(
        "bill",
        sa.Column("bill_no", sa.String(length=16), nullable=False),
        sa.Column("fin_year", sa.SmallInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=16), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("recipient_name", sa.String(length=120), nullable=False),
        sa.Column("bill_date", sa.Date(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("place_of_supply_state", sa.String(length=2), nullable=False),
        sa.Column("gross", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount_reason", sa.String(length=120), nullable=False),
        sa.Column("round_off", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("round_off_unit", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("net", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("paid", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column(
            "due",
            sa.Numeric(precision=12, scale=2),
            sa.Computed("net - paid", persisted=True),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("cancel_reason", sa.String(length=200), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by", sa.Uuid(), nullable=True),
        sa.Column("print_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "extra",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("origin_device_id", sa.String(length=40), nullable=True),
        sa.Column("client_ref", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "doc_type in ('bill_of_supply', 'tax_invoice')", name=op.f("ck_bill_doc_type")
        ),
        sa.CheckConstraint(
            "length(bill_no) <= 16 and bill_no ~ '^[A-Za-z0-9/-]+$'", name=op.f("ck_bill_bill_no")
        ),
        sa.CheckConstraint(
            "status <> 'cancelled' or (length(cancel_reason) > 0 and cancelled_at is not null)",
            name=op.f("ck_bill_cancelled"),
        ),
        sa.CheckConstraint("status <> 'open' or paid < net", name=op.f("ck_bill_open_status")),
        sa.CheckConstraint("status <> 'paid' or paid = net", name=op.f("ck_bill_paid_status")),
        sa.CheckConstraint("status in ('open', 'paid', 'cancelled')", name=op.f("ck_bill_status")),
        sa.CheckConstraint(
            "abs(round_off) <= coalesce(round_off_unit, 0) / 2", name=op.f("ck_bill_round_off")
        ),
        sa.CheckConstraint(
            "discount = 0 or length(discount_reason) > 0", name=op.f("ck_bill_discount_reason")
        ),
        sa.CheckConstraint("discount >= 0 and discount <= gross", name=op.f("ck_bill_discount")),
        sa.CheckConstraint("gross >= 0", name=op.f("ck_bill_gross")),
        sa.CheckConstraint("net = gross - discount + round_off", name=op.f("ck_bill_net")),
        sa.CheckConstraint("net >= 0", name=op.f("ck_bill_net_not_negative")),
        sa.CheckConstraint("paid >= 0 and paid <= net", name=op.f("ck_bill_paid")),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_bill_branch_id_branch")
        ),
        sa.ForeignKeyConstraint(
            ["cancelled_by"], ["app_user.id"], name=op.f("fk_bill_cancelled_by_app_user")
        ),
        sa.ForeignKeyConstraint(["visit_id"], ["visit.id"], name=op.f("fk_bill_visit_id_visit")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bill")),
        sa.UniqueConstraint("client_ref", name=op.f("uq_bill_client_ref")),
        sa.UniqueConstraint("fin_year", "bill_no", name=op.f("uq_bill_fin_year_bill_no")),
    )
    op.create_index("ix_bill_branch_date", "bill", ["branch_id", "bill_date"], unique=False)
    op.create_index(
        "ix_bill_branch_date_open",
        "bill",
        ["branch_id", "bill_date"],
        unique=False,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "uq_bill_visit_doc_type",
        "bill",
        ["visit_id", "doc_type"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.create_table(
        "order_item",
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("item_type", sa.String(length=12), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=True),
        sa.Column("package_id", sa.Uuid(), nullable=True),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("price_id", sa.Uuid(), nullable=True),
        sa.Column("list_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount_amt", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("net_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("cancel_reason", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "(item_type = 'test' and test_id is not null and package_id is null)"
            " or (item_type = 'package' and package_id is not null and test_id is null)"
            " or (item_type = 'extra_charge' and test_id is null and package_id is null)",
            name=op.f("ck_order_item_item_ref"),
        ),
        sa.CheckConstraint(
            "item_type <> 'extra_charge' or length(reason) > 0",
            name=op.f("ck_order_item_extra_charge_reason"),
        ),
        sa.CheckConstraint(
            "item_type in ('test', 'package', 'extra_charge')", name=op.f("ck_order_item_item_type")
        ),
        sa.CheckConstraint("status in ('active', 'cancelled')", name=op.f("ck_order_item_status")),
        sa.CheckConstraint(
            "discount_amt >= 0 and discount_amt <= list_price",
            name=op.f("ck_order_item_discount_amt"),
        ),
        sa.CheckConstraint("list_price >= 0", name=op.f("ck_order_item_list_price")),
        sa.CheckConstraint(
            "net_price = list_price - discount_amt", name=op.f("ck_order_item_net_price")
        ),
        sa.ForeignKeyConstraint(
            ["package_id"], ["package.id"], name=op.f("fk_order_item_package_id_package")
        ),
        sa.ForeignKeyConstraint(
            ["price_id"], ["price.id"], name=op.f("fk_order_item_price_id_price")
        ),
        sa.ForeignKeyConstraint(["test_id"], ["test.id"], name=op.f("fk_order_item_test_id_test")),
        sa.ForeignKeyConstraint(
            ["visit_id"], ["visit.id"], name=op.f("fk_order_item_visit_id_visit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_item")),
    )
    op.create_index(op.f("ix_order_item_visit_id"), "order_item", ["visit_id"], unique=False)
    op.create_table(
        "sample",
        sa.Column("sample_no", sa.String(length=20), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("specimen_type_id", sa.Uuid(), nullable=True),
        sa.Column("container", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'cancelled') or collected_at is not null",
            name=op.f("ck_sample_collected"),
        ),
        sa.CheckConstraint(
            "status in ('pending', 'collected', 'received', 'rejected', 'redraw', 'cancelled')",
            name=op.f("ck_sample_status"),
        ),
        sa.ForeignKeyConstraint(
            ["collected_by"], ["app_user.id"], name=op.f("fk_sample_collected_by_app_user")
        ),
        sa.ForeignKeyConstraint(
            ["specimen_type_id"],
            ["specimen_type.id"],
            name=op.f("fk_sample_specimen_type_id_specimen_type"),
        ),
        sa.ForeignKeyConstraint(["visit_id"], ["visit.id"], name=op.f("fk_sample_visit_id_visit")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sample")),
        sa.UniqueConstraint("sample_no", name=op.f("uq_sample_sample_no")),
    )
    op.create_index(op.f("ix_sample_visit_id"), "sample", ["visit_id"], unique=False)
    op.create_table(
        "bill_line",
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("line_no", sa.SmallInteger(), nullable=False),
        sa.Column("description", sa.String(length=120), nullable=False),
        sa.Column("sac_code", sa.String(length=8), nullable=False),
        sa.Column("rate", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("price_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("amount = rate - discount", name=op.f("ck_bill_line_amount")),
        sa.CheckConstraint(
            "discount >= 0 and discount <= rate", name=op.f("ck_bill_line_discount")
        ),
        sa.CheckConstraint("rate >= 0", name=op.f("ck_bill_line_rate")),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"], name=op.f("fk_bill_line_bill_id_bill")),
        sa.ForeignKeyConstraint(
            ["order_item_id"], ["order_item.id"], name=op.f("fk_bill_line_order_item_id_order_item")
        ),
        sa.ForeignKeyConstraint(
            ["price_id"], ["price.id"], name=op.f("fk_bill_line_price_id_price")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bill_line")),
        sa.UniqueConstraint("bill_id", "line_no", name=op.f("uq_bill_line_bill_id_line_no")),
    )
    op.create_table(
        "order_test",
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("order_item_id", sa.Uuid(), nullable=False),
        sa.Column("test_id", sa.Uuid(), nullable=False),
        sa.Column("sample_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status in ('ordered', 'collected', 'in_lab', 'sent_out', 'resulted', 'verified',"
            " 'released', 'cancelled')",
            name=op.f("ck_order_test_status"),
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id"],
            ["order_item.id"],
            name=op.f("fk_order_test_order_item_id_order_item"),
        ),
        sa.ForeignKeyConstraint(
            ["sample_id"], ["sample.id"], name=op.f("fk_order_test_sample_id_sample")
        ),
        sa.ForeignKeyConstraint(["test_id"], ["test.id"], name=op.f("fk_order_test_test_id_test")),
        sa.ForeignKeyConstraint(
            ["visit_id"], ["visit.id"], name=op.f("fk_order_test_visit_id_visit")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_order_test")),
    )
    op.create_index(
        op.f("ix_order_test_order_item_id"), "order_test", ["order_item_id"], unique=False
    )
    op.create_index(op.f("ix_order_test_sample_id"), "order_test", ["sample_id"], unique=False)
    op.create_index(
        "uq_order_test_visit_test",
        "order_test",
        ["visit_id", "test_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.create_table(
        "payment",
        sa.Column("receipt_no", sa.String(length=30), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("received_by", sa.Uuid(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin_device_id", sa.String(length=40), nullable=True),
        sa.Column("client_ref", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("mode in ('cash', 'upi', 'card')", name=op.f("ck_payment_mode")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payment_amount")),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"], name=op.f("fk_payment_bill_id_bill")),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_payment_branch_id_branch")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patient.id"], name=op.f("fk_payment_patient_id_patient")
        ),
        sa.ForeignKeyConstraint(
            ["received_by"], ["app_user.id"], name=op.f("fk_payment_received_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment")),
        sa.UniqueConstraint("client_ref", name=op.f("uq_payment_client_ref")),
        sa.UniqueConstraint("receipt_no", name=op.f("uq_payment_receipt_no")),
    )
    op.create_index(op.f("ix_payment_bill_id"), "payment", ["bill_id"], unique=False)
    op.create_table(
        "refund",
        sa.Column("refund_no", sa.String(length=30), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("bill_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("reference", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("refunded_by", sa.Uuid(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_ref", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("mode in ('cash', 'upi', 'card')", name=op.f("ck_refund_mode")),
        sa.CheckConstraint("amount > 0", name=op.f("ck_refund_amount")),
        sa.CheckConstraint("length(reason) > 0", name=op.f("ck_refund_reason")),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"], name=op.f("fk_refund_bill_id_bill")),
        sa.ForeignKeyConstraint(
            ["branch_id"], ["branch.id"], name=op.f("fk_refund_branch_id_branch")
        ),
        sa.ForeignKeyConstraint(
            ["refunded_by"], ["app_user.id"], name=op.f("fk_refund_refunded_by_app_user")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refund")),
        sa.UniqueConstraint("bill_id", name=op.f("uq_refund_bill_id")),
        sa.UniqueConstraint("client_ref", name=op.f("uq_refund_client_ref")),
        sa.UniqueConstraint("refund_no", name=op.f("uq_refund_refund_no")),
    )
    op.execute(MONEY_GUARD)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS bill_guard() CASCADE")
    for table in ("bill_line", "payment", "refund"):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_change ON {table}")
        op.execute(f"DROP TRIGGER IF EXISTS {table}_no_truncate ON {table}")
    op.execute("DROP TRIGGER IF EXISTS bill_no_delete ON bill")
    op.execute("DROP TRIGGER IF EXISTS bill_no_truncate ON bill")
    op.drop_table("refund")
    op.drop_index(op.f("ix_payment_bill_id"), table_name="payment")
    op.drop_table("payment")
    op.drop_index(
        "uq_order_test_visit_test",
        table_name="order_test",
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.drop_index(op.f("ix_order_test_sample_id"), table_name="order_test")
    op.drop_index(op.f("ix_order_test_order_item_id"), table_name="order_test")
    op.drop_table("order_test")
    op.drop_table("bill_line")
    op.drop_index(op.f("ix_sample_visit_id"), table_name="sample")
    op.drop_table("sample")
    op.drop_index(op.f("ix_order_item_visit_id"), table_name="order_item")
    op.drop_table("order_item")
    op.drop_index(
        "uq_bill_visit_doc_type",
        table_name="bill",
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.drop_index(
        "ix_bill_branch_date_open", table_name="bill", postgresql_where=sa.text("status = 'open'")
    )
    op.drop_index("ix_bill_branch_date", table_name="bill")
    op.drop_table("bill")
    op.drop_index(op.f("ix_visit_patient_id"), table_name="visit")
    op.drop_index("ix_visit_branch_visited", table_name="visit")
    op.drop_table("visit")
    op.drop_index(op.f("ix_patient_phone"), table_name="patient")
    op.drop_index(
        "ix_patient_full_name_trgm",
        table_name="patient",
        postgresql_using="gin",
        postgresql_ops={"full_name": "gin_trgm_ops"},
    )
    op.drop_index("ix_patient_branch_created", table_name="patient")
    op.drop_table("patient")
    op.drop_index(
        "ix_referrer_name_trgm",
        table_name="referrer",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_table("referrer")
