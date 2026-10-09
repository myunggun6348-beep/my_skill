---
name: exam-source-downloader
description: Download and verify Korean exam source files for CSAT, KICE mock exams, and National Union mock exams, including question papers, answer files, and solution/explanation PDFs from EBSi previous-exam listings. Use when Codex needs to collect 평가원 수능 or 모의평가 PDFs, 전국연합학력평가 문항/정답/해설 files, EBSi 해설지, previous-exam source archives, or a manifest-backed exam-file download set by year, month, grade, subject, and file type.
---

# Exam Source Downloader

Use this skill when the user asks to download Korean previous-exam source files:

- 평가원 수능 or 모의평가: question paper, answer, solution/explanation
- 전국연합학력평가: question paper, answer, solution/explanation
- EBSi previous-exam files by year, month, grade, subject, or curriculum

The default repeatable path is the bundled `scripts/download_exam_sources.py` script. It calls the EBSi previous-paper AJAX endpoint, parses `goDownLoadP`, `goDownLoadJ`/`goDownLoadJ2`, and `goDownLoadH`, downloads the files, verifies headers and hashes, and writes a JSON manifest.

Read [references/ebsi-previous-paper.md](references/ebsi-previous-paper.md) before changing provider logic, adding new subject IDs, or debugging missing files.

## Quick Start

For 평가원 수능/모의평가 sources, use `--exam-family kice`.

```powershell
python ".\scripts\download_exam_sources.py" `
  --exam-family kice `
  --subject earth-science-ii `
  --years 2024-2026 `
  --months 06,09,11 `
  --kinds problem,answer,solution `
  --out ".\downloads\kice_earth2"
```

For 전국연합학력평가 sources, use `--exam-family national` and specify grade.

```powershell
python ".\scripts\download_exam_sources.py" `
  --exam-family national `
  --grade 2 `
  --subject earth-science-i `
  --years 2020-2025 `
  --months 06 `
  --kinds problem,solution `
  --out ".\downloads\high2_june_earth1"
```

Use `--dry-run` first when exploring a new subject or exam range. Use `--overwrite` only when the user explicitly wants to replace existing files.

## Workflow

1. Clarify the requested source set:
   - exam family: `kice` for 평가원 수능/모의평가, `national` for 전국연합학력평가
   - years: academic years for `kice`, calendar exam years for `national`
   - months: usually `06,09,11` for `kice`; often `03,06,09,11` depending on grade for `national`
   - grade: required for `national` unless the user explicitly wants all grades found
   - subject and file kinds: `problem`, `answer`, `solution`
2. Run the script into a new output folder. Do not mix new downloads into a hand-curated source folder unless the user asks.
3. Inspect the manifest:
   - `ok` should be true for complete runs.
   - `missing_by_kind` should be empty unless missing files are expected.
   - each item should have `verified: true`, a valid header, file size, and `sha256`.
4. If files are missing, save the AJAX HTML and manifest as evidence, then adjust subject ID, `exam-family`, grade, months, or custom subject settings.
5. Keep downloaded source files untouched. Put any derived crops, OCR, HWPX, PPT, or worksheet outputs in a separate folder.

## Subject Handling

The script includes built-in aliases for common science subjects and the high-school 2015 subject set used by EBSi National Union listings.

Use built-in aliases first:

- `earth-science-i`
- `earth-science-ii`
- `physics-i`
- `physics-ii`
- `chemistry-i`
- `chemistry-ii`
- `life-science-i`
- `life-science-ii`

For National Union listings, `--subject all` downloads every built-in 2015 subject for that family. For KICE listings, `--subject all` downloads every built-in KICE subject currently mapped in the script.

For a subject not in the map, inspect the EBSi previous-paper form and pass:

```powershell
--subject custom `
--subject-id "<EBSi subject id>" `
--subject-label "<Korean subject label>" `
--form-field "<form field name>" `
--area-order "<area order>"
```

## Verification Rules

Treat the manifest as the source of truth.

- PDF files must start with `%PDF`.
- PNG/JPG answer images must have matching image headers.
- Every downloaded item records `size_bytes`, `sha256`, `source_url`, `output`, and `verified`.
- A run is incomplete if requested year-month-kind combinations are listed in `missing_by_kind`.
- If EBSi serves an answer key as an image instead of PDF, accept the image only when the detected header matches.

When sandboxed network access fails, rerun the same command with network escalation. The workflow requires live access to `www.ebsi.co.kr` and `wdown.ebsi.co.kr`.

## Limits

This skill uses EBSi previous-exam listings as the default provider because they expose 평가원 and 전국연합 source files in a consistent downloadable form. If the user explicitly requires the official KICE website rather than the EBSi mirror, inspect the current KICE page live, download the files manually or with a task-local script, and still write a manifest with the same fields.
