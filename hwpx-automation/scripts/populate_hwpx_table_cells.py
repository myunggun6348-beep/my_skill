from __future__ import annotations

import argparse
import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = {
    "ha": "http://www.hancom.co.kr/hwpml/2011/app",
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hp10": "http://www.hancom.co.kr/hwpml/2016/paragraph",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hhs": "http://www.hancom.co.kr/hwpml/2011/history",
    "hm": "http://www.hancom.co.kr/hwpml/2011/master-page",
    "hpf": "http://www.hancom.co.kr/schema/2011/hpf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "opf": "http://www.idpf.org/2007/opf/",
    "ooxmlchart": "http://www.hancom.co.kr/hwpml/2016/ooxmlchart",
    "hwpunitchar": "http://www.hancom.co.kr/hwpml/2016/HwpUnitChar",
    "epub": "http://www.idpf.org/2007/ops",
    "config": "urn:oasis:names:tc:opendocument:xmlns:config:1.0",
}

DEFAULT_TEXT_WIDTH = 39740
TABLE_WIDTH_RATIO = 0.92
MIN_TABLE_WIDTH = 26000
MAX_TABLE_WIDTH = 38000

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def clear_linesegarray(paragraph: ET.Element) -> None:
    for node in list(paragraph):
        if node.tag == qn("hp", "linesegarray"):
            paragraph.remove(node)


def ensure_first_run(paragraph: ET.Element) -> ET.Element:
    runs = paragraph.findall("hp:run", NS)
    if runs:
        return runs[0]
    run = ET.Element(qn("hp", "run"))
    run.set("charPrIDRef", "20")
    paragraph.insert(0, run)
    return run


def set_cell_text(cell: ET.Element, text: str) -> None:
    paragraph = cell.find("hp:subList/hp:p", NS)
    if paragraph is None:
        sub_list = cell.find("hp:subList", NS)
        if sub_list is None:
            sub_list = ET.SubElement(cell, qn("hp", "subList"))
        paragraph = ET.SubElement(sub_list, qn("hp", "p"))

    for run in paragraph.findall("hp:run", NS):
        for child in list(run):
            if child.tag == qn("hp", "t"):
                run.remove(child)

    run = ensure_first_run(paragraph)
    if text:
        text_node = ET.Element(qn("hp", "t"))
        text_node.text = text
        run.append(text_node)

    clear_linesegarray(paragraph)


def infer_text_width(root: ET.Element) -> int:
    widths: list[int] = []
    for lineseg in root.iterfind(".//hp:lineseg", NS):
        horzsize = lineseg.get("horzsize")
        if horzsize and horzsize.isdigit():
            widths.append(int(horzsize))

    if not widths:
        return DEFAULT_TEXT_WIDTH

    return max(widths)


def display_length(text: str) -> int:
    compact = " ".join(text.split())
    if not compact:
        return 0
    return len(compact)


def clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def resolve_min_column_width(column_count: int) -> int:
    if column_count <= 2:
        return 5200
    if column_count == 3:
        return 4200
    if column_count == 4:
        return 3400
    return 2800


def resolve_max_column_share(column_count: int) -> float:
    if column_count <= 2:
        return 0.58
    if column_count == 3:
        return 0.46
    if column_count == 4:
        return 0.36
    return 0.32


def distribute_widths(total_width: int, scores: list[float], min_width: int, max_width: int) -> list[int]:
    column_count = len(scores)
    if column_count == 0:
        return []

    if min_width * column_count > total_width:
        base_width = total_width // column_count
        widths = [base_width] * column_count
        widths[-1] += total_width - sum(widths)
        return widths

    remaining = float(total_width)
    active = set(range(column_count))
    widths: list[float | None] = [None] * column_count

    while active:
        score_sum = sum(scores[index] for index in active)
        changed = False
        for index in list(active):
            proportional = remaining / len(active) if score_sum == 0 else remaining * scores[index] / score_sum
            if proportional < min_width:
                widths[index] = float(min_width)
                remaining -= min_width
                active.remove(index)
                changed = True
            elif proportional > max_width:
                widths[index] = float(max_width)
                remaining -= max_width
                active.remove(index)
                changed = True

        if not changed:
            for index in active:
                widths[index] = remaining / len(active) if score_sum == 0 else remaining * scores[index] / score_sum
            break

    resolved = [width if width is not None else 0.0 for width in widths]
    integer_widths = [int(width) for width in resolved]
    remainder = total_width - sum(integer_widths)
    fractional_order = sorted(
        range(column_count),
        key=lambda index: resolved[index] - integer_widths[index],
        reverse=True,
    )

    for index in fractional_order:
        if remainder <= 0:
            break
        integer_widths[index] += 1
        remainder -= 1

    if remainder != 0:
        integer_widths[-1] += remainder

    return integer_widths


def calculate_column_widths(rows: list[list[str]], text_width: int) -> list[int]:
    if not rows:
        return []

    column_count = len(rows[0])
    max_table_width = max(MIN_TABLE_WIDTH, min(MAX_TABLE_WIDTH, text_width - 800))
    total_width = clamp(int(text_width * TABLE_WIDTH_RATIO), MIN_TABLE_WIDTH, max_table_width)
    min_width = resolve_min_column_width(column_count)
    max_width = int(total_width * resolve_max_column_share(column_count))

    scores: list[float] = []
    for column_index in range(column_count):
        lengths = [display_length(row[column_index]) for row in rows]
        max_length = min(max(lengths, default=0), 42)
        avg_length = min(sum(lengths) / len(lengths), 28) if lengths else 0
        weighted_length = max(8.0, (max_length * 0.7) + (avg_length * 0.3))
        scores.append(weighted_length ** 0.8)

    return distribute_widths(total_width, scores, min_width, max_width)


def apply_table_layout(table_element: ET.Element, widths: list[int]) -> None:
    if not widths:
        return

    total_width = sum(widths)

    table_size = table_element.find("hp:sz", NS)
    if table_size is not None:
        table_size.set("width", str(total_width))

    table_position = table_element.find("hp:pos", NS)
    if table_position is not None:
        table_position.set("horzAlign", "LEFT")
        table_position.set("horzRelTo", "COLUMN")
        table_position.set("vertRelTo", "PARA")

    for tr_element in table_element.findall("hp:tr", NS):
        for cell, width in zip(tr_element.findall("hp:tc", NS), widths):
            cell_size = cell.find("hp:cellSz", NS)
            if cell_size is not None:
                cell_size.set("width", str(width))


def fill_tables(section_xml: bytes, table_specs: list[dict[str, object]]) -> bytes:
    root = ET.fromstring(section_xml)
    tables = list(root.iterfind(".//hp:tbl", NS))
    text_width = infer_text_width(root)
    if len(tables) != len(table_specs):
        raise ValueError(f"Table count mismatch: xml={len(tables)}, spec={len(table_specs)}")

    for table_element, table_spec in zip(tables, table_specs):
        rows: list[list[str]] = table_spec["rows"]  # type: ignore[assignment]
        apply_table_layout(table_element, calculate_column_widths(rows, text_width))
        tr_elements = table_element.findall("hp:tr", NS)
        if len(tr_elements) != len(rows):
            raise ValueError(
                f"Row count mismatch for {table_spec.get('placeholder')}: xml={len(tr_elements)}, spec={len(rows)}"
            )

        for tr_element, row_values in zip(tr_elements, rows):
            cells = tr_element.findall("hp:tc", NS)
            if len(cells) != len(row_values):
                raise ValueError(
                    f"Column count mismatch for {table_spec.get('placeholder')}: xml={len(cells)}, spec={len(row_values)}"
                )
            for cell, text in zip(cells, row_values):
                set_cell_text(cell, text)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Populate existing HWPX table skeletons with cell text.")
    parser.add_argument("--hwpx", required=True, help="Path to the HWPX file containing blank table skeletons.")
    parser.add_argument("--table-json", required=True, help="Path to the JSON table specification file.")
    args = parser.parse_args()

    hwpx_path = Path(args.hwpx)
    table_json_path = Path(args.table_json)

    table_specs = json.loads(table_json_path.read_text(encoding="utf-8"))["tables"]

    with zipfile.ZipFile(hwpx_path, "r") as source_zip:
        section_xml = source_zip.read("Contents/section0.xml")
        updated_section_xml = fill_tables(section_xml, table_specs)

        tmp_path = hwpx_path.with_suffix(hwpx_path.suffix + ".tmp")
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
            for info in source_zip.infolist():
                data = source_zip.read(info.filename)
                if info.filename == "Contents/section0.xml":
                    data = updated_section_xml
                target_zip.writestr(info, data)

    tmp_path.replace(hwpx_path)


if __name__ == "__main__":
    main()
