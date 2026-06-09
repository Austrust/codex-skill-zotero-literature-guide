#!/usr/bin/env python3
"""Validate MinerU-recognized displayed formulas before guide rendering."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_FROM = "markdown+tex_math_dollars+tex_math_single_backslash"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def load_manifest(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list):
        raise ValueError("asset_manifest.json must be a JSON list")
    return [item for item in data if isinstance(item, dict)]


def formula_records(manifest: list[dict[str, Any]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for item in manifest:
        typ = str(item.get("type") or "").lower()
        if typ not in {"formula", "equation"}:
            continue
        latex = str(item.get("caption_or_label") or "").strip()
        if not latex:
            continue
        if "$" not in latex and "\\" not in latex:
            continue
        records.append(
            {
                "asset_id": str(item.get("asset_id") or item.get("path") or f"formula_{len(records) + 1:03d}"),
                "path": str(item.get("path") or ""),
                "latex": latex,
            }
        )
    return records


def probe_markdown(records: list[dict[str, str]], title: str) -> str:
    lines = [
        f"# {title}",
        "",
        "This probe compiles MinerU-recognized displayed formulas before they are inserted into the guide.",
        "",
    ]
    for index, item in enumerate(records, 1):
        lines.extend([f"## F{index:03d} {item['asset_id']}", "", item["latex"], ""])
    return "\n".join(lines)


def run_pandoc(markdown: str, work_dir: Path, output_name: str, args: argparse.Namespace) -> subprocess.CompletedProcess[str]:
    md_path = work_dir / f"{output_name}.md"
    pdf_path = work_dir / f"{output_name}.pdf"
    md_path.write_text(markdown, encoding="utf-8")
    cmd = [
        args.pandoc,
        str(md_path),
        "-o",
        str(pdf_path),
        "--from",
        args.markdown_from,
        "--pdf-engine",
        args.pdf_engine,
        "-V",
        f"mainfont={args.mainfont}",
        "-V",
        f"CJKmainfont={args.cjk_font}",
        "-V",
        f"mathfont={args.mathfont}",
        "-V",
        "geometry:a4paper",
        "-V",
        "geometry:margin=2cm",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def validate_records(records: list[dict[str, str]], args: argparse.Namespace) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="zlg_formula_latex_") as tmp:
        tmp_path = Path(tmp)
        all_proc = run_pandoc(probe_markdown(records, "MinerU Formula Probe"), tmp_path, "all_formulas", args)
        results: list[dict[str, Any]] = []
        if all_proc.returncode == 0:
            for item in records:
                results.append(
                    {
                        "asset_id": item["asset_id"],
                        "path": item["path"],
                        "status": "pass",
                        "mode": "latex",
                    }
                )
        else:
            for index, item in enumerate(records, 1):
                proc = run_pandoc(probe_markdown([item], f"MinerU Formula Probe {index:03d}"), tmp_path, f"formula_{index:03d}", args)
                result: dict[str, Any] = {
                    "asset_id": item["asset_id"],
                    "path": item["path"],
                    "status": "pass" if proc.returncode == 0 else "fail",
                    "mode": "latex" if proc.returncode == 0 else "image_fallback",
                }
                if proc.returncode != 0:
                    result["stderr"] = proc.stderr[-2000:]
                results.append(result)
        failed = [item for item in results if item["status"] != "pass"]
        return {
            "schema_version": "0.1",
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "status": "pass" if not failed else "fail",
            "formula_count": len(records),
            "passed_formula_count": len(records) - len(failed),
            "failed_formula_count": len(failed),
            "markdown_from": args.markdown_from,
            "pdf_engine": args.pdf_engine,
            "pandoc_returncode_all": all_proc.returncode,
            "pandoc_stderr_all": all_proc.stderr[-4000:] if all_proc.returncode != 0 else "",
            "formulas": results,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile-check MinerU formula LaTeX from asset_manifest.json")
    parser.add_argument("--asset-manifest", required=True, type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--pandoc", default="pandoc")
    parser.add_argument("--pdf-engine", default="xelatex")
    parser.add_argument("--markdown-from", default=DEFAULT_FROM)
    parser.add_argument("--mainfont", default="Times New Roman")
    parser.add_argument("--cjk-font", default="Microsoft YaHei")
    parser.add_argument("--mathfont", default="Cambria Math")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    records = formula_records(load_manifest(args.asset_manifest))
    report = validate_records(records, args) if records else {
        "schema_version": "0.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "warn",
        "formula_count": 0,
        "passed_formula_count": 0,
        "failed_formula_count": 0,
        "formulas": [],
        "warnings": ["no MinerU formula LaTeX found in asset manifest"],
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json or not args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
