#!/usr/bin/env python3
"""Download Korean previous-exam source files from EBSi and write a manifest."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


AJAX_URL = "https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperListAjax.ajax"
DOWNLOAD_PREFIX = "https://wdown.ebsi.co.kr/W61001/01exam"

AREA_HIDDEN = {
    "1": "korArOrd",
    "2": "mathArOrd",
    "3": "engArOrd",
    "4": "hisArOrd",
    "5": "srch1ArOrd",
    "6": "srch2ArOrd",
    "7": "jobArOrd",
    "8": "scndForgnlngArOrd",
}

MONTH_LABELS = {
    "03": "3월",
    "04": "4월",
    "05": "5월",
    "06": "6월",
    "07": "7월",
    "08": "8월",
    "09": "9월",
    "10": "10월",
    "11": "수능",
    "12": "12월",
}

KICE_MONTH_LABELS = {
    "06": "6월모의평가",
    "09": "9월모의평가",
    "11": "수능",
}

KIND_BY_CALL = {
    "P": ("problem", "문제지"),
    "J": ("answer", "정답"),
    "J2": ("answer", "정답"),
    "H": ("solution", "해설"),
}


@dataclass(frozen=True)
class Subject:
    area_order: str
    form_field: str
    subject_id: str
    label: str
    slug: str
    area_hidden: str | None = None


@dataclass(frozen=True)
class LinkItem:
    family: str
    kind: str
    kind_code: str
    year: int
    month: str
    date: str
    grade: str | None
    exam_name: str
    subject_label: str
    subject_id: str
    irecord: str
    source_url: str
    filename: str
    output: str


KICE_SUBJECTS = [
    Subject("6", "sFormPartSci", "140115", "물리학Ⅰ", "physics-i"),
    Subject("6", "sFormPartSci", "140116", "물리학Ⅱ", "physics-ii"),
    Subject("6", "sFormPartSci", "156", "화학Ⅰ", "chemistry-i"),
    Subject("6", "sFormPartSci", "157", "화학Ⅱ", "chemistry-ii"),
    Subject("6", "sFormPartSci", "158", "생명과학Ⅰ", "life-science-i"),
    Subject("6", "sFormPartSci", "159", "생명과학Ⅱ", "life-science-ii"),
    Subject("6", "sFormPartSci", "154", "지구과학Ⅰ", "earth-science-i"),
    Subject("6", "sFormPartSci", "155", "지구과학Ⅱ", "earth-science-ii"),
]

NATIONAL_2015_SUBJECTS = [
    Subject("1", "sFormPartKor", "17022", "국어", "kor"),
    Subject("2", "sFormPartMath", "140111", "수학", "math"),
    Subject("3", "sFormPartEng", "120013", "영어", "eng"),
    Subject("4", "sFormPartHis", "50612", "한국사", "history"),
    Subject("5", "sFormPartSoc", "50615", "생활과 윤리", "life-ethics"),
    Subject("5", "sFormPartSoc", "50616", "윤리와 사상", "ethics-thought"),
    Subject("5", "sFormPartSoc", "17029", "한국지리", "korean-geography"),
    Subject("5", "sFormPartSoc", "50618", "세계지리", "world-geography"),
    Subject("5", "sFormPartSoc", "50613", "동아시아사", "east-asian-history"),
    Subject("5", "sFormPartSoc", "50617", "세계사", "world-history"),
    Subject("5", "sFormPartSoc", "140109", "정치와 법", "politics-law"),
    Subject("5", "sFormPartSoc", "17037", "경제", "economics"),
    Subject("5", "sFormPartSoc", "17038", "사회·문화", "society-culture"),
    Subject("6", "sFormPartSci", "140113", "물리학Ⅰ", "physics-i"),
    Subject("6", "sFormPartSci", "17042", "화학Ⅰ", "chemistry-i"),
    Subject("6", "sFormPartSci", "17043", "생명과학Ⅰ", "life-science-i"),
    Subject("6", "sFormPartSci", "17041", "지구과학Ⅰ", "earth-science-i"),
    Subject("7", "sFormPartCareer", "17078", "농업 기초 기술", "agriculture-basic"),
    Subject("7", "sFormPartCareer", "50620", "공업 일반", "industry-general"),
    Subject("7", "sFormPartCareer", "17049", "상업 경제", "commerce-economics"),
    Subject("7", "sFormPartCareer", "50622", "수산·해운 산업 기초", "fishery-shipping"),
    Subject("7", "sFormPartCareer", "17054", "인간 발달", "human-development"),
    Subject("7", "sFormPartCareer", "140110", "성공적인 직업 생활", "successful-career"),
    Subject("8", "sFormPartLang", "17058", "독일어Ⅰ", "german-i"),
    Subject("8", "sFormPartLang", "17059", "프랑스어Ⅰ", "french-i"),
    Subject("8", "sFormPartLang", "17060", "스페인어Ⅰ", "spanish-i"),
    Subject("8", "sFormPartLang", "17061", "중국어Ⅰ", "chinese-i"),
    Subject("8", "sFormPartLang", "17062", "일본어Ⅰ", "japanese-i"),
    Subject("8", "sFormPartLang", "17063", "러시아어Ⅰ", "russian-i"),
    Subject("8", "sFormPartLang", "17065", "한문Ⅰ", "classical-chinese-i"),
]

SUBJECTS_BY_FAMILY = {
    "kice": KICE_SUBJECTS,
    "national": NATIONAL_2015_SUBJECTS,
}


def parse_csv_set(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_years(value: str) -> list[int]:
    years: set[int] = set()
    for part in parse_csv_set(value):
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            step = 1 if end >= start else -1
            years.update(range(start, end + step, step))
        else:
            years.add(int(part))
    return sorted(years)


def parse_months(value: str) -> list[str]:
    return [part.zfill(2) if part.isdigit() else part for part in parse_csv_set(value)]


def safe_name(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\s+", "_", value.strip())
    return re.sub(r'[<>:"/\\|?*]+', "_", value)


def clean_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def decode_response(data: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def request_bytes(url: str, data: bytes | None = None, referer: str | None = None) -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0",
    }
    if referer:
        headers["Referer"] = referer
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        headers["X-Requested-With"] = "XMLHttpRequest"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network request failed: {url}: {exc}") from exc


def referer_for(family: str) -> str:
    target = "D300" if family == "kice" else "D200"
    return f"https://www.ebsi.co.kr/ebs/xip/xipc/previousPaperList.ebs?targetCd={target}"


def target_code_for(family: str) -> str:
    return "D300" if family == "kice" else "D200"


def query_years_for(family: str, years: list[int]) -> list[int]:
    if family == "kice":
        return [year - 1 for year in years]
    return years


def area_hidden_for(subject: Subject) -> str:
    return subject.area_hidden or AREA_HIDDEN.get(subject.area_order, "srch2ArOrd")


def build_post_data(family: str, query_years: list[int], months: list[str], subject: Subject) -> bytes:
    target_cd = target_code_for(family)
    area_hidden = area_hidden_for(subject)
    fields: list[tuple[str, str]] = [
        ("targetCd", target_cd),
        ("yearList", ",".join(str(year) for year in query_years)),
        ("monthList", ",".join(months)),
        ("arOrd", subject.area_order),
        ("subjIdList", subject.subject_id),
        ("sort", "recent"),
        ("paperId", ""),
        ("paperNo", ""),
        ("lvl", ""),
        (area_hidden, subject.area_order),
        (subject.form_field, subject.subject_id),
    ]
    if family == "national":
        fields.append(("yearAll", "all"))
    fields.extend(("year", str(year)) for year in query_years)
    fields.extend(("month", month) for month in months)
    return urllib.parse.urlencode(fields).encode("utf-8")


def normalize_url(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if value.startswith("/"):
        return DOWNLOAD_PREFIX + value
    return value


def infer_date(url: str, irecord: str) -> str | None:
    match = re.search(r"/(\d{8})/", url)
    if match:
        return match.group(1)
    if re.match(r"^20\d{6}", irecord):
        return irecord[:8]
    return None


def infer_grade(irecord: str, title: str) -> str | None:
    if len(irecord) >= 9 and irecord[8] in {"1", "2", "3"}:
        return irecord[8]
    match = re.search(r"고\s*([123])", title)
    if match:
        return match.group(1)
    return None


def exam_label(family: str, year: int, month: str, grade: str | None, title: str) -> str:
    if family == "kice":
        return KICE_MONTH_LABELS.get(month, MONTH_LABELS.get(month, f"{int(month)}월"))
    if title:
        cleaned = clean_html(title)
        if "전국연합" in cleaned:
            return cleaned
    grade_label = f"고{grade}_" if grade else ""
    month_label = MONTH_LABELS.get(month, f"{int(month)}월")
    return f"{year}_{grade_label}{month_label}_전국연합학력평가"


def extension_from_url(url: str, kind: str) -> str:
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    if suffix in {".pdf", ".png", ".jpg", ".jpeg"}:
        return suffix
    return ".png" if kind == "answer" else ".pdf"


def detect_extension(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return ".pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8"):
        return ".jpg"
    return None


def make_filename(family: str, year: int, month: str, grade: str | None, subject_label: str, kind: str, url: str) -> str:
    kind_label = {"problem": "문제지", "answer": "정답", "solution": "해설"}[kind]
    if family == "kice":
        exam = KICE_MONTH_LABELS.get(month, MONTH_LABELS.get(month, f"{int(month)}월"))
        stem = f"{year}_{exam}_{subject_label}_{kind_label}"
    else:
        grade_label = f"고{grade}" if grade else "고등"
        month_label = MONTH_LABELS.get(month, f"{int(month)}월")
        stem = f"{year}_{grade_label}_{month_label}_전국연합학력평가_{subject_label}_{kind_label}"
    return safe_name(stem) + extension_from_url(url, kind)


def block_title(block: str) -> str:
    for pattern in [
        r'<div class="qus_tit">(.*?)</div>',
        r'<strong class="tit">(.*?)</strong>',
        r'<p class="tit">(.*?)</p>',
    ]:
        match = re.search(pattern, block, re.S)
        if match:
            return clean_html(match.group(1))
    return ""


def split_blocks(page: str) -> list[str]:
    blocks = re.findall(r'<div class="qus_box\b.*?(?=<div class="qus_box\b|<!-- //board_list -->)', page, re.S)
    return blocks or [page]


def parse_call_args(arg_text: str) -> list[str]:
    return re.findall(r"'([^']*)'", arg_text)


def parse_links(
    family: str,
    page: str,
    requested_years: set[int],
    months: set[str],
    grade: str,
    subject: Subject,
    kinds: set[str],
    out_root: Path,
) -> list[LinkItem]:
    call_pattern = re.compile(r"goDownLoad(J2|[PJH])\((.*?)\);", re.S)
    items: list[LinkItem] = []
    seen: set[tuple[str, int, str, str, str]] = set()
    for block in split_blocks(page):
        title = block_title(block)
        for kind_code, arg_text in call_pattern.findall(block):
            kind, _label = KIND_BY_CALL[kind_code]
            if kind not in kinds:
                continue
            args = parse_call_args(arg_text)
            if not args:
                continue
            if len(args) > 5 and args[5] and args[5] != subject.subject_id:
                continue
            irecord = args[2] if len(args) > 2 else ""
            source_url = normalize_url(args[0])
            date = infer_date(source_url, irecord)
            if not date:
                continue
            calendar_year = int(date[:4])
            month = date[4:6]
            year = calendar_year + 1 if family == "kice" else calendar_year
            if year not in requested_years or month not in months:
                continue
            record_grade = infer_grade(irecord, title)
            if family == "national" and grade != "any" and record_grade != grade:
                continue
            key = (kind, year, month, source_url, subject.subject_id)
            if key in seen:
                continue
            seen.add(key)
            filename = make_filename(family, year, month, record_grade, subject.label, kind, source_url)
            output_dir = out_root / family / str(year) / safe_name(exam_label(family, year, month, record_grade, title)) / safe_name(subject.label)
            items.append(
                LinkItem(
                    family=family,
                    kind=kind,
                    kind_code=kind_code,
                    year=year,
                    month=month,
                    date=date,
                    grade=record_grade,
                    exam_name=exam_label(family, year, month, record_grade, title),
                    subject_label=subject.label,
                    subject_id=subject.subject_id,
                    irecord=irecord,
                    source_url=source_url,
                    filename=filename,
                    output=str(output_dir / filename),
                )
            )
    kind_order = {"problem": 0, "answer": 1, "solution": 2}
    return sorted(items, key=lambda item: (item.year, item.month, item.subject_label, kind_order.get(item.kind, 9)))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_bytes(data: bytes, kind: str, url: str) -> dict[str, object]:
    expected_ext = extension_from_url(url, kind)
    actual_ext = detect_extension(data)
    if expected_ext in {".pdf", ".png", ".jpg", ".jpeg"}:
        header_ok = actual_ext is not None
    else:
        header_ok = len(data) > 0
    return {
        "size_bytes": len(data),
        "sha256": sha256(data),
        "expected_extension": expected_ext,
        "actual_extension": actual_ext,
        "header_ok": header_ok,
        "verified": bool(header_ok and len(data) > 1024),
    }


def resolve_subjects(args: argparse.Namespace) -> list[Subject]:
    if args.subject == "custom":
        missing = [
            name
            for name, value in [
                ("--subject-id", args.subject_id),
                ("--subject-label", args.subject_label),
                ("--form-field", args.form_field),
                ("--area-order", args.area_order),
            ]
            if not value
        ]
        if missing:
            raise SystemExit(f"custom subject requires: {', '.join(missing)}")
        return [
            Subject(
                area_order=args.area_order,
                form_field=args.form_field,
                subject_id=args.subject_id,
                label=args.subject_label,
                slug="custom",
                area_hidden=args.area_hidden,
            )
        ]

    available = SUBJECTS_BY_FAMILY[args.exam_family]
    requested = parse_csv_set(args.subject)
    if not requested or requested == ["all"]:
        return available

    selected: list[Subject] = []
    for token in requested:
        matches = [
            subject
            for subject in available
            if token in {subject.slug, subject.label, subject.subject_id}
        ]
        if not matches:
            options = ", ".join(subject.slug for subject in available)
            raise SystemExit(f"unknown subject for {args.exam_family}: {token}\navailable: {options}")
        selected.extend(matches)

    deduped: dict[str, Subject] = {subject.subject_id: subject for subject in selected}
    return list(deduped.values())


def requested_kind_set(value: str) -> set[str]:
    kinds = set(parse_csv_set(value))
    allowed = {kind for kind, _label in KIND_BY_CALL.values()}
    unknown = kinds - allowed
    if unknown:
        raise SystemExit(f"unknown kinds: {', '.join(sorted(unknown))}")
    return kinds


def expected_matrix(years: list[int], months: list[str], kinds: set[str], subjects: list[Subject]) -> set[tuple[int, str, str, str]]:
    return {
        (year, month, subject.subject_id, kind)
        for year in years
        for month in months
        for subject in subjects
        for kind in kinds
    }


def missing_by_kind(
    expected: set[tuple[int, str, str, str]],
    found: set[tuple[int, str, str, str]],
    subject_by_id: dict[str, Subject],
) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for year, month, subject_id, kind in sorted(expected - found):
        result.setdefault(kind, []).append(
            {
                "year": year,
                "month": month,
                "subject": subject_by_id.get(subject_id, Subject("", "", subject_id, subject_id, subject_id)).label,
                "subject_id": subject_id,
            }
        )
    return result


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exam-family", choices=["kice", "national"], required=True)
    parser.add_argument("--years", required=True, help="Academic years for kice, calendar exam years for national.")
    parser.add_argument("--months", required=True, help="Comma-separated months such as 06,09,11.")
    parser.add_argument("--subject", default="earth-science-ii", help="Subject alias, label, id, comma list, all, or custom.")
    parser.add_argument("--grade", default="any", choices=["1", "2", "3", "any"], help="National Union grade filter.")
    parser.add_argument("--kinds", default="problem,answer,solution")
    parser.add_argument("--out", required=True, help="Output root for downloaded files and manifest.")
    parser.add_argument("--manifest", help="Optional manifest path. Defaults under --out.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-missing", action="store_true")
    parser.add_argument("--pause", type=float, default=0.15)
    parser.add_argument("--subject-id")
    parser.add_argument("--subject-label")
    parser.add_argument("--form-field")
    parser.add_argument("--area-order")
    parser.add_argument("--area-hidden")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    years = parse_years(args.years)
    months = parse_months(args.months)
    subjects = resolve_subjects(args)
    kinds = requested_kind_set(args.kinds)
    out_root = Path(args.out)
    analysis_dir = out_root / "_manifest"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    referer = referer_for(args.exam_family)

    all_links: list[LinkItem] = []
    html_paths: list[str] = []
    for subject in subjects:
        query_years = query_years_for(args.exam_family, years)
        post_data = build_post_data(args.exam_family, query_years, months, subject)
        page = decode_response(request_bytes(AJAX_URL, post_data, referer))
        html_path = analysis_dir / f"ebsi_ajax_{args.exam_family}_{subject.slug}_{years[0]}_{years[-1]}_{'-'.join(months)}.html"
        html_path.write_text(page, encoding="utf-8")
        html_paths.append(str(html_path))
        links = parse_links(
            family=args.exam_family,
            page=page,
            requested_years=set(years),
            months=set(months),
            grade=args.grade,
            subject=subject,
            kinds=kinds,
            out_root=out_root,
        )
        all_links.extend(links)
        time.sleep(args.pause)

    manifest_items: list[dict[str, object]] = []
    for link in all_links:
        output_path = Path(link.output)
        if args.dry_run:
            manifest_items.append({**asdict(link), "planned": True, "verified": None})
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and output_path.stat().st_size > 1024 and not args.overwrite:
            data = output_path.read_bytes()
            downloaded = False
        else:
            data = request_bytes(link.source_url, referer=referer)
            output_path.write_bytes(data)
            downloaded = True
            time.sleep(args.pause)

        verification = verify_bytes(data, link.kind, link.source_url)
        actual_ext = verification.get("actual_extension")
        if isinstance(actual_ext, str) and output_path.suffix.lower() != actual_ext:
            corrected_path = output_path.with_suffix(actual_ext)
            corrected_path.write_bytes(data)
            if corrected_path != output_path:
                try:
                    output_path.unlink()
                except OSError:
                    pass
            output_path = corrected_path
            extension_corrected = True
        else:
            extension_corrected = False

        manifest_items.append(
            {
                **asdict(link),
                "output": str(output_path),
                "downloaded": downloaded,
                "extension_corrected": extension_corrected,
                **verification,
            }
        )

    found = {
        (int(item["year"]), str(item["month"]), str(item["subject_id"]), str(item["kind"]))
        for item in manifest_items
        if item.get("verified") is not False
    }
    expected = expected_matrix(years, months, kinds, subjects)
    subject_by_id = {subject.subject_id: subject for subject in subjects}
    missing = missing_by_kind(expected, found, subject_by_id)
    verified_count = sum(1 for item in manifest_items if item.get("verified") is True)
    failed_count = sum(1 for item in manifest_items if item.get("verified") is False)
    ok = bool(manifest_items) and failed_count == 0 and (args.allow_missing or not any(missing.values()))

    manifest = {
        "ok": ok,
        "exam_family": args.exam_family,
        "years": years,
        "months": months,
        "grade": args.grade if args.exam_family == "national" else None,
        "kinds": sorted(kinds),
        "subjects": [asdict(subject) for subject in subjects],
        "dry_run": args.dry_run,
        "ajax_html": html_paths,
        "count": len(manifest_items),
        "verified_count": verified_count,
        "failed_count": failed_count,
        "missing_by_kind": missing,
        "items": manifest_items,
    }

    manifest_path = Path(args.manifest) if args.manifest else analysis_dir / "exam_source_download_manifest.json"
    write_json(manifest_path, manifest)

    print(f"count={len(manifest_items)}")
    print(f"verified={verified_count}/{len(manifest_items)}")
    print(f"missing={sum(len(values) for values in missing.values())}")
    print(f"manifest={manifest_path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
