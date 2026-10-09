from __future__ import annotations

import sys
from pathlib import Path


def create(path: Path) -> None:
    import fitz

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 70), "1. Find the minimum value of f(x)=x^2-4x+7.", fontsize=12)
    page.insert_text((70, 105), r"\frac{x+1}{x-2}", fontsize=12)
    page.insert_text((70, 140), "1) 1   2) 2   3) 3   4) 4   5) 5", fontsize=11)
    page.draw_line((310, 240), (510, 240), color=(0, 0, 0), width=1)
    page.draw_line((410, 160), (410, 320), color=(0, 0, 0), width=1)
    points = [(330, 290), (370, 260), (410, 250), (450, 260), (490, 290)]
    for start, end in zip(points, points[1:]):
        page.draw_line(start, end, color=(0, 0, 0), width=2)
    doc.save(path)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tests/fixtures/generated-math-smoke.pdf")
    create(target)
