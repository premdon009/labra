"""The exports (design §17.2): the daily accounting file shows the owner's daily figures,
and the full export writes every table with its schema, leaving the sign-in secrets out.
Both are for administrators only, written under LABRA_EXPORT_DIR, and audited."""

import csv
import json
import stat
from pathlib import Path

import duckdb
import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from labra.billing.models import PAYMENT_MODES
from labra.cli import build_parser, main
from labra.core.config import get_settings
from labra.core.errors import ConfigError, PermissionDeniedError
from labra.core.ids import lab_today
from labra.core.models import AuditLog
from labra.core.registry import Platform
from labra.exports import accounting, full
from labra.exports.common import APP_DIR, acting_admin, export_root
from labra.owner import service as owner
from tests.frontdesk import as_user, branch
from tests.test_db_owner import _day


def _private(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def _audited(db: Session, action: str) -> AuditLog:
    return db.scalars(select(AuditLog).where(AuditLog.action == action)).one()


@pytest.mark.item("M26")
def test_the_accounting_export_shows_the_daily_figures(
    seeded: Session, platform: Platform, tmp_path: Path
) -> None:
    db = seeded
    _day(db, platform)
    anil = acting_admin(db, "anil")
    today = lab_today()

    path = accounting.export(db, anil, today, tmp_path, "json")
    data = json.loads(path.read_text(encoding="utf-8"))
    d = owner.daily(db, as_user(db, platform, "anil"), today)
    total = data["total"]
    assert total["collection"] == {
        **{m: str(d.total.modes[m]) for m in PAYMENT_MODES},
        "refunds": str(d.total.refunds),
        "net": str(d.total.net),
    }
    assert total["bills"] == {
        "count": d.bills,
        "gross": str(d.gross),
        "discount": str(d.discount),
        "net": str(d.net),
    }
    assert total["cancelled"] == {"count": 1, "net": "180.00"}
    assert total["dues"] == {"bills": 1, "amount": "1300.00"}
    assert total["outsourcing"] == {
        "tests": 1,
        "cost": "700.00",
        "revenue": "1300.00",
        "margin": "600.00",
    }
    by_code = {b["branch_code"]: b for b in data["branches"]}
    assert by_code["B2"]["collection"]["net"] == "450.00"
    assert by_code["B3"]["collection"]["net"] == "80.00"
    assert path.name == f"accounting-{today.isoformat()}-ALL.json" and _private(path)

    sheet = accounting.export(db, anil, today, tmp_path, "csv")
    rows = list(csv.DictReader(sheet.read_text(encoding="utf-8-sig").splitlines()))
    assert [r["branch_code"] for r in rows[:-1]] == [b["branch_code"] for b in data["branches"]]
    assert set(by_code) == {"MAIN", "B2", "B3"} and rows[-1]["branch"] == "All branches"
    assert rows[-1]["collected_net"] == str(d.total.net) and rows[-1]["dues"] == "1300.00"

    one = accounting.export(db, anil, today, tmp_path, "csv", branch(db, "B3").id)
    rows = list(csv.DictReader(one.read_text(encoding="utf-8-sig").splitlines()))
    assert one.name.endswith("-B3.csv")
    assert [(r["branch_code"], r["cash"], r["bills"]) for r in rows] == [("B3", "80.00", "1")]

    logged = db.scalars(
        select(AuditLog).where(AuditLog.action == "export.accounting").order_by(AuditLog.id)
    ).all()
    assert [a.detail["format"] for a in logged] == ["json", "csv", "csv"]
    assert logged[-1].user_id == anil.user_id
    assert logged[-1].detail["branch_id"] == str(branch(db, "B3").id)


@pytest.mark.item("M26")
def test_the_full_export_has_every_table_and_its_schema(
    seeded: Session, platform: Platform, tmp_path: Path
) -> None:
    db = seeded
    _day(db, platform)
    anil = acting_admin(db, "anil")
    counts = {t.name: db.scalar(select(func.count()).select_from(t)) or 0 for t in full.tables()}

    done = full.export(db, anil, tmp_path, "both")

    assert done.tables == len(counts) and done.rows == sum(counts.values())
    assert {"local_credential", "user_session"}.isdisjoint(counts)
    assert {"patient", "bill", "payment", "audit_log", "report"} <= set(counts)
    con = duckdb.connect(":memory:")
    for name, count in counts.items():
        with (done.folder / "csv" / f"{name}.csv").open(encoding="utf-8", newline="") as f:
            assert sum(1 for _ in csv.reader(f)) == count + 1, name
        parquet = done.folder / "parquet" / f"{name}.parquet"
        assert con.execute("SELECT count(*) FROM read_parquet(?)", [str(parquet)]).fetchone() == (
            count,
        ), name
        assert _private(parquet)
    assert sorted(p.name for p in (done.folder / "csv").iterdir()) == sorted(
        f"{name}.csv" for name in counts
    )
    assert not list(done.folder.rglob("*.part")) and not list(done.folder.rglob("*.jsonl"))
    assert _private(done.folder)

    # Typed columns: amounts stay exact, times keep their zone, lists and JSON survive.
    payment = str(done.folder / "parquet" / "payment.parquet")
    types = dict(
        con.execute(
            "SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_parquet(?))",
            [payment],
        ).fetchall()
    )
    assert types["amount"] == "DECIMAL(12,2)" and types["received_at"] == "TIMESTAMP WITH TIME ZONE"
    assert types["id"] == "UUID"
    total = con.execute("SELECT sum(amount)::VARCHAR FROM read_parquet(?)", [payment]).fetchone()
    assert total == (str(db.scalar(select(func.sum(full.models.Payment.amount)))),)
    aliases = con.execute(
        "SELECT typeof(aliases) FROM read_parquet(?) LIMIT 1",
        [str(done.folder / "parquet" / "test.parquet")],
    ).fetchone()
    assert aliases == ("VARCHAR[]",)
    snapshot = con.execute(
        "SELECT print_snapshot FROM read_parquet(?) LIMIT 1",
        [str(done.folder / "parquet" / "bill.parquet")],
    ).fetchone()
    assert snapshot is not None and "supplier" in json.loads(snapshot[0])

    schema = (done.folder / "schema.md").read_text(encoding="utf-8")
    for name in counts:
        assert f"\n## {name}\n" in schema
    assert "| visit_id | uuid | no | visit.id |" in schema
    assert "`local_credential` (password hashes)" in schema

    logged = _audited(db, "export.all")
    assert logged.user_id == anil.user_id
    assert logged.detail == {
        "format": "both",
        "folder": done.folder.name,
        "tables": len(counts),
        "rows": sum(counts.values()),
    }

    only_csv = full.export(db, anil, tmp_path / "csv-only", "csv")
    assert not (only_csv.folder / "parquet").exists() and (only_csv.folder / "csv").is_dir()


@pytest.mark.item("M26")
def test_only_an_administrator_exports(seeded: Session) -> None:
    for username in ("priya", "b3desk", "meera", "nobody"):
        with pytest.raises(PermissionDeniedError):
            acting_admin(seeded, username)
    assert acting_admin(seeded, "anil").username == "anil"


@pytest.mark.item("M26")
def test_the_export_folder_must_be_set_absolute_and_outside_the_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LABRA_EXPORT_DIR", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigError, match="Set LABRA_EXPORT_DIR"):
            export_root()
    finally:
        get_settings.cache_clear()
    with pytest.raises(ConfigError, match="absolute"):
        export_root(Path("exports"))
    for inside in (APP_DIR, APP_DIR / "static" / "exports", APP_DIR.parent):
        with pytest.raises(ConfigError, match="outside"):
            export_root(inside)
    made = export_root(tmp_path / "exports")
    assert made.is_dir() and _private(made)


@pytest.mark.item("M26")
def test_the_export_commands(
    pg_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = build_parser().parse_args(
        ["export", "accounting", "--date", "2026-10-14", "--branch", "b3", "--as", "anil"]
    )
    assert (str(args.date), args.branch, args.format) == ("2026-10-14", "b3", "csv")
    args = build_parser().parse_args(["export", "all", "--as", "anil"])
    assert args.format == "both"
    with pytest.raises(SystemExit):
        build_parser().parse_args(["export", "accounting", "--date", "14/10/2026", "--as", "a"])

    # Without LABRA_EXPORT_DIR nothing is written: a configuration error.
    monkeypatch.delenv("LABRA_EXPORT_DIR", raising=False)
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as stopped:
        main(["export", "all", "--as", "anil"])
    assert stopped.value.code == 2

    # With it, the command still refuses anyone who is not an administrator.
    monkeypatch.setenv("LABRA_EXPORT_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()
    monkeypatch.setattr("labra.core.db.get_engine", lambda: pg_engine)
    try:
        with pytest.raises(SystemExit) as stopped:
            main(["export", "all", "--as", "nobody"])
    finally:
        get_settings.cache_clear()
    assert stopped.value.code == 1
    assert not list((tmp_path / "exports").iterdir())
