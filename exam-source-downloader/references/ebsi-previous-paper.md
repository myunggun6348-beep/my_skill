# EBSi Previous-Paper Notes

Use these notes when extending or debugging `scripts/download_exam_sources.py`.

## Families

`kice`

- Use for 평가원 수능 and 모의평가.
- EBSi target code: `D300`.
- User-facing years are academic years. The EBSi `yearList` values are calendar years, so academic year `N` is queried as `N - 1`.
- Common months: `06`, `09`, `11`.

`national`

- Use for 전국연합학력평가.
- EBSi target code: `D200`.
- User-facing years are calendar exam years.
- Set `--grade 1`, `--grade 2`, or `--grade 3` unless the user asks for all grades found.

## Download Functions

Parse these JavaScript calls from the AJAX HTML:

- `goDownLoadP(...)`: problem/question paper
- `goDownLoadJ(...)` or `goDownLoadJ2(...)`: answer file, often image
- `goDownLoadH(...)`: solution/explanation file

Normalize relative paths by prefixing:

```text
https://wdown.ebsi.co.kr/W61001/01exam
```

## Verification

Do not trust a successful HTTP response alone.

- Verify file headers: `%PDF`, PNG, or JPEG.
- Record `sha256` and `size_bytes`.
- Keep the AJAX HTML beside the manifest for missing-file debugging.
- Use `missing_by_kind` to decide whether the requested range is complete.

## Common Pitfalls

- For `kice`, do not send academic years directly as `yearList`; subtract one.
- EBSi answer keys may be image files, not PDFs.
- Subject IDs differ between `kice` and `national` listings.
- National Union records encode grade in the `irecord` value when available; if missing, fall back to title text.
- EBSi site structure can change. If parsing fails, save the raw AJAX HTML first and inspect current function arguments before changing script logic.
