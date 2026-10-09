"""The `labra` command: serve, migrate, seed and admin tasks."""

import argparse
import getpass
import sys

from labra.core.errors import ConfigError, LabraError


def _out(message: str) -> None:
    sys.stdout.write(message + "\n")


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "labra.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        workers=args.workers,
        proxy_headers=True,
        forwarded_allow_ips=args.forwarded_allow_ips,
        access_log=False,
    )
    return 0


def cmd_migrate(_: argparse.Namespace) -> int:
    from sqlalchemy.orm import Session

    from labra.core.db import get_engine
    from labra.core.migrate import upgrade
    from labra.org.service import sync_system_roles

    upgrade()
    with Session(get_engine()) as db:
        sync_system_roles(db)
        db.commit()
    _out("Database is at the latest version.")
    return 0


def cmd_check_config(_: argparse.Namespace) -> int:
    from labra.core.config import get_settings
    from labra.core.registry import build_platform

    platform = build_platform(get_settings())
    for name, adapter in vars(platform).items():
        _out(f"{name:10} {type(adapter).__module__}.{type(adapter).__name__}")
    _out("Configuration is valid.")
    return 0


def cmd_audit_verify(_: argparse.Namespace) -> int:
    from sqlalchemy.orm import Session

    from labra.core import audit
    from labra.core.db import get_engine
    from labra.core.metrics import count_job
    from labra.core.registry import get_platform

    with Session(get_engine()) as db:
        result = audit.verify(db)
    count_job("audit_verify", result.ok)
    detail = f"{result.checked} rows checked"
    if result.ok:
        _out(f"Audit log intact: {detail}.")
    else:
        detail += f"; row {result.first_bad_id}: {result.reason}"
        _out(f"AUDIT LOG DAMAGED: {detail}.")
    get_platform().heartbeat.ping("audit_verify", ok=result.ok, detail=detail)
    return 0 if result.ok else 1


def cmd_create_admin(args: argparse.Namespace) -> int:
    """The first administrator, with a role at every branch. Run once after `migrate`."""
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from labra import models
    from labra.core import audit
    from labra.core.db import get_engine
    from labra.core.registry import get_platform
    from labra.org.service import sync_system_roles

    identity = get_platform().identity
    password = getpass.getpass("New password: ")
    problems = identity.password_problems(password)
    if problems:
        _out(" ".join(problems))
        return 1
    if getpass.getpass("Again: ") != password:
        _out("The passwords don't match.")
        return 1
    with Session(get_engine()) as db:
        sync_system_roles(db)
        if db.scalar(select(models.AppUser).where(models.AppUser.username == args.username)):
            _out(f"User {args.username} already exists.")
            return 1
        admin_role = db.scalar(select(models.Role).where(models.Role.code == "admin"))
        branches = list(db.scalars(select(models.Branch)))
        if admin_role is None or not branches:
            _out("Add the main lab first: labra add-branch --code MAIN --name '...'.")
            return 1
        user = models.AppUser(username=args.username, full_name=args.full_name)
        db.add(user)
        db.flush()
        for b in branches:
            db.add(models.UserBranchRole(user_id=user.id, branch_id=b.id, role_id=admin_role.id))
        identity.set_password(db, user.id, password)
        audit.record(db, "user.create", "app_user", user.id, {"via": "cli"})
        db.commit()
    _out(f"Administrator {args.username} created.")
    return 0


def cmd_add_branch(args: argparse.Namespace) -> int:
    from sqlalchemy.orm import Session

    from labra import models
    from labra.core import audit
    from labra.core.db import get_engine

    with Session(get_engine()) as db:
        branch = models.Branch(code=args.code.upper(), name=args.name, kind=args.kind)
        db.add(branch)
        db.flush()
        audit.record(db, "branch.create", "branch", branch.id, {"via": "cli"})
        db.commit()
    _out(f"Branch {args.code.upper()} added.")
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    from labra.seed import run

    run()
    _out("Synthetic demo data loaded. Every password is 'demo-password-1'.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="labra")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--workers", type=int, default=1)
    serve.add_argument(
        "--forwarded-allow-ips",
        default="127.0.0.1",
        help="proxies trusted to set X-Forwarded-For (Caddy's address under Compose)",
    )
    serve.set_defaults(func=cmd_serve)

    sub.add_parser("migrate", help="upgrade the database to this version").set_defaults(
        func=cmd_migrate
    )
    sub.add_parser("check-config", help="validate settings and adapters").set_defaults(
        func=cmd_check_config
    )

    audit_cmd = sub.add_parser("audit", help="audit log tasks")
    audit_sub = audit_cmd.add_subparsers(dest="audit_command", required=True)
    audit_sub.add_parser("verify", help="check the audit log hash chain").set_defaults(
        func=cmd_audit_verify
    )

    branch = sub.add_parser("add-branch", help="add a branch (for first setup)")
    branch.add_argument("--code", required=True)
    branch.add_argument("--name", required=True)
    branch.add_argument("--kind", choices=["main_lab", "collection_centre"], default="main_lab")
    branch.set_defaults(func=cmd_add_branch)

    admin = sub.add_parser("create-admin", help="create the first administrator")
    admin.add_argument("--username", required=True)
    admin.add_argument("--full-name", required=True)
    admin.set_defaults(func=cmd_create_admin)

    sub.add_parser("seed", help="load synthetic demo data (never on a live lab)").set_defaults(
        func=cmd_seed
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        code = args.func(args)
    except ConfigError as exc:
        _out(f"Configuration error: {exc.public_message}")
        code = 2
    except LabraError as exc:
        _out(exc.public_message)
        code = 1
    sys.exit(code)
