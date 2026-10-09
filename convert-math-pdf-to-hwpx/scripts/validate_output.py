from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from collections import Counter
from xml.etree import ElementTree as ET

from common import write_json


def equation_issues(analysis: dict, config: dict | None = None) -> list[str]:
    if (config or {}).get("math", {}).get("require_all_equations", True) is False:
        return []
    issues = []
    for page in analysis.get("pages", []):
        audit = page.get("math_audit", {})
        count = sum(e.get("kind") == "equation" for e in page.get("elements", []))
        expected = audit.get("formula_count")
        if audit.get("verified") is not True or type(expected) is not int or expected < 0:
            issues.append(f"Page {page['page']}: a visually verified math_audit with formula_count is required")
        elif expected != count:
            issues.append(f"Page {page['page']}: {expected} source formulas but {count} native equations")
        pending = sum(bool(e.get("requires_equation")) for e in page.get("reviews", []) + page.get("elements", []))
        if pending:
            issues.append(f"Page {page['page']}: {pending} mathematical regions still need native equations")
    return issues


def compare_pages(source: Path, rendered: Path, directory: Path, config: dict) -> dict:
    import pymupdf as fitz
    from PIL import Image, ImageChops, ImageFilter, ImageStat

    directory.mkdir(parents=True, exist_ok=True)
    dpi = int(config.get("comparison_dpi", 144))
    tolerance = float(config.get("paper_tolerance_pt", 1.0))
    pages = []
    with fitz.open(source) as original, fitz.open(rendered) as result:
        if len(original) != len(result):
            return {"page_count_match": False, "expected_pages": len(original), "actual_pages": len(result), "pages": []}
        for index, (src, dst) in enumerate(zip(original, result)):
            sizes_match = abs(src.rect.width - dst.rect.width) <= tolerance and abs(src.rect.height - dst.rect.height) <= tolerance
            matrix = fitz.Matrix(dpi / 72, dpi / 72)
            a_pix, b_pix = src.get_pixmap(matrix=matrix, alpha=False), dst.get_pixmap(matrix=matrix, alpha=False)
            a = Image.frombytes("RGB", [a_pix.width, a_pix.height], a_pix.samples)
            b = Image.frombytes("RGB", [b_pix.width, b_pix.height], b_pix.samples)
            if b.size != a.size:
                b = b.resize(a.size, Image.Resampling.LANCZOS)
            difference = ImageChops.difference(a, b)
            mae = sum(ImageStat.Stat(difference).mean) / (3 * 255)
            ink_a = a.convert("L").point(lambda value: 255 if value < 240 else 0)
            ink_b = b.convert("L").point(lambda value: 255 if value < 240 else 0)
            near_a, near_b = ink_a.filter(ImageFilter.MaxFilter(3)), ink_b.filter(ImageFilter.MaxFilter(3))
            count_a = ink_a.histogram()[255]
            count_b = ink_b.histogram()[255]
            matched_a = ImageChops.multiply(ink_a, near_b).histogram()[255]
            matched_b = ImageChops.multiply(ink_b, near_a).histogram()[255]
            overlap = (matched_a + matched_b) / (count_a + count_b) if count_a + count_b else 1.0
            source_name = f"page-{index + 1:03d}-source.png"
            output_name = f"page-{index + 1:03d}-output.png"
            diff_name = f"page-{index + 1:03d}-difference.png"
            a.save(directory / source_name)
            b.save(directory / output_name)
            difference.save(directory / diff_name)
            pages.append({"page": index + 1, "paper_size_match": sizes_match,
                          "source_size_pt": list(src.rect)[2:], "output_size_pt": list(dst.rect)[2:],
                          "normalized_mean_absolute_difference": round(mae, 6), "ink_overlap_with_1px_tolerance": round(overlap, 6),
                          "source_preview": str((directory / source_name).resolve()),
                          "output_preview": str((directory / output_name).resolve()),
                          "difference_preview": str((directory / diff_name).resolve())})
    return {"page_count_match": True, "pages": pages,
            "passed": all(p["paper_size_match"] and p["ink_overlap_with_1px_tolerance"] >= float(config.get("minimum_ink_overlap", .80)) for p in pages)}


def validate(analysis: dict, output: Path | None, build_result: dict | None = None, config: dict | None = None) -> dict:
    elements = [element for page in analysis.get("pages", []) for element in page.get("elements", [])]
    reviews = [element for element in elements if element.get("kind") == "review" or element.get("reason")]
    reviews.extend(item for page in analysis.get("pages", []) for item in page.get("reviews", []))
    package_ok = None
    package_entries = []
    coverage = None
    native_counts = {}
    equations_match = False
    failures = []
    math_issues = equation_issues(analysis, config)
    if output:
        failures.extend(math_issues)
    if (build_result or {}).get("error"):
        failures.append(build_result["error"])
    if output and output.exists():
        try:
            with zipfile.ZipFile(output) as archive:
                bad = archive.testzip()
                package_entries = archive.namelist()
                required = {"mimetype", "Contents/header.xml", "Contents/content.hpf", "Contents/section0.xml"}
                package_ok = bad is None and required.issubset(package_entries)
                package_ok = package_ok and archive.read("mimetype") == b"application/hwp+zip"
                namespace = {"hp": "http://www.hancom.co.kr/hwpml/2011/paragraph"}
                texts = []
                scripts = []
                for name in package_entries:
                    if name.startswith("Contents/section") and name.endswith(".xml"):
                        root = ET.fromstring(archive.read(name))
                        texts.extend(node.text or "" for node in root.findall(".//hp:t", namespace))
                        scripts.extend(node.text or "" for node in root.findall(".//hp:equation/hp:script", namespace))
                        for kind, tag in [("equation", "equation"), ("image", "pic"), ("text_box", "drawText"), ("table", "tbl")]:
                            native_counts[kind] = native_counts.get(kind, 0) + len(root.findall(".//hp:" + tag, namespace))
                actual = Counter("".join(texts))
                expected = Counter("".join(e.get("text", "") for e in elements if e.get("kind") == "text"))
                total = sum(expected.values())
                coverage = sum(min(count, actual[char]) for char, count in expected.items()) / total if total else 1.0
                if coverage < .995:
                    failures.append("Expected editable text was lost during HWPX generation")
                counts_match = native_counts.get("equation", 0) == sum(e.get("kind") == "equation" for e in elements)
                if not counts_match:
                    failures.append("Native equation count does not match the analyzed equations")
                expected_scripts = [e.get("hwp_command", "") for e in elements if e.get("kind") == "equation"]
                scripts_match = Counter(re.sub(r"\s+", " ", s).strip() for s in scripts) == Counter(re.sub(r"\s+", " ", s).strip() for s in expected_scripts)
                equations_match = counts_match and scripts_match
                if not scripts_match:
                    failures.append("Native equation scripts differ from the verified source formulas")
                if analysis.get("mode") == "fidelity":
                    if native_counts.get("text_box", 0) != sum(e.get("kind") == "text" for e in elements):
                        failures.append("Native text box count differs from the analyzed text")
                    if native_counts.get("image", 0) != len(analysis.get("pages", [])):
                        failures.append("A source page background is missing")
        except (zipfile.BadZipFile, ET.ParseError):
            package_ok = False
    visual = {}
    rendered_path = (build_result or {}).get("rendered_pdf")
    if output and analysis.get("mode") == "fidelity" and not (build_result or {}).get("reopened_in_hangul"):
        failures.append("Native Hancom reopening was not verified")
    if output and rendered_path and Path(rendered_path).is_file():
        visual = compare_pages(Path(analysis["source"]), Path(rendered_path), output.parent / "validation-images", (config or {}).get("validation", {}))
        if not visual.get("page_count_match"):
            failures.append("Rendered page count differs from the source")
        elif analysis.get("mode") == "fidelity" and not visual.get("passed"):
            failures.append("Original paper geometry or visual similarity did not pass")
    elif output:
        failures.append("No PDF export available for visual validation")
    return {
        "source": analysis.get("source"),
        "output": str(output.resolve()) if output else "",
        "page_count": analysis.get("page_count", 0),
        "element_counts": {kind: sum(e.get("kind") == kind for e in elements) for kind in ("text", "equation", "image", "table", "review")},
        "review_count": len(reviews),
        "reviews": reviews,
        "hwpx_package_ok": package_ok,
        "hwpx_entry_count": len(package_entries),
        "build": build_result or {},
        "native_counts": native_counts,
        "editable_text_coverage": coverage,
        "all_equations_native": bool(output and package_ok and equations_match and not equation_issues(analysis)),
        "equation_issues": math_issues,
        "mode": analysis.get("mode", "editable"),
        "visual_comparison": visual,
        "failures": failures,
        "review_summary": dict(Counter(item.get("reason", "") for item in reviews)),
        "status": "failed" if failures or package_ok is False else ("needs-review" if reviews else ("pass" if output else "analysis-only")),
    }


def write_reports(report: dict, directory: Path) -> tuple[Path, Path]:
    json_path = directory / "conversion-report.json"
    html_path = directory / "conversion-report.html"
    write_json(json_path, report)
    rows = "".join(
        f"<tr><td>{item.get('page','')}</td><td>{html.escape(str(item.get('bbox','')))}</td><td>{html.escape(item.get('reason',''))}</td></tr>"
        for item in report["reviews"]
    ) or '<tr><td colspan="3">No review items</td></tr>'
    failures = "".join(f"<li>{html.escape(item)}</li>" for item in report.get("failures", []))
    summaries = "".join(f"<li>{html.escape(reason)}: {count}</li>" for reason, count in report.get("review_summary", {}).items())
    previews = ""
    for page in report.get("visual_comparison", {}).get("pages", []):
        images = ""
        for key, label in [("source_preview", "원본"), ("output_preview", "변환 결과"), ("difference_preview", "픽셀 차이")]:
            relative = Path(page[key]).relative_to(directory).as_posix()
            images += f'<figure><figcaption>{label}</figcaption><img src="{html.escape(relative, quote=True)}" alt="{label}"></figure>'
        previews += f'<h2>{page["page"]}쪽 비교</h2><p>용지 크기 일치: {page["paper_size_match"]} / 잉크 영역 겹침(1픽셀 허용): {page["ink_overlap_with_1px_tolerance"]:.1%}</p><div class="previews">{images}</div>'
    document = f"""<!doctype html><meta charset="utf-8"><title>HWPX conversion report</title>
<style>body{{font-family:Arial,'Malgun Gothic',sans-serif;max-width:1200px;margin:2rem auto;padding:0 16px;line-height:1.6}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bbb;padding:.5rem;text-align:left;overflow-wrap:anywhere}}.previews{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}}figure{{margin:0}}img{{width:100%;height:auto}}@media(max-width:700px){{.previews{{grid-template-columns:1fr}}}}</style>
<h1>HWPX conversion report</h1><p>Status: <strong>{html.escape(report['status'])}</strong></p>
<p>Pages: {report['page_count']} · Review items: {report['review_count']} · HWPX package: {report['hwpx_package_ok']}</p>
<p>Mode: {html.escape(report.get('mode',''))} / Native objects: {html.escape(str(report.get('native_counts',{})))}</p>
<p>All source formulas audited and native: {report.get('all_equations_native', False)}</p>
<p>수식은 본문·표·그래프 라벨까지 모두 한글 수식 객체여야 합니다. 이미지나 일반 문자로 남은 수식은 변환 실패입니다. 그래프 선과 장식은 이미지로 보존할 수 있습니다. 글꼴 대체 때문에 글자 모양이 달라질 수 있습니다. 픽셀 비교 수치는 수식 정확도를 뜻하지 않습니다.</p>
<ul>{failures}{summaries}</ul>{previews}
<table><thead><tr><th>Page</th><th>Bounding box</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>"""
    html_path.write_text(document, encoding="utf-8")
    return json_path, html_path
