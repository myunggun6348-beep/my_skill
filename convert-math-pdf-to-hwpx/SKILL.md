---
name: convert-math-pdf-to-hwpx
description: Convert Korean mathematics PDFs to HWPX on Windows with Hancom Office, matching original typography and spacing, rebuilding editable headings and native tables, preserving complete graphs as pictures, and converting mathematics outside graphs into native equations.
---

# Convert Math PDF to HWPX

Default to **fidelity with editable structure**: match source typography and spacing, rebuild headings as coherent editable paragraphs and tables as native Hancom tables, and preserve each complete graph as an independent picture. Convert mathematics outside graph pictures into native equations, including inline variables, table formulas and mathematical headings. Korean and English prose and ordinary numbering remain text.

Image-only math outside verified graph pictures and literal-text formulas are unfinished conversion. Keep `math.require_all_equations: true`; graph pictures are an explicit object policy, not permission to exempt other formulas. The agent must visually reconstruct formulas the text-layer helper cannot recognize.

## Text and Math Classification

Classify by meaning and visual context before choosing the HWPX object. Language, italic styling, font names, and the presence of Latin letters alone do not establish mathematics.

| Source content | HWPX object |
|---|---|
| Korean explanations, English sentences, titles, `Note`, `Example`, `Solution`, `EBS`, URLs and email addresses | Ordinary text with the original language and casing |
| Question/section/page numbers and ordinary labels | Ordinary text; do not include them in the equation inventory |
| A complete graph, including curves, axes, ticks, coordinates, legends and mathematical labels inside its verified boundary | One independent picture; no separate equation/text overlays |
| Variables used mathematically, such as `a`, `n`, `x`, `y`, `N`, outside graph pictures | Native equation, after verifying their mathematical role |
| Powers, fractions, roots, logarithms with their bases, relations and contiguous formulas | Native equation |
| Mixed prose and math, such as `x축`, `함수 y=a^x의 그래프`, or `Find x when x=2` | Split at glyph boundaries: prose remains text and only the mathematical occurrences become equations |

An isolated `A`, `I`, `O`, number, or abbreviated word needs context: a variable, origin label, or geometric label is math; a heading, pronoun, chapter numeral, or acronym is text. Mathematical functions such as `log` and `sin` are part of a formula only when used mathematically. A title containing a formula is split just like a sentence.

Never generate equation overrides for all alphabetic/numeric spans or all review items. A legacy-font/private-use review is a request to inspect the source, not permission to insert the extracted text or a placeholder into an equation. Whitespace, tabs, and nonprinting layout controls are not formulas. Keep unknown visible glyphs pending until their role is identified; distinguish decorative numbering from mathematical notation.

Before marking `math_audit` verified, account for every mathematical occurrence: native equation outside graphs or content within a verified complete graph picture. Check every equation contains actual mathematics rather than prose or numbering. Record graph boundaries separately from equation-only regions; do not absorb neighboring explanations into pictures. Verify surrounding Korean and English survives with its original characters and order.

## Typography and Editable Structure

Read [references/structured-layout.md](references/structured-layout.md) before reconstruction. It defines font calibration, coherent headings, native tables, independent graph pictures and their acceptance checks. Prefer matching installed fonts, then measured substitutes; do not claim identical appearance when the source font is unavailable. Preserve source page geometry and placement while improving object structure, not by applying whole-document reflow.

The bundled fidelity helper currently produces small text boxes, background table borders and native graph labels. Its output is an intermediate scaffold, not fulfillment of the new structure policy. Adapt task-local reconstruction or use Hancom COM/HWPX postprocessing for headings, tables and graph pictures. Remove superseded overlays/background content and rerun validation on the final file. Do not invent unsupported config switches or claim the existing CLI performs these steps automatically.

## Workflow

1. Preserve the source PDF. Use task-local `work/` and `outputs/`; never clear a shared directory or overwrite the source.
2. Read [references/mvp-scope.md](references/mvp-scope.md) for editability boundaries. Run `python scripts/doctor.py`; install `requirements.txt` in a task-local environment if needed.
3. Copy `assets/config.example.yaml` to a task-local config. Keep `pipeline.mode: fidelity`, task-local paths, and 300 DPI backgrounds unless size requires lower resolution.
4. Analyze first:

   ```powershell
   python scripts/convert.py input.pdf --config task-config.yaml --analyze-only
   ```

5. Inspect every source page and enlarge mathematical regions. Read [references/architecture.md](references/architecture.md) and [references/hwp-equation-rules.md](references/hwp-equation-rules.md). Inventory native equations outside verified graph pictures, and separately inventory headings, table cells and graph boundaries. Legacy fonts can extract plausible but incorrect Unicode: verify fractions, roots, signs, powers, subscripts, and bounds visually. Transcribe unconverted equations into source-hash-bound overrides. Use `math_ocr.py` only as a visually checked candidate generator. Mark each page's audit only after native equations and graph-contained mathematics are accounted for. Unreadable content remains a blocker.
6. Build:

   ```powershell
   python scripts/convert.py input.pdf --config task-config.yaml --overrides verified-equations.json --output outputs/input_layout.hwpx
   ```

7. Complete the structured reconstruction and font/spacing calibration, then reopen the final file in a separate Hancom instance and export PDF. An unregistered file-access module may require user approval in a visible Hancom dialog. Do not alter global security settings or register an unrestricted approval DLL. Stop a stalled task instance without terminating the user's existing sessions.
8. Inspect every source/result/difference page using [references/testing.md](references/testing.md). Check final headings, native tables, independent graph pictures, fonts, spacing, page geometry and local overlaps. Compare every native equation against its source crop and open a representative equation in Hancom's editor. Require zero unresolved math and native scripts/counts matching the outside-graph inventory. Report graph picture coverage separately; never misrepresent graph-contained labels as native equations. Regenerate reports after postprocessing. Fix failed comparisons before claiming successful conversion.
9. Deliver the HWPX, rendered PDF, verified equation inventory, analysis, and report. Disclose substituted fonts and nonmathematical image regions. Exit `2` means remaining review limitations; exit `3` means validation failure. A pre-build equation failure is a checkpoint: finish reconstruction and rerun instead of delivering an image-only draft as completed.

## Fidelity Rules

- Use each source page's physical size and visible orientation, not universal A4. Coordinates are PDF points from the visible page's upper-left corner.
- Keep columns, margins, headings, colors, table borders, side notes, page numbers, and drawings at source positions.
- Remove reliable glyphs from the background before placing **visible** editable text boxes. Hidden text behind a page screenshot is not editable reconstruction.
- Preserve each complete graph as one independent picture, including all internal mathematical labels; no duplicate label overlays. This exception does not cover neighboring prose, table formulas or standalone equations.
- Rebuild tables as native Hancom table objects with editable cells, matching row/column dimensions, merges, borders, fills, alignment and padding. Cell mathematics remains native equations.
- Use supported reliable text-layer expressions or visually verified overrides for every equation. Write native `hwp_command` directly for syntax beyond the small LaTeX adapter; balanced braces do not establish semantic correctness. Remove original glyphs/root/fraction strokes before placing the native object, preserving adjacent prose and graph/table lines.
- Match font family/weight, size, color, character width/spacing, baseline, line spacing and paragraph gaps against source crops. Record substitutions and residual differences; do not lower similarity thresholds to force a pass.
- Rebuild headings as coherent styled paragraphs or one text container per heading, not images or character-sized boxes; use native equation runs for mathematical parts. Keep decorative badges separate from editable title text.
- Retain source-positioned body layout unless reflow is requested. Fixed boxes are not continuous paragraphs; warn that substantial edits can outgrow them.
- Scan-only PDFs require visually verified equation transcription even without OCR. `math_ocr.py` is an optional helper, not an automatic stage in this pipeline.
- Use `editable` reflow only when explicitly requested. Its legacy extractor does not yet consume the verified inventory, so its automatic image/literal fallbacks are drafts; finish native equation reconstruction and the same audit before delivery.
- Native reopening and PDF comparison are required. ZIP validity or a high global pixel score cannot replace page inspection and math verification.

## Resources

- [references/structured-layout.md](references/structured-layout.md): typography calibration, editable headings/tables and graph-picture policy.
- [references/architecture.md](references/architecture.md): coordinate contract, fonts, overrides, package/native flow.
- [references/testing.md](references/testing.md): regression and visual acceptance checks.
- [references/hwp-equation-rules.md](references/hwp-equation-rules.md): supported formula syntax.
- `scripts/preserve_layout.py`: glyph redaction, source-positioned text/equations, embedded backgrounds.
- `scripts/convert.py`: analysis, modes, conversion, overwrite protection, reports.
- `scripts/validate_output.py`: native counts, text coverage, paper/page checks, image comparisons.
- `assets/canvas-template.hwpx`: minimal Hancom-created text-box/equation skeleton, not a source-specific document.
