from __future__ import annotations

from pathlib import Path


def inspect_pdf(path: Path, text_coverage_threshold: float = 0.35) -> dict:
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required. Install requirements.txt.") from exc

    document = fitz.open(path)
    pages = []
    for index, page in enumerate(document):
        text = page.get_text("text").strip()
        area = max(page.rect.width * page.rect.height, 1.0)
        text_blocks = [b for b in page.get_text("blocks") if len(b) > 6 and b[6] == 0]
        covered = sum(max(0.0, (b[2] - b[0]) * (b[3] - b[1])) for b in text_blocks)
        coverage = min(1.0, covered / area)
        image_count = len(page.get_images(full=True))
        drawing_count = len(page.get_drawings())
        if not text:
            kind = "scan"
        elif coverage < text_coverage_threshold and image_count:
            kind = "mixed"
        else:
            kind = "text"
        pages.append(
            {
                "page": index + 1,
                "width_pt": round(page.rect.width, 3),
                "height_pt": round(page.rect.height, 3),
                "orientation": "landscape" if page.rect.width > page.rect.height else "portrait",
                "kind": kind,
                "text_coverage": round(coverage, 4),
                "image_count": image_count,
                "drawing_count": drawing_count,
            }
        )
    result_kind = "mixed" if len({p["kind"] for p in pages}) > 1 else (pages[0]["kind"] if pages else "empty")
    return {"source": str(path.resolve()), "page_count": len(pages), "kind": result_kind, "pages": pages}
