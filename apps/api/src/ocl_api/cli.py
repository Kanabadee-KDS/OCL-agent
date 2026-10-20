"""`ocl` command line: ingest (D2), extract (D4), worker (R1)."""

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ocl", description="OCL Agent tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest", help="curriculum book (.docx/.pdf) -> Markdown + assets + JSON")
    p.add_argument("file")
    p.add_argument("--out", help="output dir (default: data/ingest/<file stem>)")
    p.set_defaults(func=cmd_ingest)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
