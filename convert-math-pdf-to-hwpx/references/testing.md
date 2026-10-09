# Validation Procedure

```powershell
python -m pytest tests -q -p no:cacheprovider --basetemp work/test-run-unique
python scripts/doctor.py
python scripts/convert.py sample.pdf --config task-config.yaml --analyze-only
python scripts/convert.py sample.pdf --config task-config.yaml --overrides verified-equations.json --output outputs/sample_layout.hwpx
```

Use a fresh workspace test directory. Pytest may clear an existing `--basetemp`; do not use one holding needed files.

Tests cover mappings, bounds, stale/unverified overrides, mixed paper sizes, column coordinates, native objects, image-only pages, rotation, missing exports, and visual mismatches. Fake Hancom tests check package XML only; real Hancom integration is required before claiming fidelity.

## Gates

- Visually verified `math_audit` for every page; source formula counts equal reconstructed equation counts. Missing audits or unresolved mathematical regions block a build before Hancom starts.
- ZIP and section XML integrity; native equation scripts and count match analysis. A literal string or source crop does not count as a native equation.
- Expected editable text is retained (99.5 percent minimum). Character counts do not prove reading order.
- Native exported page count equals source; paper width/height differs by at most 1 point by default.
- At 144 DPI report normalized RGB difference and symmetric foreground-ink overlap within 1 pixel. The default 80 percent overlap gate is not an OCR-accuracy claim.
- Missing PDF, lost text, missing equations, changed geometry, or insufficient overlap is a validation failure.
- Verified complete graph pictures are intentional image content; report their count, bounds and labels separately. Other mathematical image regions remain failures. The unmodified helper does not implement this graph exception; explicitly adapt task-local validation without weakening outside-graph math checks.
- Require coherent editable heading containers and native table objects with correct cells, merges, borders, fills and equations. Floating cell text above background borders does not pass this structure check.
- Check typography by source style groups: font family/weight, size, width/spacing, baselines, line spacing, paragraph gaps and wrap positions. Preserve thresholds and disclose font substitutions; inspect local errors even when global similarity passes.

## Page Inspection

Inspect every original/result/difference page. Check headings, columns, margins, tables, graphs/labels, side notes, page numbers, inline baselines, fractions, inequalities, roots, and indices.

Reject missing content, duplicated glyphs, clipping, overlap, displaced formulas, blank pages, reordered content, and undisclosed fallback. Global scores can hide local errors: enlarge changed regions. Open a text box and converted equation in Hancom to confirm real editability.

Include inline symbols, mathematical headings and table expressions in the native inventory. Account for graph-contained labels in the separate verified graph inventory. Inspect crops for complete axes/labels, no neighboring prose, correct aspect ratio and no duplicated background/overlays. Select a graph picture, edit a coherent title and a native table cell in Hancom, then restore originals. Regenerate all checks against the final postprocessed file. Inspect raster formula replacements for matching backgrounds and intact neighbors. Test missing audits, stale counts, unresolved outside-graph math, partial-span overrides and native script tampering.

Inspect classification in both directions. Korean and English explanations, `Note`, acronyms, URLs/emails, section numbers and page numbers must not appear in native equation scripts. Mixed sentences must retain all prose around equation-only regions. Ambiguous single letters require source context, not a global alphabet-to-equation rule. Test `x축`, Korean particles following a formula, English sentences containing LaTeX, English labels, addresses, and standalone mathematical function expressions. Unsplit mixed prose/math must remain a blocking review rather than an automatically converted equation or a completed literal-text fallback.

Keep synthetic redistribution-safe fixtures in the skill; user PDFs and source renders belong only to task outputs.
