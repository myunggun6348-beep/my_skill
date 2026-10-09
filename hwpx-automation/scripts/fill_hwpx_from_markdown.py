from __future__ import annotations

import argparse
import copy
import json
import re
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

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


def qn(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(paragraph.itertext()).strip()


def split_markdown_table_row(line: str) -> list[str]:
    parts = [part.strip() for part in line.strip().strip("|").split("|")]
    return parts


def sanitize_inline(text: str) -> str:
    cleaned = text.replace("`", "")
    cleaned = cleaned.replace("*", "")
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def parse_markdown(markdown_text: str) -> list[tuple[str, object]]:
    lines = markdown_text.splitlines()
    blocks: list[tuple[str, object]] = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line.strip():
            index += 1
            continue

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            blocks.append((f"h{level}", sanitize_inline(line[level:].strip())))
            index += 1
            continue

        if line.lstrip().startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            blocks.append(("table", table_lines))
            continue

        if re.match(r"^[*-]\s+", line.strip()):
            list_items: list[str] = []
            while index < len(lines) and re.match(r"^[*-]\s+", lines[index].strip()):
                item = re.sub(r"^[*-]\s+", "", lines[index].strip())
                list_items.append(sanitize_inline(item))
                index += 1
            blocks.append(("list", list_items))
            continue

        if re.match(r"^[가-하]\.\s+", line.strip()) or re.match(r"^\d+\)\s+", line.strip()):
            enum_items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                if not current or not (re.match(r"^[가-하]\.\s+", current) or re.match(r"^\d+\)\s+", current)):
                    break
                enum_items.append(sanitize_inline(current))
                index += 1
            blocks.append(("enum", enum_items))
            continue

        paragraph_lines = [line.strip()]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            stripped = next_line.strip()
            if not stripped:
                break
            if next_line.startswith("#") or next_line.lstrip().startswith("|") or re.match(r"^[*-]\s+", stripped):
                break
            paragraph_lines.append(stripped)
            index += 1
        blocks.append(("p", sanitize_inline(" ".join(paragraph_lines))))
    return blocks


def markdown_table_to_rows(table_lines: list[str]) -> list[list[str]]:
    rows = [split_markdown_table_row(line) for line in table_lines]
    if len(rows) < 2:
        return []
    return [[sanitize_inline(cell) for cell in row] for row in [rows[0], *rows[2:]]]


def table_rows_to_preview_lines(rows: list[list[str]]) -> list[str]:
    preview_lines: list[str] = []
    for row in rows:
        preview_lines.append(" | ".join(cell for cell in row))
    return preview_lines


def split_content_and_bibliography(
    blocks: list[tuple[str, object]],
) -> tuple[list[tuple[str, object]], list[str]]:
    content_blocks: list[tuple[str, object]] = []
    bibliography_entries: list[str] = []
    in_bibliography = False

    for block_type, payload in blocks:
        if block_type == "h2" and sanitize_inline(str(payload)) == "참고문헌":
            in_bibliography = True
            continue

        if in_bibliography:
            if block_type == "list":
                for item in payload:  # type: ignore[assignment]
                    bibliography_entries.append(sanitize_inline(str(item)))
            elif block_type == "p":
                paragraph = sanitize_inline(str(payload))
                if paragraph:
                    bibliography_entries.append(paragraph)
            continue

        content_blocks.append((block_type, payload))

    return content_blocks, bibliography_entries


def collect_content_paragraphs(
    blocks: list[tuple[str, object]],
) -> tuple[str, list[tuple[str, str]], list[dict[str, object]]]:
    title = ""
    content: list[tuple[str, str]] = []
    tables: list[dict[str, object]] = []
    table_index = 0
    for block_type, payload in blocks:
        if block_type == "h1":
            title = str(payload)
        elif block_type == "h2":
            content.append(("big_heading", str(payload)))
        elif block_type == "h3":
            content.append(("middle_heading", str(payload)))
        elif block_type == "h4":
            content.append(("small_heading", "  " + str(payload)))
        elif block_type == "p":
            paragraph = str(payload)
            if paragraph:
                content.append(("body", "    " + paragraph))
        elif block_type == "list":
            for item in payload:  # type: ignore[assignment]
                content.append(("body", "      - " + str(item)))
        elif block_type == "enum":
            for item in payload:  # type: ignore[assignment]
                content.append(("body", "    " + str(item)))
        elif block_type == "table":
            rows = markdown_table_to_rows(payload)  # type: ignore[arg-type]
            if not rows:
                continue
            table_index += 1
            placeholder = f"[[AUTO_TABLE_{table_index:03d}]]"
            content.append(("table_placeholder", placeholder))
            tables.append(
                {
                    "placeholder": placeholder,
                    "rows": rows,
                }
            )
    return title, content, tables


def clear_linesegarray(paragraph: ET.Element) -> None:
    for node in list(paragraph):
        if node.tag == qn("hp", "linesegarray"):
            paragraph.remove(node)


def set_text_on_run(paragraph: ET.Element, text: str, target_run_index: int) -> ET.Element:
    runs = paragraph.findall("hp:run", NS)
    if not runs:
        raise ValueError("Paragraph does not contain any run nodes.")

    for run in runs:
        for child in list(run):
            if child.tag == qn("hp", "t"):
                run.remove(child)

    target_run = runs[target_run_index]
    if text:
        text_node = ET.Element(qn("hp", "t"))
        text_node.text = text
        target_run.append(text_node)

    clear_linesegarray(paragraph)
    return paragraph


def clone_paragraph(sample: ET.Element, text: str, target_run_index: int) -> ET.Element:
    paragraph = copy.deepcopy(sample)
    return set_text_on_run(paragraph, text, target_run_index)


def find_sample(paragraphs: list[ET.Element], marker: str) -> ET.Element:
    for paragraph in paragraphs:
        if marker in paragraph_text(paragraph):
            return paragraph
    raise ValueError(f"Could not find paragraph containing marker: {marker}")


def build_preview_text(
    title: str,
    author_name: str,
    author_info: str,
    content: list[tuple[str, str]],
    tables: list[dict[str, object]],
    discussion_topics: list[str],
    bibliography_entries: list[str],
) -> str:
    table_lookup = {
        str(table["placeholder"]): table_rows_to_preview_lines(table["rows"])  # type: ignore[index]
        for table in tables
    }
    lines = [title, "", author_name, author_info, ""]
    for block_type, text in content:
        if block_type == "body":
            lines.append(text.strip())
        elif block_type == "table_placeholder":
            lines.extend(table_lookup.get(text, [text]))
            lines.append("")
        else:
            lines.append(text.strip())
            lines.append("")
    lines.append("토의 주제")
    lines.extend(topic.strip() for topic in discussion_topics)
    lines.append("")
    lines.append("참 고 문 헌")
    lines.extend(entry.strip() for entry in bibliography_entries)
    return "\n".join(lines).strip() + "\n"


def build_document(
    template_xml: bytes,
    markdown_text: str,
    author_name: str,
    author_info: str,
    discussion_topics: list[str],
    bibliography_entries: list[str],
) -> tuple[bytes, str, list[dict[str, object]]]:
    root = ET.fromstring(template_xml)
    paragraphs = root.findall("hp:p", NS)

    title_sample = find_sample(paragraphs, "(제목)")
    author_name_sample = find_sample(paragraphs, "홍 길 동")
    author_info_sample = find_sample(paragraphs, "부산초등학교 교장")
    blank_sample = paragraphs[36]
    big_heading_sample = find_sample(paragraphs, "Ⅰ. 시작하면서")
    middle_heading_sample = find_sample(paragraphs, "1. 중간 제목")
    small_heading_sample = find_sample(paragraphs, "가. 작은 제목")
    body_sample = find_sample(paragraphs, "안녕하십니까?")
    discussion_heading_sample = find_sample(paragraphs, "토의 주제")
    discussion_item_sample = find_sample(paragraphs, "원고 작성은 저작권법에 위배되지 않도록 해야합니다.")
    bibliography_heading_sample = find_sample(paragraphs, "참 고 문 헌")
    bibliography_entry_sample = find_sample(paragraphs, "남정걸(2002)")

    markdown_blocks = parse_markdown(markdown_text)
    content_blocks, bibliography_entries_from_markdown = split_content_and_bibliography(markdown_blocks)
    title, content, tables = collect_content_paragraphs(content_blocks)
    if not title:
        raise ValueError("Markdown title (# heading) is required.")
    if bibliography_entries_from_markdown:
        bibliography_entries = bibliography_entries_from_markdown

    new_paragraphs: list[ET.Element] = [
        clone_paragraph(title_sample, title, 1),
        copy.deepcopy(blank_sample),
        copy.deepcopy(blank_sample),
        clone_paragraph(author_name_sample, author_name, 1),
        clone_paragraph(author_info_sample, author_info, 1),
        copy.deepcopy(blank_sample),
    ]

    first_big_heading = True
    for block_type, text in content:
        if block_type == "big_heading":
            if not first_big_heading:
                new_paragraphs.append(copy.deepcopy(blank_sample))
            new_paragraphs.append(clone_paragraph(big_heading_sample, text, 0))
            new_paragraphs.append(copy.deepcopy(blank_sample))
            first_big_heading = False
        elif block_type == "middle_heading":
            new_paragraphs.append(clone_paragraph(middle_heading_sample, text, 0))
        elif block_type == "small_heading":
            new_paragraphs.append(clone_paragraph(small_heading_sample, text, 0))
        elif block_type == "table_placeholder":
            new_paragraphs.append(clone_paragraph(body_sample, text, 0))
        else:
            new_paragraphs.append(clone_paragraph(body_sample, text, 0))

    new_paragraphs.append(copy.deepcopy(blank_sample))
    new_paragraphs.append(copy.deepcopy(discussion_heading_sample))
    for topic in discussion_topics:
        new_paragraphs.append(clone_paragraph(discussion_item_sample, "  * " + topic, 0))

    new_paragraphs.append(copy.deepcopy(blank_sample))
    new_paragraphs.append(copy.deepcopy(blank_sample))
    new_paragraphs.append(copy.deepcopy(bibliography_heading_sample))
    for entry in bibliography_entries:
        new_paragraphs.append(clone_paragraph(bibliography_entry_sample, "  " + entry, 0))

    root[:] = new_paragraphs
    preview_text = build_preview_text(
        title,
        author_name,
        author_info,
        content,
        tables,
        discussion_topics,
        bibliography_entries,
    )
    xml_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True, short_empty_elements=False)
    return xml_bytes, preview_text, tables


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill an HWPX manuscript template from a Markdown source.")
    parser.add_argument("--template", required=True, help="Path to the source HWPX template.")
    parser.add_argument("--markdown", required=True, help="Path to the Markdown manuscript.")
    parser.add_argument("--output", required=True, help="Path to the generated HWPX file.")
    parser.add_argument("--table-json", help="Optional path to write parsed table metadata as JSON.")
    parser.add_argument("--author-name", default="작성자 정보 입력 필요", help="Author name to place under the title.")
    parser.add_argument("--author-info", default="소속 및 직위 입력 필요", help="Author affiliation/title to place under the name.")
    args = parser.parse_args()

    template_path = Path(args.template)
    markdown_path = Path(args.markdown)
    output_path = Path(args.output)
    table_json_path = Path(args.table_json) if args.table_json else output_path.with_suffix(output_path.suffix + ".tables.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    table_json_path.parent.mkdir(parents=True, exist_ok=True)

    markdown_text = markdown_path.read_text(encoding="utf-8")
    discussion_topics = [
        "수업에서 수리적 점검 절차를 습관화하려면 어떤 발문과 활동이 효과적인가?",
        "과학 사례를 활용할 때 계산력, 수학 역량, 수리력을 어떻게 구분하고 연결할 것인가?",
    ]
    bibliography_entries = [
        "제공 원고에는 별도 참고문헌이 제시되지 않아 최종 제출 전 작성자 보완이 필요합니다.",
    ]

    with zipfile.ZipFile(template_path, "r") as source_zip:
        section_xml = source_zip.read("Contents/section0.xml")
        new_section_xml, preview_text, tables = build_document(
            section_xml,
            markdown_text,
            args.author_name,
            args.author_info,
            discussion_topics,
            bibliography_entries,
        )

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
            for info in source_zip.infolist():
                data = source_zip.read(info.filename)
                if info.filename == "Contents/section0.xml":
                    data = new_section_xml
                elif info.filename == "Preview/PrvText.txt":
                    data = preview_text.encode("utf-8")
                target_zip.writestr(info, data)

    table_json_path.write_text(
        json.dumps({"tables": tables}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
