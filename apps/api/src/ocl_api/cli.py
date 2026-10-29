"""`ocl` command line: ingest (D2/D3), extract (D4), worker (R1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_ingest(args: argparse.Namespace) -> int:
    from ocl_api.ingest.pipeline import ingest

    src = Path(args.file)
    out = Path(args.out) if args.out else Path("data/ingest") / src.stem
    report = ingest(src, out)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    from ocl_api.extract.pipeline import DEFAULT_PARTS, extract

    target = Path(args.target)
    if target.is_file():  # a source book: ingest first (or reuse an existing ingest dir)
        from ocl_api.ingest.pipeline import ingest

        ingest_dir = Path("data/ingest") / target.stem
        if not (ingest_dir / "document.json").exists() or args.reingest:
            ingest(target, ingest_dir)
    else:
        ingest_dir = target
    gateway = None
    if not args.no_llm:
        from ocl_api.llm.gateway import LLMGateway

        gateway = LLMGateway()
        print(f"LLM: provider={gateway.provider} model={gateway.model}", file=sys.stderr)
    parts = [p.strip() for p in args.parts.split(",")] if args.parts else DEFAULT_PARTS
    report = extract(ingest_dir, parts=parts, gateway=gateway, out_dir=args.out)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    return 0


def cmd_golden(args: argparse.Namespace) -> int:
    from ocl_api.extract.golden import render_golden

    ingest_dir = Path(args.ingest_dir)
    extract_dir = Path(args.extract) if args.extract else ingest_dir / "extract"
    book = ingest_dir.name
    out = Path(args.out) if args.out else Path("data/golden") / f"{book}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_golden(extract_dir, book=book, reviewer=args.reviewer), encoding="utf-8")
    print(out)
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    from ocl_api.worker import run_loop

    return 0 if run_loop(once=args.once) is not None else 1


def cmd_db(args: argparse.Namespace) -> int:
    import json

    from ocl_api.config import get_settings
    from ocl_api.db import migrate, status

    s = get_settings()
    if not s.database_url:
        print("DATABASE_URL is not set: the store runs in file mode (DATA_DIR/imports)")
        return 1
    if args.action == "migrate":
        applied = migrate(s.database_url, s.database_schema)
        print("applied:", ", ".join(applied) or "nothing (already up to date)")
    print(json.dumps(status(s.database_url, s.database_schema), ensure_ascii=False, indent=1))
    return 0


def cmd_users(args: argparse.Namespace) -> int:
    import getpass
    import json

    from ocl_api.auth import ROLES
    from ocl_api.config import get_settings
    from ocl_api.users import UserStore

    s = get_settings()
    if not s.database_url:
        print("users need DATABASE_URL (Postgres)")
        return 1
    from ocl_api.db import migrate

    migrate(s.database_url, s.database_schema)  # the columns this command reads
    users = UserStore(s.database_url, s.database_schema)
    if args.action == "list":
        for u in users.list():
            print(
                f"{u['email']:40} {u.get('buasri_id') or '-':14} "
                f"{','.join(u['roles']) or '-':28} "
                f"{'active' if u['usable'] else 'DISABLED' if not u['active'] else 'EXPIRED':8} "
                f"{u.get('name') or ''}"
            )
        return 0
    if args.action == "roles":
        print(json.dumps(ROLES, ensure_ascii=False, indent=1))
        return 0
    if not args.email:
        print("--email is required")
        return 1
    if args.action in ("add", "set"):
        password = args.password
        if args.ask_password:
            password = getpass.getpass("password: ")
        roles = [r.strip() for r in (args.roles or "").split(",") if r.strip()]
        u = users.upsert(
            args.email,
            name=args.name or "",
            roles=roles,
            buasri_id=args.buasri,
            password=password,
            unit=args.unit,
        )
        # the users page shows who changed an account; record the server command too
        detail = {"roles": roles or None, "password_set": bool(password), "buasri": args.buasri}
        users.log(args.email, f"cli:{getpass.getuser()}", f"cli_{args.action}", detail)
        print(json.dumps(u, ensure_ascii=False, indent=1))
        return 0
    if args.action in ("disable", "enable"):
        users.set_active(args.email, args.action == "enable")
        users.log(args.email, f"cli:{getpass.getuser()}", f"cli_{args.action}", {})
        print(f"{args.email}: {'active' if args.action == 'enable' else 'disabled'}")
        return 0
    return 1


def cmd_seed(args: argparse.Namespace) -> int:
    """Fill the SUPREME / HURIS copies from the sample adapter, or show what is loaded."""
    import json

    from ocl_api.config import get_settings
    from ocl_api.db import migrate
    from ocl_api.external import SYSTEMS, ExternalStore
    from ocl_api.external.sample import SampleAdapter

    s = get_settings()
    if not s.database_url:
        print("seed needs DATABASE_URL (Postgres)")
        return 1
    migrate(s.database_url, s.database_schema)
    store = ExternalStore(s.database_url, s.database_schema)
    if args.action == "sample":
        for system in SYSTEMS if args.system == "all" else [args.system]:
            src = store.source(system)
            if src and not src["sample"] and not args.replace_real:
                print(f"{system}: filled by {src['adapter']}, not replaced (--replace-real)")
                continue
            print(system, json.dumps(store.load(SampleAdapter(), system)))
    for row in store.status():
        print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_outbox(args: argparse.Namespace) -> int:
    """E-mails the system queued (nothing is sent yet): list, show one, or queue a test."""
    import json

    from ocl_api.config import get_settings
    from ocl_api.db import migrate
    from ocl_api.mail import Outbox

    s = get_settings()
    if not s.database_url:
        print("outbox needs DATABASE_URL (Postgres)")
        return 1
    migrate(s.database_url, s.database_schema)
    box = Outbox(s.database_url, s.database_schema)
    if args.action == "test":
        if not args.to:
            print("--to is required")
            return 1
        try:
            m = box.send(
                args.to,
                "ทดสอบการส่งอีเมลจากระบบบริหารจัดการหลักสูตร",
                "อีเมลทดสอบจากคำสั่ง ocl outbox test · ยังไม่มีการส่งจริง",
                kind="test",
                by="cli",
            )
        except ValueError as e:
            print(e)
            return 1
        print(json.dumps(m, ensure_ascii=False, indent=1))
        return 0
    if args.action == "show":
        m = box.get(args.id) if args.id else None
        if m is None:
            print("not found (--id)")
            return 1
        print(json.dumps(m, ensure_ascii=False, indent=1))
        return 0
    from datetime import datetime, timedelta, timezone

    # NFR-15: Thai time. A fixed +07:00 (Thailand has no daylight saving) needs no tzdata,
    # which the slim API image may not carry.
    bkk = timezone(timedelta(hours=7))
    for m in box.list(args.status, args.limit):
        at = datetime.fromisoformat(m["created_at"]).astimezone(bkk).strftime("%Y-%m-%d %H:%M")
        print(
            f"{m['id']:>6} {at} {m['status']:7} {m['kind']:10} "
            f"{','.join(m['to_addrs'])[:40]:40} {m['subject']}"
        )
    return 0


def cmd_flows(args: argparse.Namespace) -> int:
    """Approval flows: queue today's overdue reminders now (the worker does it hourly)."""
    from ocl_api.config import get_settings
    from ocl_api.curricula import CurriculumStore
    from ocl_api.db import migrate

    s = get_settings()
    if not s.database_url:
        print("flows need DATABASE_URL (Postgres)")
        return 1
    migrate(s.database_url, s.database_schema)
    sent = CurriculumStore(s.database_url, s.database_schema, None).remind_overdue()
    print(f"overdue reminders queued: {sent}")
    return 0


def cmd_api(args: argparse.Namespace) -> int:
    import uvicorn

    from ocl_api.config import get_settings

    s = get_settings()
    uvicorn.run(
        "ocl_api.main:app",
        host=args.host or s.api_host,
        port=args.port or s.api_port,
        reload=args.reload,
    )
    return 0


def cmd_fewshot(args: argparse.Namespace) -> int:
    from ocl_api.fewshot.check import main as check_main

    return check_main(args.parts or None)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocl", description="OCL Agent tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("ingest", help="curriculum book (.docx/.pdf) -> Markdown + assets + JSON")
    p.add_argument("file")
    p.add_argument("--out", help="output dir (default: data/ingest/<file stem>)")
    p.set_defaults(func=cmd_ingest)

    e = sub.add_parser(
        "extract", help="ingest dir (or book) -> structured parts JSON + checks + md"
    )
    e.add_argument("target", help="ingest dir from `ocl ingest`, or a .docx/.pdf (ingested first)")
    e.add_argument(
        "--parts",
        help="comma list of parts, e.g. info,plan,courses (default: all)",
    )
    e.add_argument("--no-llm", action="store_true", help="parser only, never call the LLM")
    e.add_argument("--reingest", action="store_true", help="re-run ingest even if output exists")
    e.add_argument("--out", help="output dir (default: <ingest dir>/extract)")
    e.set_defaults(func=cmd_extract)

    g = sub.add_parser(
        "golden", help="review checklist (Markdown) for the Admin from extract output"
    )
    g.add_argument("ingest_dir")
    g.add_argument("--extract", help="extract dir (default: <ingest dir>/extract)")
    g.add_argument("--reviewer", default="")
    g.add_argument("--out", help="output file (default: data/golden/<book>.md)")
    g.set_defaults(func=cmd_golden)

    w = sub.add_parser("worker", help="process queued import jobs one at a time (ingest + extract)")
    w.add_argument("--once", action="store_true", help="drain the queue then exit")
    w.set_defaults(func=cmd_worker)

    u = sub.add_parser("users", help="manage users and roles (Postgres)")
    u.add_argument("action", choices=["add", "set", "list", "roles", "disable", "enable"])
    u.add_argument("--email")
    u.add_argument("--name", default="")
    u.add_argument("--roles", help="comma list, e.g. central,curator")
    u.add_argument("--buasri", help="Buasri ID (username for password sign-in)")
    u.add_argument("--password", help="password for Buasri sign-in (or --ask-password)")
    u.add_argument("--ask-password", action="store_true")
    u.add_argument("--unit", help="คณะ/หน่วยงาน")
    u.set_defaults(func=cmd_users)

    sd = sub.add_parser("seed", help="external data: load the sample adapter, or show status")
    sd.add_argument("action", choices=["sample", "status"])
    sd.add_argument("--system", choices=["all", "huris", "supreme"], default="all")
    sd.add_argument("--replace-real", action="store_true", help="overwrite data from a real feed")
    sd.set_defaults(func=cmd_seed)

    ob = sub.add_parser("outbox", help="e-mail outbox: list, show, or queue a test message")
    ob.add_argument("action", choices=["list", "show", "test"])
    ob.add_argument("--id", type=int)
    ob.add_argument("--to", help="recipient for test")
    ob.add_argument("--status", choices=["queued", "sent", "failed"])
    ob.add_argument("--limit", type=int, default=50)
    ob.set_defaults(func=cmd_outbox)

    fl = sub.add_parser("flows", help="approval flows: queue overdue reminders now")
    fl.add_argument("action", choices=["remind"])
    fl.set_defaults(func=cmd_flows)

    db = sub.add_parser("db", help="database: migrate (apply schema) or status")
    db.add_argument("action", choices=["migrate", "status"])
    db.set_defaults(func=cmd_db)

    f = sub.add_parser("fewshot", help="few-shot examples: check the files before approving")
    f.add_argument("action", choices=["check"])
    f.add_argument("parts", nargs="*", help="info / plo / courses (default: all)")
    f.set_defaults(func=cmd_fewshot)

    a = sub.add_parser("api", help="run the REST API (uvicorn)")
    a.add_argument("--host")
    a.add_argument("--port", type=int)
    a.add_argument("--reload", action="store_true")
    a.set_defaults(func=cmd_api)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
