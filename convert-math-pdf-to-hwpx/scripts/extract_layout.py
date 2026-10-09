from __future__ import annotations

from pathlib import Path

from math_to_hwp import contains_math_marker, is_formula_candidate, latex_to_hwp


def _bbox(values) -> list[float]:
    return [round(float(v), 3) for v in values]


def extract_layout(pdf_path: Path, asset_dir: Path, config: dict) -> dict:
    if config.get("pipeline", {}).get("mode", "fidelity") == "fidelity":
        from preserve_layout import extract_fidelity
        return extract_fidelity(pdf_path, asset_dir, config)
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required. Install requirements.txt.") from exc

    asset_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    pages = []
    accept = float(config.get("math", {}).get("accept_confidence", 0.90))
    dpi = int(config.get("pdf", {}).get("render_dpi", 300))
    scale = dpi / 72.0
    for page_index, page in enumerate(doc):
        elements = []
        text_dict = page.get_text("dict")
        for block in text_dict.get("blocks", []):
            if block.get("type") == 0:
                for line in block.get("lines", []):
                    line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                    if not line_text:
                        continue
                    element = {"kind": "text", "page": page_index + 1, "bbox": _bbox(line["bbox"]), "text": line_text, "confidence": 1.0}
                    from preserve_layout import ENCODED_MATH, readable
                    if any(ENCODED_MATH.search(span.get("font", "")) for span in line["spans"]) or any(not readable(ch) for ch in line_text):
                        asset = asset_dir / f"page-{page_index + 1:03d}-uncertain-{len(elements):03d}.png"
                        page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=fitz.Rect(line["bbox"]), alpha=False).save(asset)
                        element.update(kind="review", asset=str(asset.resolve()), confidence=0.0,
                                       reason="Unreliable symbol-font text retained as source crop")
                    elif is_formula_candidate(line_text):
                        try:
                            element.update({"kind": "equation", "hwp_command": latex_to_hwp(line_text), "confidence": 0.95})
                        except ValueError as exc:
                            element.update({"kind": "review", "confidence": 0.0, "reason": str(exc)})
                    elif contains_math_marker(line_text):
                        element.update({"confidence": 0.80, "requires_equation": True,
                                        "reason": "Mixed prose/math requires separate verified equation regions"})
                    elements.append(element)
            elif block.get("type") == 1:
                rect = fitz.Rect(block["bbox"])
                asset = asset_dir / f"page-{page_index + 1:03d}-image-{len(elements) + 1:03d}.png"
                page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False).save(asset)
                elements.append({"kind": "image", "page": page_index + 1, "bbox": _bbox(rect), "asset": str(asset.resolve()), "confidence": 1.0})

        for figure_index, drawing_box in enumerate(page.cluster_drawings(x_tolerance=6, y_tolerance=6)):
            rect = fitz.Rect(drawing_box) + (-4, -4, 4, 4)
            if rect.get_area() >= float(config.get("pdf", {}).get("vector_figure_min_area_pt2", 900)):
                rect &= page.rect
                asset = asset_dir / f"page-{page_index + 1:03d}-vector-{figure_index:03d}.png"
                page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False).save(asset)
                elements = [item for item in elements if not rect.contains(fitz.Rect(item["bbox"]))]
                elements.append({"kind": "image", "page": page_index + 1, "bbox": _bbox(rect), "asset": str(asset.resolve()), "confidence": 1.0, "note": "Connected vector drawings retained as a source crop"})

        if not elements:
            asset = asset_dir / f"page-{page_index + 1:03d}-full.png"
            page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(asset)
            elements.append({"kind": "review", "page": page_index + 1, "bbox": _bbox(page.rect), "asset": str(asset.resolve()), "confidence": 0.0, "reason": "No editable text layer; OCR provider required"})
        elements.sort(key=lambda item: (item["bbox"][1], item["bbox"][0], item["kind"] == "image"))
        pages.append({"page": page_index + 1, "width_pt": page.rect.width, "height_pt": page.rect.height, "elements": elements})
    doc.close()
    return {"source": str(pdf_path.resolve()), "mode": "editable", "page_count": len(pages), "accept_confidence": accept, "pages": pages}
