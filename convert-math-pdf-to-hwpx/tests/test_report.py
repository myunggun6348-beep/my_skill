import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_output import validate, write_reports


def test_review_report(tmp_path):
    analysis = {
        "source": "sample.pdf",
        "page_count": 1,
        "pages": [{"page": 1, "elements": [{"kind": "review", "page": 1, "bbox": [0, 0, 10, 10], "reason": "low confidence"}]}],
    }
    report = validate(analysis, None)
    assert report["status"] == "needs-review"
    json_path, html_path = write_reports(report, tmp_path)
    assert json_path.exists() and html_path.exists()
    assert "low confidence" in html_path.read_text(encoding="utf-8")

