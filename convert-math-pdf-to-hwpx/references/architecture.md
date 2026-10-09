# Layout and Override Contract

## Pipeline

The pipeline below describes the bundled scaffold. The final document must also follow [structured-layout.md](structured-layout.md): coherent editable headings, native tables, independent complete graph pictures and font/spacing calibration. These stages require task-local reconstruction or postprocessing; the unmodified helper does not implement them. Revalidate the final artifact, not an earlier scaffold.

`inspect_pdf -> extract_fidelity -> analysis.json -> HWPX package -> isolated Hancom reopen/save/PDF export -> validation/report`

Copy one source page at a time. Redact reliable text glyphs without removing images or vector strokes; embed the rendered remainder in `BinData/`. Native Hancom-created text-box/equation skeletons supply compatible XML. Set paper-relative floating positions, zero margins, explicit sizes, foreground order, colors, character sizes, and measured width ratios. Separate sections permit different paper sizes. Reopen/save through Hancom before exporting PDF.

## Coordinates

Pages are one-based. Boxes are `[left, top, right, bottom]` in PDF points, in visible page orientation (72 points/inch). HWPX uses 100 units per point. Boxes must be finite, nonempty, and within the page. Normalize rotated pages; individual non-horizontal writing stays in the background and is reported.

Text elements contain `kind`, `page`, `bbox`, `origin`, `text`, `font`, `font_size_pt`, `color`, `flags`, and `confidence`. Equations contain `hwp_command` and source boxes. Page records hold physical dimensions, background/source paths, elements, and reviews.

## Verified Math

Read rendered source formulas before declaring an override verified. Do not rely solely on legacy-font text extraction.

```json
{
  "source_sha256": "SHA256_OF_THE_EXACT_INPUT_PDF",
  "pages": [{
    "page": 1,
    "math_audit": {"verified": true, "formula_count": 1},
    "keep_image_regions": [[300, 80, 370, 110]],
    "equations": [{
      "bbox": [80, 130, 150, 155],
      "verified": true,
      "hwp_command": "{x+1} over {x-2}",
      "font_size_pt": 10,
      "color": 0
    }]
  }]
}
```

Supported `latex` can replace `hwp_command`. Require matching SHA-256, valid pages, explicit verification, valid bounds/font size, balanced commands, and nonoverlapping equation boxes. Do not erase neighboring prose with oversized boxes. Keep-image regions and equation boxes must not overlap. Pass `--overrides file.json` or `layout.overrides`.

Every page needs `math_audit: {"verified": true, "formula_count": N}` after visual inspection. In the unmodified scaffold, `N` includes graph labels; in the final structured reconstruction it counts native equations outside verified graph pictures, with a separate source-bound graph inventory. Explicitly adapt extraction and validation for that distinction; do not reuse a stale count. Group contiguous expressions and count repeated occurrences separately. A page without native equations needs `N: 0`. The inventory comes from source inspection, not generated output. Raster/outlined math still requires visual audit.

For raster formulas on a visually verified solid background, add `"replace_raster": true, "background_color": "#FFFFFF"` (use the actual background color) to the equation. The pipeline clears only that rectangle in the rendered background before placing the native object. Verify the rectangle contains the complete formula and no prose, table borders, graph lines, or nonuniform background. If it does, reconstruct the affected graphics or prepare a clean background before using replacement; a broad white rectangle is not acceptable. Raster intersections without explicit replacement/color are rejected. Inspect the source and cleared background to reject remnants or erased neighbors.

Text-layer overrides remove glyphs and fully contained vector fraction/root strokes without deleting paths extending outside the formula box. If strokes share a path with graphics, prepare a clean background and verify the local replacement. Overrides split prose runs at glyph boundaries. Mathematical glyphs inside `keep_image_regions` still fail the bundled helper's gate; this field is not a graph-picture implementation. Use explicit task-local graph handling as described in structured-layout.md. Normalize rotated pages while preserving visible size and annotations.

Run `--analyze-only` with overrides to inspect remaining `requires_equation` review items before building. Missing audits, mismatched counts, or unresolved math cause exit `3` before native export. Native reopening validates equation objects and their scripts again. Check each rendered native equation, not merely its command; exact script/count matching and image overlap do not prove mathematical correctness.

## Fonts

Map installed font files and correct family names when available:

```yaml
layout:
  font_map:
    OriginalFontName:
      face: "Installed family"
      file: "C:/Windows/Fonts/example.ttf"
```

Fallbacks use Malgun Gothic for Gothic/title/sans faces and HY Shin Myeongjo for serif text. Width ratios are measured against source spans and clamped to 50-200 percent. Width matching cannot guarantee identical strokes or prevent overflow after edits.

## Native Access

Use `DispatchEx`, not a user's shared document. Register only an already-configured file-access module. Without it, request approval in a visible Hancom window; never change global security settings. Native fidelity export runs in a worker with `hwp.timeout_seconds: 120`. On timeout, terminate only the exact process handle obtained from that worker's own COM window. Retain the unvalidated draft and report failure. Existing user sessions remain untouched.

Outputs default to `outputs/`, not the source folder. Explicit `--overwrite` permits only named output replacement. Never recursively clear task directories.

`math_ocr.py` is optional and is not automatically wired into conversion. The old reflow path exists only for explicitly requested continuous editing.

Hancom documents that file-access approval dialogs cannot be suppressed by `SetMessageBoxMode`: [official developer response](https://forum.developer.hancom.com/t/topic/1560).
