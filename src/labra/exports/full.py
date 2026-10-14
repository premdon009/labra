"""The full data export (`labra export all`): every table, as CSV and Parquet, with a
generated `schema.md`, so the lab can take its data to any other system, not only Labra.

Each table is read in primary-key order in one transaction (the command opens it as
REPEATABLE READ, so all the tables show the same moment). Parquet is written by DuckDB from
a temporary file of JSON lines with the column types spelled out; DuckDB loads no extension
and never touches the network.
"""

import csv
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
from sqlalchemy import Column, Table, select, text
from sqlalchemy import types as sa
from sqlalchemy.orm import Session

import labra
from labra import models
from labra.auth.principal import Principal
from labra.core import audit
from labra.core.ids import IST, utcnow
from labra.exports.common import private_dir, private_file

FORMATS = ("csv", "parquet", "both")
# Secrets that would let someone sign in, never written out.
LEFT_OUT = {
    "local_credential": "password hashes",
    "user_session": "signed-in sessions",
}
BATCH = 1000


@dataclass(frozen=True)
class Exported:
    folder: Path
    tables: int
    rows: int


def tables() -> list[Table]:
    """Every table Labra keeps, parents before children, less the secrets."""
    return [t for t in models.Base.metadata.sorted_tables if t.name not in LEFT_OUT]


def duck_type(column: Column[Any]) -> str:
    """The DuckDB type for a column. JSON is kept as its text so no extension is needed."""
    t = column.type
    if isinstance(t, sa.ARRAY):
        return f"{duck_type(Column('item', t.item_type))}[]"
    if isinstance(t, sa.JSON):
        return "VARCHAR"
    if isinstance(t, sa.Uuid):
        return "UUID"
    if isinstance(t, sa.Boolean):
        return "BOOLEAN"
    if isinstance(t, sa.SmallInteger):
        return "SMALLINT"
    if isinstance(t, sa.BigInteger):
        return "BIGINT"
    if isinstance(t, sa.Integer):
        return "INTEGER"
    if isinstance(t, sa.Numeric) and t.precision is not None:
        return f"DECIMAL({t.precision},{t.scale or 0})"
    if isinstance(t, sa.DateTime):
        return "TIMESTAMPTZ" if t.timezone else "TIMESTAMP"
    if isinstance(t, sa.Date):
        return "DATE"
    if isinstance(t, sa.String):
        return "VARCHAR"
    raise TypeError(f"No export type for {column.table.name}.{column.name}: {t!r}")


def _is_json(column: Column[Any]) -> bool:
    return isinstance(column.type, sa.JSON)


def _text(value: object, as_json: bool = False) -> object:
    """A value as text, for CSV and for the JSON lines DuckDB reads."""
    if value is None:
        return None
    if as_json:
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    return value


def _rows(db: Session, table: Table) -> Iterator[list[object]]:
    stmt = select(table).order_by(*table.primary_key.columns)
    flags = [_is_json(c) for c in table.columns]
    for row in db.execute(stmt.execution_options(yield_per=BATCH)):
        yield [_text(v, j) for v, j in zip(row, flags, strict=True)]


def _csv_cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return value


def _write_csv(db: Session, table: Table, path: Path) -> int:
    count = 0
    with private_file(path, newline="") as f:
        out = csv.writer(f)
        out.writerow([c.name for c in table.columns])
        for row in _rows(db, table):
            out.writerow([_csv_cell(v) for v in row])
            count += 1
    return count


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _write_parquet(db: Session, table: Table, path: Path, con: duckdb.DuckDBPyConnection) -> int:
    lines = path.with_name(path.name + ".jsonl")
    names = [c.name for c in table.columns]
    count = 0
    try:
        with private_file(lines) as f:
            for row in _rows(db, table):
                f.write(json.dumps(dict(zip(names, row, strict=True)), ensure_ascii=False))
                f.write("\n")
                count += 1
        columns = {c.name: duck_type(c) for c in table.columns}
        # Table and column names come from Labra's own models, never from input.
        name = _quoted(table.name)
        con.execute(f"DROP TABLE IF EXISTS {name}")
        if count:
            con.execute(
                f"CREATE TABLE {name} AS SELECT * FROM read_json("  # noqa: S608
                "?, format = 'newline_delimited', columns = ?)",
                [str(lines), columns],
            )
        else:
            spec = ", ".join(f"{_quoted(k)} {v}" for k, v in columns.items())
            con.execute(f"CREATE TABLE {name} ({spec})")
        part = path.with_name(path.name + ".part")
        con.execute(f"COPY {name} TO ? (FORMAT parquet, COMPRESSION zstd)", [str(part)])
        con.execute(f"DROP TABLE {name}")
        part.chmod(0o600)
        part.replace(path)
    finally:
        lines.unlink(missing_ok=True)
    return count


def schema_md(db: Session, counts: dict[str, int], at: datetime) -> str:
    revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    lines = [
        "# Labra data export",
        "",
        f"Exported {at.astimezone(IST):%d %b %Y %H:%M} IST by Labra {labra.__version__},"
        f" database version {revision}.",
        f"{len(counts)} tables, {sum(counts.values())} rows.",
        "",
        "- Each table is in `csv/<table>.csv` and `parquet/<table>.parquet`, ordered by its"
        " primary key. In CSV an empty cell is a missing value; JSON values and lists are"
        " written as JSON text.",
        "- Times are in UTC with their offset. Amounts are rupees with two decimals.",
        "- Uploaded files (letterheads, signatures, outside reports, report PDFs) are listed in"
        " `stored_file` but are not in the export; they are in the files folder and the backups.",
        "- Left out on purpose: "
        + "; ".join(f"`{name}` ({why})" for name, why in sorted(LEFT_OUT.items()))
        + ".",
        "",
    ]
    for table in tables():
        keys = ", ".join(c.name for c in table.primary_key.columns)
        lines += [
            f"## {table.name}",
            "",
            f"{counts.get(table.name, 0)} rows. Primary key: {keys}.",
            "",
            "| Column | Type | Empty allowed | Refers to |",
            "|---|---|---|---|",
        ]
        for c in table.columns:
            refers = ", ".join(f"{fk.column.table.name}.{fk.column.name}" for fk in c.foreign_keys)
            empty = "yes" if c.nullable else "no"
            lines.append(f"| {c.name} | {duck_type(c).lower()} | {empty} | {refers} |")
        lines.append("")
    return "\n".join(lines)


def export(db: Session, principal: Principal, root: Path, fmt: str = "both") -> Exported:
    """Write every table to a new folder under `root` and audit it."""
    if fmt not in FORMATS:
        raise ValueError(fmt)
    at = utcnow()
    folder = root / f"all-{at.astimezone(IST):%Y%m%d-%H%M%S}"
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    counts: dict[str, int] = {}
    if fmt in ("csv", "both"):
        csv_dir = private_dir(folder / "csv")
        for table in tables():
            counts[table.name] = _write_csv(db, table, csv_dir / f"{table.name}.csv")
    if fmt in ("parquet", "both"):
        parquet_dir = private_dir(folder / "parquet")
        con = duckdb.connect(
            ":memory:",
            config={"autoinstall_known_extensions": False, "autoload_known_extensions": False},
        )
        try:
            for table in tables():
                counts[table.name] = _write_parquet(
                    db, table, parquet_dir / f"{table.name}.parquet", con
                )
        finally:
            con.close()
    with private_file(folder / "schema.md") as f:
        f.write(schema_md(db, counts, at))
    total = sum(counts.values())
    audit.record(
        db,
        "export.all",
        "export",
        None,
        {"format": fmt, "folder": folder.name, "tables": len(counts), "rows": total},
        user_id=principal.user_id,
    )
    return Exported(folder, len(counts), total)
