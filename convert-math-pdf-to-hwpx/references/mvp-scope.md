# Coverage and Boundaries

Final fidelity reconstruction preserves source page geometry, columns, decoration and typography as closely as available fonts permit. Headings are coherent editable paragraphs/containers; tables are native Hancom tables; each complete graph is an independent picture including its internal labels. Mathematics outside graphs is native equations, including inline, table and heading occurrences. See [structured-layout.md](structured-layout.md).

Normal Unicode text is editable in small fixed-position boxes. Legacy math fonts, private-use glyphs, non-horizontal math, and scans require visual verification and equation overrides. The analysis may temporarily retain them as image regions, but unresolved math prevents a completed build. Blank pages retain their geometry and receive a verified zero-formula audit.

Title prose must be editable even when its source font is unavailable: calibrate an installed substitute and disclose the difference. Decorative badges may remain pictures. Mathematical heading parts require native equations.

The bundled helper still outputs floating text boxes, background table borders and native graph labels. This is a scaffold and needs task-local reconstruction/postprocessing to satisfy native table and independent graph-picture requirements. Do not claim the unmodified CLI automatically provides them. Unsupported math outside graphs requires verified native transcription.

## Tradeoffs

- Missing fonts are substituted and width-matched, so glyph shapes need not be identical.
- Fixed boxes retain positions but do not offer flowing paragraph editing. Substantial edits require checking size and overlap.
- Raster resolution affects sharpness and file size; it cannot preserve infinite vector scalability.
- Flattened source annotations are not native HWP annotations.
- Native equation rendering can differ from PDF typography. Visually check every replaced formula.
- Similarity scores are not mathematical accuracy. Verify minus signs, fractions, roots, indices, bounds, and inequalities independently.

## Reflow

`--mode editable` retains sequential COM reconstruction when the user explicitly requests continuous editing. It does not promise original paper size, columns, or spacing. Its legacy extractor does not consume the verified override inventory; automatic output alone cannot satisfy the all-equations gate. Finish native reconstruction and audit before delivery. Prefer fidelity by default.

## Acceptance

Require final-file native reopening/export, original page count/geometry, retained content, coherent editable headings, native table structure, independent graph pictures and inspected typography/spacing. Match native scripts/counts to the outside-graph inventory and verify graph coverage separately, with zero unaccounted math. Disclose image-only graph labels and decorations. Missing content, export or failed comparison remains a validation failure even when the ZIP is valid.
