from __future__ import annotations

import copy
import hashlib
import math
import os
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree as ET

from common import read_json
from math_to_hwp import braces_balanced, contains_math_marker, is_formula_candidate, latex_to_hwp

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "opf": "http://www.idpf.org/2007/opf/",
}
ENCODED_MATH = re.compile(r"^(EH|HYhwpEQ|HwpEQ)|symbol", re.I)


def units(points: float) -> int:
    return round(points * 100)


def checked_bbox(values, width: float, height: float) -> list[float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError("A bounding box must contain four PDF-point coordinates")
    box = [float(value) for value in values]
    if not all(math.isfinite(value) for value in box):
        raise ValueError("Bounding box contains a non-finite coordinate")
    if not (0 <= box[0] < box[2] <= width and 0 <= box[1] < box[3] <= height):
        raise ValueError(f"Bounding box is outside the page: {box}")
    return box


def intersects(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def readable(char: str) -> bool:
    return char.isprintable() and not (0xE000 <= ord(char) <= 0xF8FF) and char != "\ufffd"


def glyph_inside(char, box):
    x0, y0, x1, y1 = char['bbox']
    # Font boxes can overlap adjacent prose; classify by the glyph's center.
    return box[0] <= (x0 + x1) / 2 <= box[2] and box[1] <= (y0 + y1) / 2 <= box[3]


def _groups(chars, excluded_boxes=()):
    group = []
    for char in chars:
        if readable(char["c"]) and not any(glyph_inside(char, box) for box in excluded_boxes):
            group.append(char)
        elif group:
            yield group
            group = []
    if group:
        yield group


def _union(rectangles):
    return [min(r[0] for r in rectangles), min(r[1] for r in rectangles),
            max(r[2] for r in rectangles), max(r[3] for r in rectangles)]


def extract_fidelity(pdf_path: Path, asset_dir: Path, config: dict) -> dict:
    import pymupdf as fitz

    asset_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    overrides_path = config.get("layout", {}).get("overrides")
    overrides = read_json(Path(overrides_path)) if overrides_path else {}
    if overrides and overrides.get("source_sha256") != digest:
        raise ValueError("Layout overrides must contain the matching source_sha256")
    override_pages = {int(item["page"]): item for item in overrides.get("pages", [])}
    if len(override_pages) != len(overrides.get("pages", [])):
        raise ValueError("Duplicate override page numbers")
    dpi = int(config.get("pdf", {}).get("render_dpi", 300))
    if not 72 <= dpi <= 600:
        raise ValueError("render_dpi must be between 72 and 600")
    result = {"source": str(pdf_path.resolve()), "source_sha256": digest, "mode": "fidelity", "pages": []}
    with fitz.open(pdf_path) as document:
        if any(number < 1 or number > len(document) for number in override_pages):
            raise ValueError("Override page number is outside the PDF")
        for index, original in enumerate(document):
            if original.rotation:
                working = fitz.open()
                page = working.new_page(width=original.rect.width, height=original.rect.height)
                page.show_pdf_page(page.rect, document, index)
            else:
                working = fitz.open()
                working.insert_pdf(document, from_page=index, to_page=index)
                page = working[0]
            width, height = page.rect.width, page.rect.height
            page_override = override_pages.get(index + 1, {})
            if original.rotation and page_override.get("equations"):
                raise ValueError("Normalize rotated pages before adding verified equation overrides")
            exclusions = [checked_bbox(box, width, height) for box in page_override.get("keep_image_regions", [])]
            equations = []
            for item in page_override.get("equations", []):
                box = checked_bbox(item.get("bbox"), width, height)
                if item.get("verified") is not True:
                    raise ValueError("An equation override must explicitly be verified")
                command = item.get("hwp_command") or latex_to_hwp(item.get("latex", ""))
                if not command.strip() or not braces_balanced(command):
                    raise ValueError("Invalid verified equation command")
                size = float(item.get("font_size_pt", 10))
                if not math.isfinite(size) or not 1 <= size <= 100:
                    raise ValueError("Invalid equation font size")
                if any(intersects(box, e["bbox"]) for e in equations):
                    raise ValueError("Verified equation regions overlap")
                if any(intersects(box, region) for region in exclusions):
                    raise ValueError("Verified equations overlap keep-image regions")
                raster = any(intersects(box, image["bbox"]) for image in page.get_image_info())
                if raster and item.get("replace_raster") is not True:
                    raise ValueError("A verified equation overlaps raster content that text redaction cannot remove")
                background_color = item.get("background_color")
                if item.get("replace_raster") is True and not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(background_color)):
                    raise ValueError("Raster replacement requires a verified solid background_color (#RRGGBB)")
                color = item.get("color", 0)
                if type(color) is not int or not 0 <= color <= 0xFFFFFF:
                    raise ValueError("Invalid equation color")
                equations.append({"kind": "equation", "page": index + 1, "bbox": box,
                                  "hwp_command": command, "font_size_pt": size, "confidence": 1.0, "color": color,
                                  "replace_raster": item.get("replace_raster") is True,
                                  "background_color": background_color,
                                  "evidence": "Verified source-bound layout override"})
            elements = []
            reviews = []
            redactions = []
            for block in page.get_text("rawdict")["blocks"]:
                for line in block.get("lines", []):
                    direction = line.get("dir", (1, 0))
                    for span in line["spans"]:
                        chars = span.get("chars", [])
                        raw_text = "".join(char["c"] for char in chars)
                        if not raw_text.strip():
                            continue
                        box = list(span["bbox"])
                        # A formula can occupy only part of a prose span; retain its other glyphs.
                        chars = [char for char in chars if not any(glyph_inside(char, e["bbox"]) for e in equations)]
                        if not chars:
                            continue
                        if not ENCODED_MATH.search(span["font"]):
                            chars = [char for char in chars if not any(intersects(char["bbox"], region) for region in exclusions)]
                        if not chars:
                            continue
                        raw_text = "".join(char["c"] for char in chars)
                        if not raw_text.strip():
                            continue
                        box = _union([char["bbox"] for char in chars])
                        reason = ""
                        if original.rotation:
                            reason = "Rotated PDF page retained as visible source image"
                        elif ENCODED_MATH.search(span["font"]):
                            reason = "Legacy/symbol math font: retained visibly in the source background"
                        elif (re.search(r"title|display", span["font"], re.I) or span["size"] >= 20) and span["font"] not in config.get("layout", {}).get("font_map", {}):
                            reason = "Unmapped display typography retained to preserve original appearance"
                        elif abs(direction[0] - 1) > 0.001 or abs(direction[1]) > 0.001:
                            reason = "Rotated text retained visibly in the source background"
                        if reason:
                            reviews.append({"kind": "review", "page": index + 1, "bbox": box,
                                            "text": raw_text, "font": span["font"], "reason": reason,
                                            "requires_equation": bool(ENCODED_MATH.search(span["font"]) or is_formula_candidate(raw_text))})
                            continue
                        if any(not readable(char["c"]) and not char["c"].isspace() and ord(char["c"]) >= 32 for char in chars):
                            reviews.append({"kind": "review", "page": index + 1, "bbox": box,
                                            "reason": "Non-Unicode glyphs require visual classification or native equations",
                                            "requires_equation": True})
                        for group in _groups(span.get("chars", []), exclusions + [e["bbox"] for e in equations]):
                            text = "".join(char["c"] for char in group)
                            if not text.strip():
                                continue
                            group_box = _union([char["bbox"] for char in group])
                            if not (0 <= group_box[0] < group_box[2] <= width and 0 <= group_box[1] < group_box[3] <= height):
                                reviews.append({"kind": "review", "page": index + 1, "bbox": group_box,
                                                "reason": "Text outside paper bounds retained in background"})
                                continue
                            element = {"kind": "text", "page": index + 1, "bbox": group_box,
                                       "origin": list(group[0]["origin"]), "text": text,
                                       "font": span["font"], "font_size_pt": span["size"],
                                       "color": span["color"], "flags": span["flags"], "confidence": 1.0}
                            if is_formula_candidate(text):
                                try:
                                    element.update(kind="equation", hwp_command=latex_to_hwp(text))
                                except ValueError:
                                    reviews.append({"kind": "review", "page": index + 1, "bbox": group_box,
                                                    "reason": "Unsupported formula requires a verified native equation",
                                                    "requires_equation": True})
                            elif contains_math_marker(text):
                                reviews.append({"kind": "review", "page": index + 1, "bbox": group_box,
                                                "text": text,
                                                "reason": "Mixed prose/math requires verified equation-only regions; preserve surrounding prose as text",
                                                "requires_equation": True})
                            elements.append(element)
                            for char in group:
                                x0, y0, x1, y1 = char["bbox"]
                                if char["c"].strip():
                                    redactions.append([x0 + 0.15, (y0 + y1) / 2 - 0.05,
                                                       x1 - 0.15, (y0 + y1) / 2 + 0.05])
            for box in redactions:
                if box[0] < box[2]:
                    page.add_redact_annot(fitz.Rect(box), fill=False, cross_out=False)
            if redactions:
                page.apply_redactions(images=0, graphics=0, text=0)
            for equation in equations:
                page.add_redact_annot(fitz.Rect(equation["bbox"]), fill=False, cross_out=False)
            if equations:
                # Remove fraction/root strokes only when entirely contained by a verified formula region.
                page.apply_redactions(images=0, graphics=1, text=0)
            background = asset_dir / f"page-{index + 1:03d}-background.png"
            background_page = original if original.rotation else page
            background_page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False).save(background)
            raster_equations = [e for e in equations if e["replace_raster"]]
            if raster_equations:
                from PIL import Image, ImageDraw
                with Image.open(background) as image:
                    draw = ImageDraw.Draw(image)
                    for equation in raster_equations:
                        x0, y0, x1, y1 = equation["bbox"]
                        draw.rectangle((math.floor(x0 * dpi / 72), math.floor(y0 * dpi / 72),
                                        math.ceil(x1 * dpi / 72) - 1, math.ceil(y1 * dpi / 72) - 1),
                                       fill=equation["background_color"])
                    image.save(background)
            source_render = asset_dir / f"page-{index + 1:03d}-source.png"
            original.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False).save(source_render)
            if not elements and not equations:
                reviews.append({"kind": "review", "page": index + 1, "bbox": [0, 0, width, height],
                                "reason": "Page preserved as image; no reliable editable text layer"})
            elements.extend(equations)
            elements.sort(key=lambda e: (e["bbox"][1], e["bbox"][0]))
            result["pages"].append({"page": index + 1, "width_pt": width, "height_pt": height,
                                    "background": str(background.resolve()), "source_render": str(source_render.resolve()),
                                    "elements": elements, "reviews": reviews,
                                    "math_audit": page_override.get("math_audit", {})})
            working.close()
    result["page_count"] = len(result["pages"])
    return result


def _tag(prefix: str, name: str) -> str:
    return f"{{{NS[prefix]}}}{name}"


def _identity(shape, number: int, z: int) -> None:
    shape.set("id", str(100000 + number))
    shape.set("instid", str(200000 + number))
    shape.set("zOrder", str(z))


def _position(shape, x: float, y: float, width: float, height: float) -> None:
    pos = shape.find("hp:pos", NS)
    pos.attrib.update(dict(treatAsChar="0", flowWithText="0", allowOverlap="1", affectLSpacing="0",
                      vertRelTo="PAPER", horzRelTo="PAPER", vertAlign="TOP", horzAlign="LEFT",
                      horzOffset=str(units(x)), vertOffset=str(units(y))))
    shape.set("textWrap", "IN_FRONT_OF_TEXT")
    size = shape.find("hp:sz", NS)
    size.attrib.update(dict(width=str(units(width)), height=str(units(height)), protect="1"))
    margin = shape.find("hp:outMargin", NS)
    for key in ("left", "right", "top", "bottom"):
        margin.set(key, "0")


def _font_info(element, config):
    source = element.get("font", "")
    fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    mapping = config.get("layout", {}).get("font_map", {})
    if source in mapping:
        item = mapping[source]
        return item["face"], Path(item["file"])
    gothic = bool(re.search(r"go(?:std)?|gothic|sans|title|din|bold", source, re.I))
    if gothic:
        return "맑은 고딕", fonts / "malgun.ttf"
    return "HY신명조", fonts / "H2MJSM.TTF"


def _picture(page, binary_id):
    from PIL import Image

    width, height = units(page["width_pt"]), units(page["height_pt"])
    with Image.open(page["background"]) as image:
        pixel_width, pixel_height = image.size
    shape = ET.Element(_tag("hp", "pic"), id="0", zOrder="0", numberingType="PICTURE",
                       textWrap="BEHIND_TEXT", textFlow="BOTH_SIDES", lock="0", dropcapstyle="None",
                       href="", groupLevel="0", instid="0", reverse="0")
    ET.SubElement(shape, _tag("hp", "offset"), x="0", y="0")
    ET.SubElement(shape, _tag("hp", "orgSz"), width=str(width), height=str(height))
    ET.SubElement(shape, _tag("hp", "curSz"), width="0", height="0")
    ET.SubElement(shape, _tag("hp", "flip"), horizontal="0", vertical="0")
    ET.SubElement(shape, _tag("hp", "rotationInfo"), angle="0", centerX=str(width // 2), centerY=str(height // 2), rotateimage="1")
    info = ET.SubElement(shape, _tag("hp", "renderingInfo"))
    for name in ("transMatrix", "scaMatrix", "rotMatrix"):
        ET.SubElement(info, _tag("hc", name), e1="1", e2="0", e3="0", e4="0", e5="1", e6="0")
    ET.SubElement(shape, _tag("hc", "img"), binaryItemIDRef=binary_id, bright="0", contrast="0", effect="REAL_PIC", alpha="0")
    rectangle = ET.SubElement(shape, _tag("hp", "imgRect"))
    for name, x, y in [("pt0", 0, 0), ("pt1", width, 0), ("pt2", width, height), ("pt3", 0, height)]:
        ET.SubElement(rectangle, _tag("hc", name), x=str(x), y=str(y))
    ET.SubElement(shape, _tag("hp", "imgClip"), left="0", right=str(pixel_width * 75), top="0", bottom=str(pixel_height * 75))
    ET.SubElement(shape, _tag("hp", "inMargin"), left="0", right="0", top="0", bottom="0")
    ET.SubElement(shape, _tag("hp", "imgDim"), dimwidth=str(pixel_width * 75), dimheight=str(pixel_height * 75))
    ET.SubElement(shape, _tag("hp", "effects"))
    ET.SubElement(shape, _tag("hp", "sz"), width=str(width), widthRelTo="ABSOLUTE", height=str(height), heightRelTo="ABSOLUTE", protect="0")
    ET.SubElement(shape, _tag("hp", "pos"), treatAsChar="0", affectLSpacing="0", flowWithText="0", allowOverlap="1",
                  holdAnchorAndSO="0", vertRelTo="PAPER", horzRelTo="PAPER", vertAlign="TOP", horzAlign="LEFT", vertOffset="0", horzOffset="0")
    ET.SubElement(shape, _tag("hp", "outMargin"), left="0", right="0", top="0", bottom="0")
    ET.SubElement(shape, _tag("hp", "shapeComment")).text = "Source visual regions; editable text has been removed from this image"
    return shape


def build_fidelity(analysis: dict, output: Path, config: dict) -> dict:
    import pymupdf as fitz
    from validate_output import equation_issues

    issues = equation_issues(analysis, config)
    if issues:
        raise ValueError("Native equation reconstruction is incomplete: " + "; ".join(issues))

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(__file__).resolve().parent.parent / "assets" / "canvas-template.hwpx"
    parser = ET.XMLParser(resolve_entities=False, no_network=True)
    with zipfile.ZipFile(temporary) as archive:
        contents = {name: archive.read(name) for name in archive.namelist()}
    section = ET.fromstring(contents["Contents/section0.xml"], parser)
    header = ET.fromstring(contents["Contents/header.xml"], parser)
    manifest = ET.fromstring(contents["Contents/content.hpf"], parser)
    rectangle = section.find(".//hp:rect", NS)
    native_equation = section.find(".//hp:equation", NS)
    first_para = section.find("hp:p", NS)
    section_properties = first_para.find("hp:run", NS)
    char_properties = header.find("hh:refList/hh:charProperties", NS)
    para_properties = header.find("hh:refList/hh:paraProperties", NS)
    plain_para = copy.deepcopy(para_properties.find("hh:paraPr", NS))
    plain_para_id = len(para_properties)
    plain_para.set("id", str(plain_para_id))
    plain_para.find("hh:align", NS).set("horizontal", "LEFT")
    for node in plain_para.findall(".//hc:intent", NS) + plain_para.findall(".//hc:left", NS) + plain_para.findall(".//hc:right", NS):
        node.set("value", "0")
    para_properties.append(plain_para)
    para_properties.set("itemCnt", str(len(para_properties)))
    fontfaces = header.find("hh:refList/hh:fontfaces", NS)
    font_cache = {}
    style_cache = {}
    substitutions = {}
    font_measures = {}
    shape_number = 0
    inserted = {"text": 0, "equation": 0, "image": len(analysis["pages"])}

    def font_id(face):
        if face not in font_cache:
            ids = {}
            for family in fontfaces:
                match = next((f for f in family if f.get("face") == face), None)
                if match is None:
                    match = copy.deepcopy(family[0])
                    match.set("id", str(len(family)))
                    match.set("face", face)
                    family.append(match)
                    family.set("fontCnt", str(len(family)))
                ids[family.get("lang").lower()] = match.get("id")
            font_cache[face] = ids
        return font_cache[face]

    def text_style(element):
        face, fontfile = _font_info(element, config)
        substitutions[element.get("font", "")] = face
        size = float(element["font_size_pt"])
        ratio = 100
        if fontfile.is_file():
            if str(fontfile) not in font_measures:
                font_measures[str(fontfile)] = fitz.Font(fontfile=str(fontfile))
            width = font_measures[str(fontfile)].text_length(element["text"], fontsize=size)
            if width:
                ratio = max(50, min(200, round(100 * (element["bbox"][2] - element["bbox"][0]) / width)))
        key = (face, round(size * 100), element.get("color", 0), bool(element.get("flags", 0) & 16), ratio)
        if key not in style_cache:
            style = copy.deepcopy(char_properties[0])
            identifier = str(len(char_properties))
            style.attrib.update(dict(id=identifier, height=str(key[1]), textColor=f"#{key[2]:06X}"))
            style.find("hh:fontRef", NS).attrib.update(font_id(face))
            for lang in style.find("hh:ratio", NS).attrib:
                style.find("hh:ratio", NS).set(lang, str(ratio))
            for spacing in style.find("hh:spacing", NS).attrib:
                style.find("hh:spacing", NS).set(spacing, "0")
            if key[3] and style.find("hh:bold", NS) is None:
                ET.SubElement(style, _tag("hh", "bold"))
            char_properties.append(style)
            style_cache[key] = identifier
        return style_cache[key]

    sections = []
    for index, page in enumerate(analysis["pages"]):
        new_section = ET.Element(section.tag, nsmap=section.nsmap)
        paragraph = copy.deepcopy(first_para)
        for child in list(paragraph):
            paragraph.remove(child)
        paragraph.set("id", str(300000 + index))
        paragraph.set("paraPrIDRef", str(plain_para_id))
        properties = copy.deepcopy(section_properties)
        for child in list(properties):
            if child.tag not in {_tag("hp", "secPr"), _tag("hp", "ctrl")}:
                properties.remove(child)
        page_properties = properties.find("hp:secPr/hp:pagePr", NS)
        page_properties.set("width", str(units(page["width_pt"])))
        page_properties.set("height", str(units(page["height_pt"])))
        page_properties.set("landscape", "WIDELY")
        for attribute in page_properties.find("hp:margin", NS).attrib:
            page_properties.find("hp:margin", NS).set(attribute, "0")
        paragraph.append(properties)
        background = _picture(page, f"background{index}")
        contents[f"BinData/background{index}.png"] = Path(page["background"]).read_bytes()
        _identity(background, shape_number, 0)
        shape_number += 1
        _position(background, 0, 0, page["width_pt"], page["height_pt"])
        background.set("textWrap", "BEHIND_TEXT")
        run = ET.SubElement(paragraph, _tag("hp", "run"), charPrIDRef="0")
        run.append(background)
        for element in page["elements"]:
            shape_number += 1
            x0, y0, x1, y1 = element["bbox"]
            if element["kind"] == "equation":
                shape = copy.deepcopy(native_equation)
                shape.find("hp:script", NS).text = element["hwp_command"]
                shape.set("baseUnit", str(units(element.get("font_size_pt", 10))))
                shape.set("textColor", f"#{element.get('color', 0):06X}")
                _identity(shape, shape_number, shape_number)
                _position(shape, x0, y0, x1 - x0, y1 - y0)
                inserted["equation"] += 1
            else:
                shape = copy.deepcopy(rectangle)
                _identity(shape, shape_number, shape_number)
                size = element["font_size_pt"]
                origin = element.get("origin", [x0, y0 + size * .85])
                height = max(y1 - y0, size * 1.8)
                top = max(0, origin[1] - size * .85)
                box_width = min(page["width_pt"] - x0, x1 - x0 + size * .5)
                _position(shape, x0, top, box_width, height)
                for tag in ("hp:orgSz", "hp:curSz"):
                    shape.find(tag, NS).attrib.update(dict(width=str(units(box_width)), height=str(units(height))))
                shape.find("hp:rotationInfo", NS).attrib.update(dict(angle="0", centerX=str(units(box_width / 2)), centerY=str(units(height / 2))))
                for matrix in shape.find("hp:renderingInfo", NS):
                    matrix.attrib.update(dict(e1="1", e2="0", e3="0", e4="0", e5="1", e6="0"))
                shape.find("hp:lineShape", NS).set("style", "NONE")
                shape.find("hc:fillBrush/hc:winBrush", NS).set("faceColor", "none")
                for tag, x, y in [("pt0", 0, 0), ("pt1", box_width, 0), ("pt2", box_width, height), ("pt3", 0, height)]:
                    shape.find("hc:" + tag, NS).attrib.update(dict(x=str(units(x)), y=str(units(y))))
                draw = shape.find("hp:drawText", NS)
                draw.set("lastWidth", str(units(box_width)))
                for key in draw.find("hp:textMargin", NS).attrib:
                    draw.find("hp:textMargin", NS).set(key, "0")
                sublist = draw.find("hp:subList", NS)
                sublist.set("vertAlign", "TOP")
                sublist.set("lineWrap", "SQUEEZE")
                text_paragraph = sublist.find("hp:p", NS)
                text_paragraph.set("id", str(400000 + shape_number))
                text_paragraph.set("paraPrIDRef", str(plain_para_id))
                for child in list(text_paragraph):
                    text_paragraph.remove(child)
                text_run = ET.SubElement(text_paragraph, _tag("hp", "run"), charPrIDRef=text_style(element))
                ET.SubElement(text_run, _tag("hp", "t")).text = element["text"]
                inserted["text"] += 1
            ET.SubElement(paragraph, _tag("hp", "run"), charPrIDRef="0").append(shape)
        ET.SubElement(ET.SubElement(paragraph, _tag("hp", "run"), charPrIDRef="0"), _tag("hp", "t"))
        new_section.append(paragraph)
        sections.append(ET.tostring(new_section, encoding="UTF-8", xml_declaration=True))
    header.set("secCnt", str(len(sections)))
    char_properties.set("itemCnt", str(len(char_properties)))
    items = manifest.find("opf:manifest", NS)
    spine = manifest.find("opf:spine", NS)
    for item in list(items):
        if item.get("id", "").startswith("section"):
            items.remove(item)
    for item in list(spine):
        if item.get("idref", "").startswith("section"):
            spine.remove(item)
    for index in range(len(sections)):
        ET.SubElement(items, _tag("opf", "item"), id=f"background{index}", href=f"BinData/background{index}.png", **{"media-type": "image/png", "isEmbeded": "1"})
        ET.SubElement(items, _tag("opf", "item"), id=f"section{index}", href=f"Contents/section{index}.xml", **{"media-type": "application/xml"})
        ET.SubElement(spine, _tag("opf", "itemref"), idref=f"section{index}", linear="yes")
    contents["Contents/header.xml"] = ET.tostring(header, encoding="UTF-8", xml_declaration=True)
    contents["Contents/content.hpf"] = ET.tostring(manifest, encoding="UTF-8", xml_declaration=True)
    contents.pop("Preview/PrvText.txt", None)
    contents.pop("Preview/PrvImage.png", None)
    for name in list(contents):
        if name.startswith("Contents/section") and name.endswith(".xml"):
            contents.pop(name)
    for index, data in enumerate(sections):
        contents[f"Contents/section{index}.xml"] = data
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data, compress_type=zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED)
    print("[fidelity] Opening positioned HWPX", file=sys.stderr, flush=True)
    from native_export import export_native
    result = {"inserted": inserted, "font_substitutions": substitutions,
              "layout": "Original paper sizes, page coordinates, visible backgrounds and editable text boxes"}
    try:
        result.update(export_native(output, config.get("hwp", {})))
    except (RuntimeError, ImportError) as exc:
        result.update(error=str(exc), rendered_pdf="", reopened_in_hangul=False)
    return result
