from __future__ import annotations

import argparse
from pathlib import Path

from build_hwpx import build_hwpx
from common import load_yaml, write_json
from extract_layout import extract_layout
from inspect_pdf import inspect_pdf
from validate_output import equation_issues, validate, write_reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert mathematics PDFs to HWPX while preserving original page geometry")
    parser.add_argument("input", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--mode", choices=("fidelity", "editable"))
    parser.add_argument("--overrides", type=Path, help="Verified equations tied to the source PDF SHA-256")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        raise SystemExit(f"Input PDF not found: {source}")
    config = load_yaml(args.config.resolve())
    if args.mode:
        config.setdefault("pipeline", {})["mode"] = args.mode
    if args.overrides:
        config.setdefault("layout", {})["overrides"] = str(args.overrides.resolve())
    if config.get("pipeline", {}).get("mode", "fidelity") not in {"fidelity", "editable"}:
        raise SystemExit("pipeline.mode must be fidelity or editable")
    work_dir = Path(config.get("pipeline", {}).get("work_dir", "work/math-pdf-to-hwpx")).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    output = (args.output or Path.cwd() / "outputs" / (source.stem + "_editable.hwpx")).resolve()
    if output == source:
        raise SystemExit("The source PDF must not be overwritten")
    if output.suffix.lower() != ".hwpx":
        raise SystemExit("Output filename must end in .hwpx")
    if output.exists() and not args.overwrite and not args.analyze_only:
        raise SystemExit(f"Output already exists; pass --overwrite: {output}")
    metadata = inspect_pdf(source, float(config.get("pdf", {}).get("text_coverage_threshold", 0.35)))
    analysis = extract_layout(source, work_dir / "assets", config)
    analysis["inspection"] = metadata
    analysis_path = work_dir / "analysis.json"
    write_json(analysis_path, analysis)
    if args.analyze_only:
        report = validate(analysis, None, config=config)
        write_reports(report, work_dir)
        print(analysis_path)
        return 0
    issues = equation_issues(analysis, config)
    if issues:
        report = validate(analysis, None, config=config)
        report.update(status="failed", failures=issues)
        write_reports(report, work_dir)
        print("Native equation reconstruction is incomplete. See " + str(work_dir / "conversion-report.json"))
        return 3
    build_result = build_hwpx(analysis, output, config)
    report = validate(analysis, output, build_result, config)
    write_json(output.parent / "analysis.json", analysis)
    write_reports(report, output.parent)
    print(output)
    return 3 if report["status"] == "failed" else (2 if report["status"] == "needs-review" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
