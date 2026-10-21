"""extract(ingest_dir): Document -> parts JSON + checks + Markdown views."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ocl_api.extract.base import PartResult, load_document
from ocl_api.extract.courses import extract_courses
from ocl_api.extract.info import extract_info
from ocl_api.extract.mapping import extract_mapping
from ocl_api.extract.plo import extract_plo
from ocl_api.extract.render import RENDERERS
from ocl_api.extract.structure import extract_structure
from ocl_api.extract.validators import run_checks

PLUGINS = {
    "info": extract_info,
    "structure": extract_structure,
    "plo": extract_plo,
    "courses": extract_courses,
    "mapping": extract_mapping,
}
DEFAULT_PARTS = ["info", "structure", "plo", "courses", "mapping"]


def extract(
    ingest_dir: str | Path,
    *,
    parts: list[str] | None = None,
    gateway=None,
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    ingest_dir = Path(ingest_dir)
    out = Path(out_dir) if out_dir else ingest_dir / "extract"
    out.mkdir(parents=True, exist_ok=True)
    (out / "md").mkdir(exist_ok=True)
    doc = load_document(ingest_dir)
    parts = parts or DEFAULT_PARTS
    results: dict[str, PartResult] = {}
    timings: dict[str, float] = {}
    for key in parts:
        fn = PLUGINS[key]
        t0 = time.perf_counter()
        results[key] = fn(doc, gateway)
        timings[key] = round(time.perf_counter() - t0, 2)
        (out / f"{key}.json").write_text(
            json.dumps(
                {
                    "part": key,
                    "data": results[key].data,
                    "notes": results[key].notes,
                    "llm": results[key].llm_usage,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
        name, render = RENDERERS[key]
        (out / "md" / name).write_text(render(results[key].data), encoding="utf-8")

    checks = run_checks({k: r.data for k, r in results.items()})
    (out / "checks.json").write_text(
        json.dumps([c.to_dict() for c in checks], ensure_ascii=False, indent=1), encoding="utf-8"
    )
    report = {
        "source": doc.source_name,
        "out_dir": str(out),
        "provider": getattr(gateway, "provider", None) if gateway else None,
        "model": getattr(gateway, "model", None) if gateway else None,
        "parts": {
            k: {
                "seconds": timings[k],
                "count": r.data.get("count", r.data.get("node_count")),
                "llm": r.llm_usage,
                "notes": r.notes,
            }
            for k, r in results.items()
        },
        "checks": {
            "pass": sum(c.status == "pass" for c in checks),
            "warn": sum(c.status == "warn" for c in checks),
            "fail": sum(c.status == "fail" for c in checks),
            "items": [c.to_dict() for c in checks],
        },
    }
    (out / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return report
