# Structured Fidelity Reconstruction

## Font and Spacing Calibration

Inventory source font names, weights, sizes, colors, baselines, line heights, paragraph gaps and column widths. Check installed fonts and any usable embedded font resources without installing fonts or redistributing them without authorization. Prefer an available exact face; otherwise compare plausible installed substitutes on representative Korean prose, English labels, bold headings and mathematical expressions. Record the chosen mapping and remaining differences.

Calibrate style groups, not unrelated individual characters: font family/weight first, then size and measured width, character spacing, baseline, line spacing and paragraph gaps. Keep source coordinates, page size and margins. Avoid excessive horizontal compression or overlaps to satisfy a global score. Inspect source/output/difference crops at normal size and enlarged view; font substitution never guarantees identical strokes. Re-export after changes and fix clipping, displaced lines, collisions and line-wrap changes before acceptance.

## Editable Headings

Create one coherent paragraph or text container per heading, with reusable chapter/section heading styles. Preserve the source size, color, alignment, position and spacing. Keep badges, shading and ornamental chapter numbers separate when needed; the actual title text must remain editable. A mixed heading contains ordinary Korean/English runs and native equation runs in source order. Do not convert a Roman chapter numeral or English word into mathematics.

Test editing a whole title in Hancom. It must not require selecting many character-sized boxes. Ensure a short representative replacement does not clip or overlap; restore the original before delivery. Large text changes may require manual layout adjustment and should be disclosed.

## Native Tables

Inventory each source table's rows, columns, cell coordinates, merges, border styles, fills, alignment and padding. Build a native Hancom table using COM or a validated Hancom-created HWPX table skeleton. Preserve overall placement and measured row heights/column widths. Populate ordinary prose as text and mathematical occurrences as native equation objects within the appropriate cells. Do not flatten a formula-containing cell to an image.

Remove superseded background borders, source cell glyphs and floating cell overlays without erasing neighboring content. Verify the final native table count, row/column structure, merges, cell content and rendered geometry. Open a representative cell and change its text to establish editability, then restore the source. Background lines plus floating text boxes do not qualify as a native table. If reconstruction fails, report that limitation rather than claiming the table is editable.

## Independent Graph Pictures

Visually identify each complete graph boundary, including curves, axes/arrows, ticks, numeric labels, coordinates, legends and formulas belonging to the graph. Exclude surrounding explanations, section headings and standalone formulas. Crop the original source directly, normally at 300 DPI; do not use a background whose labels have already been redacted. Preserve color, aspect ratio, physical placement and readable labels. Never stretch axes independently.

Insert each graph as a separate native picture object so it can be selected, moved and resized independently. Remove its source background occurrence and any rebuilt text/equation overlays. Ensure cropping does not truncate arrows or superscripts or include unrelated prose. Verify each picture against its original crop and select one in Hancom to confirm independent manipulation.

Graph-contained mathematics is intentionally image content under this policy. Maintain a source-hash-bound graph inventory with page, bbox, crop path, resolution and visual verification. Outside-graph math remains fully editable native equations. Do not pass graph boxes into the existing `keep_image_regions` as a way to bypass the old equation gate: that helper currently rejects mathematical image regions. Adapt task-local extraction and validation explicitly, preserving its safety and unresolved-math checks.

## Final Audit

Account for each source mathematical occurrence as either a native equation outside a graph or content inside a verified complete graph picture. Native equation counts/scripts must match the outside-graph inventory; graph counts/bounds must match the picture inventory. No occurrence may be omitted or rendered twice. Heading text and cell prose must remain text, including English labels and URLs.

Report separate checks for native equations, graph pictures, coherent headings, native table structure, typography/spacing and final page comparison. `all_equations_native` from the unmodified helper is not sufficient for a postprocessed file and must not imply graph labels are editable equations. Regenerate final-file XML checks, Hancom reopen/export and visual reports after all edits. Keep failed criteria and substituted fonts visible; do not silently exempt non-graph math or lower comparison thresholds.
