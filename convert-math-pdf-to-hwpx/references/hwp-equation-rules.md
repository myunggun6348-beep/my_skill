# Hangul Equation Conversion Rules

Use conservative, brace-preserving transformations. Reject malformed input instead of repairing it silently.

| Source form | Hangul equation command |
|---|---|
| `\\frac{a}{b}` | `{a} over {b}` |
| `\\sqrt{x}` | `sqrt {x}` |
| `x^{2}` | `x^{2}` |
| `a_{n}` | `a_{n}` |
| `\\sum_{k=1}^{n} k` | `sum_{k=1}^{n} k` |
| `\\int_{0}^{1} f(x) dx` | `int_{0}^{1} f(x) dx` |
| `\\lim_{x \\to 0}` | `Lim_{x -> 0}` |
| `\\begin{matrix}a&b\\\\c&d\\end{matrix}` | `matrix{a&b#c&d}` |

Validate balanced braces after every conversion. Unknown commands or low-confidence recognition require visual transcription to a verified native `hwp_command`. The LaTeX adapter supports only the listed subset; unsupported syntax is not permission to leave a formula as a source image or literal text. Preserve the crop as verification evidence and resolve the review before completion. Check every rendered equation's signs, fraction grouping, indices, roots, and bounds against the source.

Authoritative command references:

- https://help.hancom.com/hoffice/multi/ko_kr/hwp/insert/equation/equation%28explanation%29.htm
- https://help.hancom.com/hoffice130/ko-KR/Hwp/insert/equation/equation%28script%29.htm
