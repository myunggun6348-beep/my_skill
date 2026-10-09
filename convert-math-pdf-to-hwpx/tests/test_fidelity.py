import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pymupdf as fitz
import pytest
from lxml import etree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from preserve_layout import NS, _groups, build_fidelity, checked_bbox, extract_fidelity
from validate_output import compare_pages, equation_issues, validate


def test_overlapping_font_boxes_do_not_swallow_adjacent_prose():
    chars = [{'c': 'x', 'bbox': [0, 0, 5, 10]}, {'c': '축', 'bbox': [4.8, 0, 15, 10]}]
    assert [[c['c'] for c in group] for group in _groups(chars, [[0, 0, 5, 10]])] == [['축']]


def test_coordinate_package_and_native_objects(tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    first = document.new_page(width=420, height=600)
    first.insert_text((40, 80), "Source heading", fontsize=16, color=(0, .4, .2))
    first.insert_text((40, 120), "a=1", fontsize=12)
    first.draw_rect((35, 100, 200, 150), color=(.8, 0, 0))
    second = document.new_page(width=600, height=420)
    second.insert_text((300, 90), "Right column", fontsize=11)
    document.save(source)
    document.close()
    config = {"pdf": {"render_dpi": 72}}
    audits = tmp_path / "audits.json"
    audits.write_text(json.dumps({"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "pages": [
        {"page": 1, "math_audit": {"verified": True, "formula_count": 1}},
        {"page": 2, "math_audit": {"verified": True, "formula_count": 0}},
    ]}), encoding="utf-8")
    config["layout"] = {"overrides": str(audits)}
    analysis = extract_fidelity(source, tmp_path / "assets", config)
    assert [(p["width_pt"], p["height_pt"]) for p in analysis["pages"]] == [(420, 600), (600, 420)]
    assert [e["kind"] for e in analysis["pages"][0]["elements"]] == ["text", "equation"]
    assert analysis["pages"][1]["elements"][0]["bbox"][0] == 300

    def fake_export(output, config):
        # Package-only check; real Hancom rendering is a separate integration gate.
        rendered = output.with_suffix(".rendered.pdf")
        rendered.write_bytes(source.read_bytes())
        return {"rendered_pdf": str(rendered), "reopened_in_hangul": True}

    monkeypatch.setattr("native_export.export_native", fake_export)
    output = tmp_path / "output.hwpx"
    build = build_fidelity(analysis, output, config)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.read("mimetype") == b"application/hwp+zip"
        for index, page in enumerate(analysis["pages"]):
            root = ET.fromstring(archive.read(f"Contents/section{index}.xml"))
            paper = root.find(".//hp:pagePr", NS)
            assert int(paper.get("width")) == round(page["width_pt"] * 100)
            assert int(paper.get("height")) == round(page["height_pt"] * 100)
            assert root.find(".//hp:pic/hp:pos", NS).get("vertRelTo") == "PAPER"
        root = ET.fromstring(archive.read("Contents/section0.xml"))
        assert root.find(".//hp:equation/hp:script", NS).text == "a=1"
        assert root.find(".//hp:drawText//hp:t", NS).text == "Source heading"
    report = validate(analysis, output, build, config)
    assert report["failures"] == []
    assert report["editable_text_coverage"] == 1
    assert report["native_counts"] == {"equation": 1, "image": 2, "text_box": 2, "table": 0}
    assert report["all_equations_native"] is True
    tampered = tmp_path / "tampered.hwpx"
    with zipfile.ZipFile(output) as original, zipfile.ZipFile(tampered, "w") as changed:
        for name in original.namelist():
            data = original.read(name)
            if name == "Contents/section0.xml":
                root = ET.fromstring(data)
                root.find(".//hp:equation/hp:script", NS).text = "a=99"
                data = ET.tostring(root)
            changed.writestr(name, data)
    assert "Native equation scripts differ from the verified source formulas" in validate(analysis, tampered, build, config)["failures"]
    missing = validate(analysis, output, {}, config)
    assert missing["status"] == "failed"
    def failed_export(output, config):
        raise RuntimeError("approval timeout")
    monkeypatch.setattr("native_export.export_native", failed_export)
    failed = build_fidelity(analysis, output, config)
    assert failed["reopened_in_hangul"] is False
    assert zipfile.is_zipfile(output)
    assert "approval timeout" in validate(analysis, output, failed, config)["failures"]


def test_overrides_are_source_bound_and_checked(tmp_path):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page(width=200, height=300).insert_text((20, 40), "x=2")
    document.save(source)
    document.close()
    overrides = tmp_path / "overrides.json"
    data = {"source_sha256": "stale", "pages": []}
    overrides.write_text(json.dumps(data), encoding="utf-8")
    config = {"layout": {"overrides": str(overrides)}, "pdf": {"render_dpi": 72}}
    with pytest.raises(ValueError, match="source_sha256"):
        extract_fidelity(source, tmp_path / "assets", config)
    data["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    data["pages"] = [{"page": 1, "equations": [{"bbox": [19, 25, 50, 44], "hwp_command": "x=2", "verified": False}]}]
    overrides.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="verified"):
        extract_fidelity(source, tmp_path / "assets", config)
    data["pages"][0]["equations"][0]["verified"] = True
    overrides.write_text(json.dumps(data), encoding="utf-8")
    analysis = extract_fidelity(source, tmp_path / "assets", config)
    assert [e["kind"] for e in analysis["pages"][0]["elements"]] == ["equation"]
    for bbox in ([0, 0, 0, 1], [0, 0, 201, 1], [0, 0, float("nan"), 1]):
        with pytest.raises(ValueError):
            checked_bbox(bbox, 200, 300)


def test_scan_rotation_and_visual_mismatch(tmp_path):
    source = tmp_path / "source.pdf"
    document = fitz.open()
    document.new_page(width=200, height=300).draw_circle((80, 90), 25)
    page = document.new_page(width=200, height=300)
    page.insert_text((20, 60), "Rotated")
    page.set_rotation(90)
    document.save(source)
    document.close()
    analysis = extract_fidelity(source, tmp_path / "assets", {"pdf": {"render_dpi": 72}})
    assert analysis["pages"][0]["reviews"]
    assert analysis["pages"][1]["width_pt"] == 300
    assert analysis["pages"][1]["height_pt"] == 200
    assert compare_pages(source, source, tmp_path / "same", {"comparison_dpi": 72})["passed"]
    blank = fitz.open()
    blank.new_page(width=200, height=300)
    blank.new_page(width=300, height=200)
    wrong = tmp_path / "blank.pdf"
    blank.save(wrong)
    blank.close()
    assert not compare_pages(source, wrong, tmp_path / "wrong", {"comparison_dpi": 72})["passed"]


def test_blank_and_reflow_analysis(tmp_path):
    from extract_layout import extract_layout

    source = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page(width=200, height=300)
    document.save(source)
    document.close()
    assert compare_pages(source, source, tmp_path / "blank-comparison", {"comparison_dpi": 72})["passed"]
    analysis = extract_layout(source, tmp_path / "assets", {"pipeline": {"mode": "editable"}, "pdf": {"render_dpi": 72}})
    assert analysis["mode"] == "editable"
    assert analysis["pages"][0]["elements"][0]["kind"] == "review"
    assert validate(analysis, None)["status"] == "needs-review"


def test_all_equations_gate_and_inline_override(tmp_path):
    source = tmp_path / "inline.pdf"
    document = fitz.open()
    page = document.new_page(width=200, height=300)
    page.insert_text((20, 40), "Left x=2 Right", fontsize=12)
    chars = page.get_text("rawdict")["blocks"][0]["lines"][0]["spans"][0]["chars"]
    box = list(fitz.Rect(chars[5]["bbox"]) | fitz.Rect(chars[7]["bbox"]))
    document.save(source)
    document.close()
    config = {"pdf": {"render_dpi": 72}}
    initial = extract_fidelity(source, tmp_path / "initial", config)
    assert any(r.get('requires_equation') and 'Mixed prose/math' in r['reason'] for r in initial['pages'][0]['reviews'])
    assert "math_audit" in equation_issues(initial)[0]
    with pytest.raises(ValueError, match="reconstruction is incomplete"):
        build_fidelity(initial, tmp_path / "must-not-build.hwpx", config)
    assert not (tmp_path / "must-not-build.hwpx").exists()
    overrides = tmp_path / "inline.json"
    overrides.write_text(json.dumps({"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "pages": [{
        "page": 1, "math_audit": {"verified": True, "formula_count": 1},
        "equations": [{"bbox": box, "verified": True, "hwp_command": "x=2", "color": 0x008000}],
    }]}), encoding="utf-8")
    config["layout"] = {"overrides": str(overrides)}
    analysis = extract_fidelity(source, tmp_path / "converted", config)
    elements = analysis["pages"][0]["elements"]
    assert [e["text"].strip() for e in elements if e["kind"] == "text"] == ["Left", "Right"]
    assert next(e for e in elements if e["kind"] == "equation")["color"] == 0x008000
    assert equation_issues(analysis) == []
    analysis["pages"][0]["math_audit"]["formula_count"] = 2
    assert "2 source formulas but 1 native equations" in equation_issues(analysis)[0]
    analysis["pages"][0]["math_audit"]["formula_count"] = 1
    analysis["pages"][0]["reviews"].append({"requires_equation": True})
    assert "still need native equations" in equation_issues(analysis)[0]


def test_english_labels_and_ambiguous_letters_remain_text(tmp_path):
    source = tmp_path / 'labels.pdf'
    doc = fitz.open()
    page = doc.new_page(width=300, height=300)
    labels = ['Note', 'Example', 'Solution', 'EBS', 'www.ebsi.co.kr/math_x=2', 'teacher_x@example.com', 'A', 'I', 'O', '1']
    for i, label in enumerate(labels):
        page.insert_text((20, 20+i*20), label, fontsize=10)
    page.insert_text((20, 250), 'sin x', fontsize=10)
    doc.save(source)
    doc.close()
    result = extract_fidelity(source, tmp_path / 'assets', {'pdf': {'render_dpi': 72}})
    elements = result['pages'][0]['elements']
    assert [e['text'] for e in elements if e['kind'] == 'text'] == labels
    assert [e['hwp_command'] for e in elements if e['kind'] == 'equation'] == ['sin x']
    assert not result['pages'][0]['reviews']


def test_verified_scan_formula_replacement(tmp_path):
    from PIL import Image

    original = fitz.open()
    page = original.new_page(width=200, height=300)
    page.insert_text((20, 40), "x=2", fontsize=12)
    page.draw_line((100, 70), (150, 70), color=(0, 0, 0))
    scan = page.get_pixmap(alpha=False).tobytes("png")
    original.close()
    document = fitz.open()
    page = document.new_page(width=200, height=300)
    page.insert_image(page.rect, stream=scan)
    source = tmp_path / "scan.pdf"
    document.save(source)
    document.close()
    override = {"bbox": [18, 25, 46, 45], "verified": True, "hwp_command": "x=2"}
    data = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "pages": [{
        "page": 1, "math_audit": {"verified": True, "formula_count": 1}, "equations": [override],
    }]}
    overrides = tmp_path / "scan.json"
    config = {"layout": {"overrides": str(overrides)}, "pdf": {"render_dpi": 72}}
    overrides.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="raster content"):
        extract_fidelity(source, tmp_path / "assets", config)
    override["replace_raster"] = True
    overrides.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="background_color"):
        extract_fidelity(source, tmp_path / "assets", config)
    override["background_color"] = "#FFFFFF"
    overrides.write_text(json.dumps(data), encoding="utf-8")
    analysis = extract_fidelity(source, tmp_path / "assets", config)
    assert equation_issues(analysis) == []
    with Image.open(analysis["pages"][0]["background"]) as image:
        assert image.crop((18, 25, 46, 45)).getextrema() == ((255, 255),) * 3
        assert image.getpixel((125, 70)) != (255, 255, 255)
