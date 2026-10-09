#!/usr/bin/env python3
"""Audit batch student-record drafts for length, phrases, evidence, and similarity."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from normalize_input import clean, header_key, load_rows


FIELD_ALIASES = {
    "student_id": ["student_id", "학번", "번호", "학생id"],
    "name": ["name", "이름", "성명", "학생명"],
    "area": ["area", "영역", "기록영역"],
    "draft_text": [
        "draft_text",
        "검토용초안",
        "검토용 초안",
        "초안",
        "기록문장",
        "문장",
    ],
    "evidence_summary": [
        "evidence_summary",
        "근거요약",
        "입력근거",
        "근거",
        "evidence_text",
    ],
    "check_needed": ["check_needed", "확인필요", "확인 필요"],
    "excluded_items": ["excluded_items", "제외사항", "제외·확인사항"],
}

FIELD_LOOKUP = {
    header_key(alias): canonical
    for canonical, aliases in FIELD_ALIASES.items()
    for alias in aliases
}

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3}


def canonicalize_row(row: dict[str, Any], index: int) -> dict[str, str]:
    result = {field: "" for field in FIELD_ALIASES}
    for key, value in row.items():
        mapped = FIELD_LOOKUP.get(header_key(key))
        if mapped and not result[mapped]:
            result[mapped] = clean(value)
    result["record_key"] = (
        result["student_id"] or result["name"] or f"row-{index + 2}"
    )
    return result


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    required = {"limits", "similarity", "default_area"}
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"설정 파일 필수 항목 누락: {', '.join(missing)}")
    return config


def load_phrase_rules(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    required = {"severity", "category", "match_type", "pattern", "reason"}
    if not rows:
        return []
    missing = required - set(rows[0])
    if missing:
        raise ValueError(f"표현 규칙 필수 열 누락: {', '.join(sorted(missing))}")

    rules = []
    for index, row in enumerate(rows, start=2):
        rule = {key: clean(value) for key, value in row.items()}
        if not rule["pattern"]:
            continue
        if rule["severity"] not in SEVERITY_ORDER:
            raise ValueError(f"표현 규칙 {index}행 severity 오류: {rule['severity']}")
        if rule["match_type"] not in {"literal", "regex"}:
            raise ValueError(f"표현 규칙 {index}행 match_type 오류")
        if rule["match_type"] == "regex":
            try:
                re.compile(rule["pattern"], flags=re.IGNORECASE)
            except re.error as exc:
                raise ValueError(f"표현 규칙 {index}행 정규식 오류: {exc}") from exc
        rules.append(rule)
    return rules


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_area(area: str, config: dict[str, Any]) -> tuple[str, bool]:
    if area in config["limits"]:
        return area, True
    compact = header_key(area)
    for alias, canonical in config.get("area_aliases", {}).items():
        if header_key(alias) == compact and canonical in config["limits"]:
            return canonical, True
    return config["default_area"], False


def make_issue(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def match_phrases(text: str, rules: list[dict[str, str]]) -> list[dict[str, str]]:
    findings = []
    for rule in rules:
        if rule["match_type"] == "literal":
            position = text.lower().find(rule["pattern"].lower())
            matched = text[position : position + len(rule["pattern"])] if position >= 0 else ""
        else:
            match = re.search(rule["pattern"], text, flags=re.IGNORECASE)
            matched = match.group(0) if match else ""
        if matched:
            findings.append({**rule, "matched": matched})
    return findings


def similarity_text(text: str, ignore_phrases: list[str]) -> str:
    normalized = normalize_newlines(text).lower()
    for phrase in ignore_phrases:
        normalized = normalized.replace(phrase.lower(), " ")
    return re.sub(r"[^0-9a-z가-힣]+", "", normalized)


def word_tokens(text: str, ignore_phrases: list[str]) -> set[str]:
    normalized = normalize_newlines(text).lower()
    for phrase in ignore_phrases:
        normalized = normalized.replace(phrase.lower(), " ")
    return set(re.findall(r"[0-9a-z가-힣]+", normalized))


def ngrams(text: str, width: int = 3) -> set[str]:
    if len(text) <= width:
        return {text} if text else set()
    return {text[index : index + width] for index in range(len(text) - width + 1)}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def similarity_score(
    left: str, right: str, ignore_phrases: list[str]
) -> tuple[float, str]:
    compact_left = similarity_text(left, ignore_phrases)
    compact_right = similarity_text(right, ignore_phrases)
    sequence = SequenceMatcher(None, compact_left, compact_right).ratio()
    trigram = jaccard(ngrams(compact_left), ngrams(compact_right))
    token = jaccard(
        word_tokens(left, ignore_phrases),
        word_tokens(right, ignore_phrases),
    )
    score = 0.55 * sequence + 0.25 * trigram + 0.20 * token

    readable_left = re.sub(r"\s+", " ", normalize_newlines(left)).strip()
    readable_right = re.sub(r"\s+", " ", normalize_newlines(right)).strip()
    matcher = SequenceMatcher(None, readable_left, readable_right)
    longest = matcher.find_longest_match(
        0, len(readable_left), 0, len(readable_right)
    )
    excerpt = readable_left[longest.a : longest.a + longest.size].strip()
    if len(excerpt) > 80:
        excerpt = excerpt[:77] + "..."
    return round(score, 4), excerpt


def audit_single(
    record: dict[str, str],
    config: dict[str, Any],
    phrase_rules: list[dict[str, str]],
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    text = normalize_newlines(record["draft_text"]).strip()
    area, known_area = normalize_area(record["area"], config)
    limits = config["limits"][area]
    characters = len(text)
    byte_count = len(text.encode(config.get("byte_encoding", "utf-8")))
    max_characters = int(limits["max_characters"])
    max_bytes = int(limits["max_bytes_utf8"])
    near_ratio = float(config.get("near_limit_ratio", 0.95))
    within_limit = characters <= max_characters and byte_count <= max_bytes
    near_limit = (
        within_limit
        and (
            characters >= max_characters * near_ratio
            or byte_count >= max_bytes * near_ratio
        )
    )

    if not text:
        issues.append(make_issue("high", "empty_draft", "검토용 초안이 비어 있습니다."))
    if not record["evidence_summary"]:
        issues.append(
            make_issue("high", "missing_evidence", "초안과 연결된 근거 요약이 없습니다.")
        )
    if not known_area:
        issues.append(
            make_issue(
                "medium",
                "unknown_area",
                f"영역 '{record['area'] or '(빈칸)'}'을 확인하지 못해 기본 영역 '{area}'의 상한을 적용했습니다.",
            )
        )
    if not within_limit:
        issues.append(
            make_issue(
                "high",
                "over_limit",
                f"분량 상한 초과: {characters}/{max_characters}자, {byte_count}/{max_bytes}바이트",
            )
        )
    elif near_limit:
        issues.append(
            make_issue(
                "medium",
                "near_limit",
                f"분량 상한에 임박: {characters}/{max_characters}자, {byte_count}/{max_bytes}바이트",
            )
        )
    if record["check_needed"]:
        issues.append(
            make_issue(
                "medium",
                "check_needed",
                f"교사 확인 필요: {record['check_needed']}",
            )
        )

    expression_findings = match_phrases(text, phrase_rules)
    for finding in expression_findings:
        issues.append(
            make_issue(
                finding["severity"],
                f"expression_{finding['category']}",
                f"'{finding['matched']}' — {finding['reason']}",
            )
        )

    return {
        **record,
        "normalized_area": area,
        "characters": characters,
        "max_characters": max_characters,
        "bytes": byte_count,
        "max_bytes": max_bytes,
        "within_limit": within_limit,
        "near_limit": near_limit,
        "expression_findings": expression_findings,
        "duplicate_matches": [],
        "issues": issues,
    }


def add_similarity_findings(
    audited: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    settings = config["similarity"]
    medium = float(settings["medium_threshold"])
    high = float(settings["high_threshold"])
    minimum = int(settings.get("minimum_text_characters", 20))
    ignore_phrases = config.get("ignore_phrases", [])
    pairs = []

    for left_index in range(len(audited)):
        left = audited[left_index]
        if len(left["draft_text"]) < minimum:
            continue
        for right_index in range(left_index + 1, len(audited)):
            right = audited[right_index]
            if len(right["draft_text"]) < minimum:
                continue
            score, excerpt = similarity_score(
                left["draft_text"], right["draft_text"], ignore_phrases
            )
            left_norm = similarity_text(left["draft_text"], ignore_phrases)
            right_norm = similarity_text(right["draft_text"], ignore_phrases)
            if left_norm and left_norm == right_norm:
                level = "exact"
                severity = "high"
            elif score >= high:
                level = "high"
                severity = "high"
            elif score >= medium:
                level = "medium"
                severity = "medium"
            else:
                continue

            pair = {
                "left_key": left["record_key"],
                "left_name": left["name"],
                "right_key": right["record_key"],
                "right_name": right["name"],
                "score": score,
                "level": level,
                "common_excerpt": excerpt,
            }
            pairs.append(pair)
            for current, other in ((left, right), (right, left)):
                current["duplicate_matches"].append(
                    {
                        "record_key": other["record_key"],
                        "name": other["name"],
                        "score": score,
                        "level": level,
                    }
                )
                current["issues"].append(
                    make_issue(
                        severity,
                        f"duplicate_{level}",
                        f"{other['record_key']} {other['name']} 문장과 유사도 {score:.2f} ({level})",
                    )
                )

    pairs.sort(key=lambda item: item["score"], reverse=True)
    maximum = int(settings.get("max_reported_pairs", 100))
    return pairs[:maximum]


def priority_for(issues: list[dict[str, str]]) -> str:
    highest = max(
        (SEVERITY_ORDER.get(issue["severity"], 0) for issue in issues),
        default=0,
    )
    if highest >= SEVERITY_ORDER["high"]:
        return "P1"
    if highest >= SEVERITY_ORDER["low"]:
        return "P2"
    return "통과"


def recommendation(issues: list[dict[str, str]]) -> str:
    codes = {issue["code"] for issue in issues}
    actions = []
    if "empty_draft" in codes:
        actions.append("입력 근거로 초안 작성")
    if "missing_evidence" in codes:
        actions.append("핵심 문장과 입력 근거 연결")
    if "over_limit" in codes or "near_limit" in codes:
        actions.append("공통 설명·수식어·반복 평가어부터 축약")
    if any(code.startswith("expression_") for code in codes):
        actions.append("공식 기준과 문맥을 확인해 위험 표현 수정")
    if any(code.startswith("duplicate_") for code in codes):
        actions.append("학생 고유 행동·과정·결과 중심으로 재구성")
    if "check_needed" in codes or "unknown_area" in codes:
        actions.append("교사 기록과 적용 영역 확인")
    return " / ".join(dict.fromkeys(actions)) or "실제 수행과 공식·교내 기준 최종 대조"


def csv_safe(value: Any) -> str:
    if isinstance(value, bool):
        return "Y" if value else "N"
    return clean(value)


def write_student_audit(path: Path, audited: list[dict[str, Any]]) -> None:
    fieldnames = [
        "record_key",
        "student_id",
        "name",
        "area",
        "normalized_area",
        "priority",
        "characters",
        "max_characters",
        "bytes",
        "max_bytes",
        "within_limit",
        "near_limit",
        "expression_flags",
        "duplicate_matches",
        "issues",
        "recommended_action",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in audited:
            writer.writerow(
                {
                    "record_key": item["record_key"],
                    "student_id": item["student_id"],
                    "name": item["name"],
                    "area": item["area"],
                    "normalized_area": item["normalized_area"],
                    "priority": item["priority"],
                    "characters": item["characters"],
                    "max_characters": item["max_characters"],
                    "bytes": item["bytes"],
                    "max_bytes": item["max_bytes"],
                    "within_limit": csv_safe(item["within_limit"]),
                    "near_limit": csv_safe(item["near_limit"]),
                    "expression_flags": " | ".join(
                        f"{finding['severity']}:{finding['matched']}"
                        for finding in item["expression_findings"]
                    ),
                    "duplicate_matches": " | ".join(
                        f"{match['record_key']} {match['name']}:{match['score']:.2f}({match['level']})"
                        for match in item["duplicate_matches"]
                    ),
                    "issues": " | ".join(
                        issue["message"] for issue in item["issues"]
                    ),
                    "recommended_action": item["recommended_action"],
                }
            )


def write_duplicate_pairs(path: Path, pairs: list[dict[str, Any]]) -> None:
    fieldnames = [
        "left_key",
        "left_name",
        "right_key",
        "right_name",
        "score",
        "level",
        "common_excerpt",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(pairs)


def md_escape(value: Any) -> str:
    return clean(value).replace("|", "\\|").replace("\n", " ")


def write_report(
    path: Path,
    audited: list[dict[str, Any]],
    pairs: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    counts = {
        label: sum(1 for item in audited if item["priority"] == label)
        for label in ("P1", "P2", "통과")
    }
    lines = [
        "# 학생별 기록 수정 우선순위 보고서",
        "",
        f"- 생성 시각: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"- 적용 기준 연도: {config.get('policy_year', '확인 필요')}",
        f"- 전체: {len(audited)}명 / P1: {counts['P1']}명 / P2: {counts['P2']}명 / 통과: {counts['통과']}명",
        "",
    ]

    for label, title in (
        ("P1", "P1 — 반드시 수정"),
        ("P2", "P2 — 확인 후 수정"),
        ("통과", "자동 검수 통과"),
    ):
        lines.extend([f"## {title}", ""])
        selected = [item for item in audited if item["priority"] == label]
        if not selected:
            lines.extend(["해당 없음.", ""])
            continue
        lines.extend(
            [
                "| 학생 | 영역 | 분량 | 발견 사항 | 권장 조치 |",
                "|---|---|---:|---|---|",
            ]
        )
        for item in selected:
            identity = f"{item['record_key']} {item['name']}".strip()
            issues = "; ".join(issue["message"] for issue in item["issues"])
            if not issues:
                issues = "자동 검수상 중대한 문제 없음"
            length = (
                f"{item['characters']}/{item['max_characters']}자, "
                f"{item['bytes']}/{item['max_bytes']}B"
            )
            lines.append(
                f"| {md_escape(identity)} | {md_escape(item['normalized_area'])} | "
                f"{length} | {md_escape(issues)} | "
                f"{md_escape(item['recommended_action'])} |"
            )
        lines.append("")

    lines.extend(["## 중복 검수", ""])
    if not pairs:
        lines.extend(["설정된 임계값 이상의 문장 쌍이 없습니다.", ""])
    else:
        lines.extend(
            [
                "| 학생 A | 학생 B | 유사도 | 등급 | 공통 구간 |",
                "|---|---|---:|---|---|",
            ]
        )
        for pair in pairs:
            left = f"{pair['left_key']} {pair['left_name']}".strip()
            right = f"{pair['right_key']} {pair['right_name']}".strip()
            lines.append(
                f"| {md_escape(left)} | {md_escape(right)} | "
                f"{pair['score']:.2f} | {pair['level']} | "
                f"{md_escape(pair['common_excerpt'])} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 최종 확인",
            "",
            "자동 검수 통과는 기재 가능성의 최종 판정이 아니다.",
            "",
            "교사 확인: 실제 수행, 허위·과장, 기재금지사항, 최신 공식 기재요령과 학교 내부 기준을 대조한 뒤 최종 입력",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    parser = argparse.ArgumentParser(
        description="학생별 기록 초안의 분량·표현·근거·중복을 일괄 점검합니다."
    )
    parser.add_argument("input", type=Path, help="초안 CSV, TSV, XLSX 또는 JSON")
    parser.add_argument("--sheet", help="XLSX 시트 이름")
    parser.add_argument(
        "--config",
        type=Path,
        default=skill_dir / "assets" / "audit-config.json",
        help="영역별 상한과 중복 임계값 JSON",
    )
    parser.add_argument(
        "--phrases",
        type=Path,
        default=skill_dir / "assets" / "prohibited-expressions.tsv",
        help="금지·주의 표현 TSV",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("audit-output"),
        help="검수 결과 폴더",
    )
    args = parser.parse_args()

    try:
        rows = load_rows(args.input, args.sheet)
        records = [
            canonicalize_row(row, index)
            for index, row in enumerate(rows)
        ]
        config = load_config(args.config)
        phrase_rules = load_phrase_rules(args.phrases)
        audited = [
            audit_single(record, config, phrase_rules)
            for record in records
        ]
        pairs = add_similarity_findings(audited, config)
        for item in audited:
            item["priority"] = priority_for(item["issues"])
            item["recommended_action"] = recommendation(item["issues"])

        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_student_audit(args.output_dir / "student-audit.csv", audited)
        write_duplicate_pairs(args.output_dir / "duplicate-pairs.csv", pairs)
        write_report(
            args.output_dir / "priority-report.md",
            audited,
            pairs,
            config,
        )

        summary = {
            "records": len(audited),
            "P1": sum(item["priority"] == "P1" for item in audited),
            "P2": sum(item["priority"] == "P2" for item in audited),
            "passed": sum(item["priority"] == "통과" for item in audited),
            "duplicate_pairs": len(pairs),
            "output_dir": str(args.output_dir),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
