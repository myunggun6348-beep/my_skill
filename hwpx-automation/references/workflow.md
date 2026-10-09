# Workflow

## 1. Start from the new form, not from the old example

Treat every new `.hwp` or `.hwpx` file as a fresh adaptation target.

- Do not assume the previous form's anchors, table positions, or placeholder patterns still apply.
- Use older scripts and plans only as a scaffold.
- Re-derive the actual anchors from the new file before filling anything.
- Expect the user to keep providing new forms; the engine must adapt each time.

The reusable thing is the workflow, not the specific form.

## 2. Choose the path

### New or existing HWP/HWPX form

Use this path whenever the user gives a school or admin template, even if it looks similar to an earlier one.

1. Extract text with `extract_text.ps1`.
2. Inspect anchors, repeated labels, placeholders, and likely table cells.
3. Decide whether the target is:
   - plain text replacement
   - nth occurrence replacement
   - next table cell after a title or label sequence
   - HWPX XML table generation
4. Build or update a `fill_plan.json`.
5. Run the plan on a copy.
6. Validate text and position.

### New form intake checklist

For each new file, record the local facts before filling:

- source template path
- output path
- source content path or content payload
- required fields and missing values
- text anchors found in the template
- repeated labels and their order
- table candidates and whether they are real table controls
- validation checks that prove the result is in the right place

### Markdown manuscript to HWPX

Use this path when the user provides a Markdown draft and an HWPX manuscript form.

1. Generate the body with `fill_hwpx_from_markdown.py`.
2. Replace Markdown tables with placeholders plus JSON table specs.
3. Run `insert_hwpx_tables.ps1`.
4. Let `populate_hwpx_table_cells.py` fill cells and widths.
5. Validate with text extraction and XML spot checks.

## 3. COM vs XML responsibility

Use COM for:

- opening and saving HWP/HWPX
- extracting plain text
- finding anchors
- inserting blank table skeletons at exact document positions

Use XML for:

- deterministic cell text population
- column width calculation
- low-noise repeated edits to `section0.xml`
- HWPX memo insertion when the target anchor is known

Do not collapse these responsibilities unless there is a strong reason.

When editing paragraph text in `section0.xml`, remember that HWPX page controls
may be stored inside the same top-level paragraph as body content. A recursive
`.//hp:t` query can include header, footer, footnote, or endnote text. Exclude
`hp:t` descendants of `hp:header`, `hp:footer`, `hp:footNote`, and `hp:endNote`
before splitting headings or replacing paragraph text.

If COM text extraction shows table content as one item per line, do not treat that as a table failure by itself. Confirm the XML contains `hp:tbl` and populated `hp:tc` cells.

### HWPX memo insertion

Use this path when the user asks to attach review comments or memos at a
specific place inside an `.hwpx` file.

1. Work on a new output copy; do not overwrite the source.
2. Search `Contents/section*.xml` for the exact visible target text.
3. Prefer a paragraph whose concatenated `hp:t` text exactly equals the target
   phrase. If the phrase is embedded in a larger paragraph, anchor the smallest
   safe containing paragraph and report that choice.
4. Add `hp:memogroup` if missing, then append `hp:memo` with a stable `id`,
   `memoShapeIDRef`, `author`, `createDateTime`, and `hp:paraList/hp:p` memo
   body.
5. Insert a matching `hp:run/hp:ctrl/hp:fieldBegin type="MEMO"` before the
   target paragraph content and a matching `hp:fieldEnd` after it.
6. Set field parameters consistently:
   - `ID`: same value as `hp:memo/@id`
   - `Number`: memo display number, usually `1` for a one-off test
   - `CreateDateTime`: current local timestamp
   - `Author`: `J` unless the user gives another author
   - `MemoShapeID`: same memo shape reference used by the document, usually `1`
7. Remove `hp:linesegarray` from the edited target paragraph after inserting
   the field controls.
8. Repack the HWPX with all original ZIP entries preserved except the edited
   section XML.

Validate memo insertion with:

- ZIP package test returns OK.
- Exactly the expected new `hp:memo` exists.
- Exactly the expected new `hp:fieldBegin type="MEMO"` exists.
- `hp:memo/@author` and field parameter `Author` match, normally `J`.
- The field parameter `ID` matches the memo `id`.
- The target paragraph contains both the matching field begin and field end.
- The output section XML does not contain an unintended previous author such as
  a temporary test name.
- If the user checks in Hangul, the memo balloon appears at the intended text.

## 4. Table heuristics

### Placement

- Insert multiple tables from bottom to top.
- Delete the placeholder selection before creating the skeleton table.
- Re-open the document between risky COM steps if state becomes unstable.

### Width

- Target total width: about 92% of the detected body text width.
- Derive a score per column from max length and average length.
- Apply minimum widths so label columns do not collapse.
- Apply maximum share caps so description columns do not consume the whole table.

### Cell styling

- Treat cell background and borders as cell properties, not paragraph properties.
- Use `hp:tc/@borderFillIDRef` for shaded label/header cells and a plain cell border fill for body cells.
- Keep the `hp:p/@paraPrIDRef` used inside cells free of `hh:border`, paragraph background, or character shading.
- If text appears inside a small inner rectangle, the problem is usually a paragraph-level border/background inside the cell. Remove that paragraph styling; do not solve it by changing the cell fill.
- Reference documents often contain useful table colors but unsafe paragraph styles. Copy the visual intent, then clean or clone paragraph styles before delivery.

### Schedule and lesson-plan layout

When a schedule-style table has a time column and a long content column, avoid
placing all times in one tall cell and all contents in one adjacent tall cell.
That layout drifts visually because wrapped content takes different heights.

- Prefer one real `hp:tr` per time block, with the time cell and content cell
  sharing the same `hp:cellAddr/@rowAddr`.
- Update `hp:tbl/@rowCnt`, downstream row addresses, and any merged label cell
  `hp:cellSpan/@rowSpan` after adding rows.
- Set row heights intentionally with `hp:cellSz/@height`; do not rely on manual
  blank lines in the time cell to line items up.

For content that begins with an item marker such as `○`, use hanging indent
rather than leading spaces:

- First line: marker and title begin at the normal paragraph start.
- Wrapped continuation lines: indent under the body text, not under the marker.
- If the user manually adjusts one good row, inspect that row's
  `hp:p/@paraPrIDRef` and the referenced `hh:paraPr` margins in
  `Contents/header.xml`; apply the same paragraph style to matching rows.
- Remove descendant `hp:linesegarray` after changing paragraph style or text so
  Hangul recalculates wrapping.

### Debug order

When a table looks wrong, inspect in this order:

1. Is it a real `hp:tbl`?
2. Is the placeholder gone?
3. Do all `hp:tc` cells contain text?
4. Are `hp:cellSz width` values non-uniform when they should be?
5. Do cell `borderFillIDRef` values point to the intended cell fills?
6. Do the table-cell paragraphs avoid `hh:paraPr/hh:border` and other paragraph-level box styling?
7. Only then tune alignment, padding, and height.

### Page-boundary behavior

When a long table is pushed to the bottom of a page or appears squeezed into one
page, inspect the table pagination attributes in `Contents/section0.xml`.

- `hp:tbl/hp:pos/@treatAsChar="0"` corresponds to disabling "treat as character".
- `hp:tbl/@pageBreak` controls the page-boundary split behavior, but the XML
  value is not always intuitive from the Hangul UI label. Prefer comparing
  against a user-made learning/reference file and copying the verified value.
- In the verified lecture-plan case, the reference table used
  `pageBreak="TABLE"`, `hp:pos/@treatAsChar="0"`, and the same table content and
  row geometry. Applying those table-level values fixed the page-bottom squeeze.
- Do not solve this by changing cell text, row text, or paragraph layout first;
  the table anchoring and page-break attributes are the primary facts to check.

## 5. Validation discipline

Use text extraction for content presence, not for layout proof.

For forms:

- Verify required text is present.
- Verify old instruction/example text is removed when required.
- Verify inserted text is anchored to the intended location, not appended at the end.

For HWPX tables:

- Count `hp:tbl`.
- Confirm placeholder count is zero.
- Confirm all required cell strings exist inside table cells.
- Inspect representative `hp:cellSz width` values after width tuning.
- Inspect representative table-cell `paraPrIDRef` values in `Contents/header.xml`; cells should not use paragraph styles with `hh:border`.
- For public-facing formatting, open the final HWP/HWPX in Hangul or export/render it and visually confirm table shading, borders, and text alignment.

For documents with existing page controls:

- Compare source and output counts/text for `hp:header` and `hp:footer`.
- Confirm footer text did not move into header text after any first-paragraph or
  section-heading rewrite.
- Render at least the first affected page when header/footer placement matters.

## 6. Reuse policy

When using this skill in another folder:

1. Prefer copying the bundled `scripts/` into the target workspace.
2. Keep project-local copies editable.
3. When the project-local engine improves, sync the changes back into this skill.

This keeps the skill useful as a transportable baseline instead of a frozen note.
