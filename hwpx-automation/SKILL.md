---
name: hwpx-automation
description: Analyze, adapt to, fill, and refine Korean HWP/HWPX forms and manuscript templates with a mixed COM plus HWPX XML workflow. Use when Codex needs to work on new or existing `.hwp` or `.hwpx` files, Hangul forms, Korean form templates, manuscript forms, report forms, submission forms, table-heavy templates, template analysis, anchor discovery, fill-plan authoring, Markdown-to-HWPX manuscript generation, real table insertion, table width tuning, or when a new workspace needs to bootstrap reusable HWP/HWPX automation scripts.
---

# HWPX Automation

Use this skill when working on Korean HWP/HWPX automation tasks, especially when the user keeps introducing new forms. The skill is not for one fixed template; it is for repeatedly adapting to new `.hwp` and `.hwpx` files. Prefer the local workspace engine if it already exists. If the workspace does not have one, bootstrap it from this skill's bundled `scripts/`.

## Quick Start

1. Preserve the original `.hwp` or `.hwpx` and work on a copy.
2. Treat every provided form as a fresh target until proven otherwise.
3. Decide which path matches the request:
   - New form or template: extract text first, inspect anchors and table structure, then create or revise a `fill_plan.json`.
   - Existing form/template fill: reuse the same process, but keep the prior engine only as a starting point.
   - Markdown manuscript to HWPX: generate body first, then post-process real tables.
   - HWPX memo insertion: find the exact text anchor, add both the memo body and the visible MEMO field anchor.
4. Validate with both:
   - plain-text extraction via `extract_text.ps1`
   - HWPX XML spot checks when tables or positions matter

Read [references/workflow.md](references/workflow.md) before changing table logic, bootstrapping a new workspace, or deciding between COM and XML.

## Bootstrap a Workspace

If the current folder lacks an HWP/HWPX engine:

1. Create or reuse a local `scripts/` directory.
2. Copy the bundled files from this skill's `scripts/` into the workspace.
3. Adapt paths and output names to the workspace.
4. Keep the pipeline split by responsibility:
   - COM for document position and table skeleton insertion
   - XML for deterministic table text and layout completion

Do not treat any one template as canonical. The reusable asset is the engine and the adaptation workflow, not the current form. Never carry over a previous fill plan without rechecking anchors and table locations in the new file.

Use these bundled files as the default engine:

- `scripts/AutoHwp.psm1`
- `scripts/extract_text.ps1`
- `scripts/fill_from_plan.ps1`
- `scripts/fill_hwpx_from_markdown.py`
- `scripts/insert_hwpx_tables.ps1`
- `scripts/populate_hwpx_table_cells.py`

## Table Rules

Plain-text extraction flattens tables, so it is useful for content checks but not enough for table validation.

Do not rely on COM cell-by-cell typing for complex HWPX tables.

Use this pattern instead:

1. Emit placeholder paragraphs for tables during body generation.
2. Insert blank table skeletons with COM, in reverse document order.
3. Re-open `Contents/section0.xml` and fill every `hp:tc` cell directly.
4. Recalculate column widths from content length.

Style table cells at the cell level, not the paragraph level:

- Apply table borders and background colors with `hp:tc/@borderFillIDRef` and table-level border fills.
- Keep paragraphs inside cells plain: alignment, margins, and line spacing only.
- Do not leave `hh:paraPr/hh:border`, paragraph background, or character shading on table-cell paragraphs. These create small inner boxes around the text instead of clean full-cell shading.
- When reusing a reference template, inspect the `paraPrIDRef` values used inside cells and clone or clean them before final delivery.

Treat table problems in this order:

1. Confirm the content is inside a real table.
2. Confirm placeholder count is zero.
3. Confirm each cell has text in XML.
4. Confirm table-cell paragraphs do not carry paragraph border/background styling.
5. Tune column widths, row height, and alignment only after 1-4 are stable.

For schedule, lesson-plan, or program tables:

- If a time column must align with long content, prefer one table row per time
  block instead of stacking all times in one cell and all content in another.
  Update `hp:tbl/@rowCnt`, each `hp:cellAddr/@rowAddr`, and any label
  `hp:cellSpan/@rowSpan` so the left time and right content start on the same
  row.
- For item-marker text such as `○ ...`, use a hanging-indent paragraph style:
  the first line should start at the marker, and only wrapped continuation
  lines should indent. Do not simulate this with leading spaces.
- When the user manually fixes one row, treat that row's `hp:p/@paraPrIDRef`
  and its `hh:paraPr` margin values as the reference style, then apply it to
  sibling content rows and remove stale `hp:linesegarray`.

For long tables that may cross a page boundary, check table-level pagination
properties in `Contents/section0.xml`:

- `hp:tbl/hp:pos/@treatAsChar="0"` disables Hangul's "treat as character"
  behavior. If this remains `"1"`, Hangul may try to keep the whole table in a
  text-line flow and squeeze content toward the page bottom.
- Use a user-approved reference file when choosing `hp:tbl/@pageBreak`; Hangul
  UI labels do not map intuitively to XML names. In one verified lecture-plan
  form, the desired page-boundary behavior saved as `pageBreak="TABLE"` while
  `treatAsChar="0"` was the decisive fix.
- Copy only the table pagination attributes from the reference unless content,
  row count, and cell geometry were intentionally changed.

For layout-sensitive formatting work, validate with an actual HWP open/render/capture when possible, not only text extraction.

## Memo Rules

For HWPX comments/memos, do not add only the memo text. Hangul shows a memo
balloon only when the section memo body and the body-field anchor agree.

- Preserve the source file and create a copy before inserting memos.
- Locate the exact target text in `Contents/section*.xml`; prefer an exact
  standalone `hp:p` match when one exists.
- When a memo concerns a specific phrase, do not append the MEMO field at the
  paragraph or table end. Insert `hp:fieldBegin` immediately before the visible
  problematic text and `hp:fieldEnd` immediately after it so Hangul highlights
  the actual review target.
- In table-heavy HWPX files, avoid anchoring to the outer paragraph that owns a
  whole table. Prefer the leaf `hp:p` containing the visible target text; when
  the same text repeats, use nearby context and an occurrence index, then
  validate the selected text between `fieldBegin` and `fieldEnd`.
- Add the memo content under `hp:memogroup/hp:memo`.
- Add a matching `MEMO` field control at the target paragraph with
  `hp:fieldBegin` and `hp:fieldEnd`.
- Put the actual comment/review text in the `hp:fieldBegin/hp:subList` visible
  text as well as in `hp:memogroup/hp:memo`. Use opaque IDs only for the `ID`
  parameter and `hp:memo/@id`; otherwise Hangul may show the ID text such as
  `memo-j-001` instead of the review opinion.
- Keep the field parameter `ID` equal to the `hp:memo/@id`.
- Use author `J` in both the field parameter `Author` and `hp:memo/@author`
  unless the user explicitly gives another name.
- Use the document's existing memo shape, normally `memoShapeIDRef="1"` and
  field parameter `MemoShapeID=1`, after confirming `hh:memoProperties`.
- Remove stale `hp:linesegarray` from the edited target paragraph so Hangul can
  recalculate the layout after the anchor insertion.
- Validate the package with a ZIP test and XML spot checks: memo count, MEMO
  field count, author values, memo ID linkage, and target paragraph anchoring.
- When validating that body content was not edited, compare the source text with
  the output after excluding only the newly inserted `MEMO` fields and
  `hp:memogroup`, not every `hp:fieldBegin`. Read `hp:t` text with full
  `itertext()` semantics so text split by line-break child nodes is not dropped.
- When the user needs visual assurance, open the output in Hangul and confirm
  the memo balloon appears at the intended visible text.

## Header and Footer Controls

HWPX page controls can be nested inside ordinary-looking body paragraphs, often
near the first paragraph as `hp:ctrl/hp:header` and `hp:ctrl/hp:footer`.

- When reading or replacing body paragraph text, do not use a broad
  `.//hp:t` selection unless you explicitly exclude text under `hp:header`,
  `hp:footer`, `hp:footNote`, and `hp:endNote`.
- If a first paragraph contains both page controls and body text, edit only the
  body text nodes. Otherwise a heading split or replacement can move footer
  text into the header and leave the footer empty.
- After modifying section-level or first-page content, compare header/footer
  text counts and rendered placement against the source HWPX before delivery.

## Update Discipline

When the local project improves the engine:

1. Patch the project first.
2. Re-run the workflow on a real artifact.
3. Copy the improved scripts back into this skill.
4. Update `references/workflow.md` if the rules changed.
5. Re-validate the skill before reinstalling or re-copying it elsewhere.
6. Sync the global install from the source copy when working in the `auto_hwpx` project.
