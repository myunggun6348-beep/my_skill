from __future__ import annotations

import re


MATH_MARKERS = re.compile(r"[=<>≤≥±×÷∑∫√∞^_]|\\(?:frac|sqrt|sum|int|lim|begin)")
MATH_FUNCTIONS = {"sin", "cos", "tan", "log", "ln", "lim", "max", "min", "sqrt"}


def is_web_or_email(text: str) -> bool:
    return bool(re.search(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text, re.I))


def is_formula_candidate(text: str) -> bool:
    compact = text.strip()
    if not compact or len(compact) > 300:
        return False
    if is_web_or_email(compact) or re.search(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7a3]", compact):
        return False
    words = re.sub(r"\\[A-Za-z]+", "", compact)
    natural_language_words = [word for word in re.findall(r"[A-Za-z]{3,}", words) if word.lower() not in MATH_FUNCTIONS | {"matrix"}]
    if natural_language_words:
        return False
    if re.search(r"\\(?:frac|sqrt|sum|int|lim|begin)", compact):
        return True
    marker_count = len(MATH_MARKERS.findall(compact))
    latin_or_digit = sum(ch.isdigit() or ("A" <= ch <= "Z") or ("a" <= ch <= "z") for ch in compact)
    function_with_argument = bool(re.search(r"\b(?:sin|cos|tan|log|ln)\s*[({ ]\s*[A-Za-z0-9]", compact))
    return (marker_count > 0 or function_with_argument) and latin_or_digit > 0


def contains_math_marker(text: str) -> bool:
    return not is_web_or_email(text) and bool(MATH_MARKERS.search(text))


def braces_balanced(text: str) -> bool:
    depth = 0
    for char in text:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _replace_frac(text: str) -> str:
    pattern = re.compile(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
    previous = None
    while previous != text:
        previous = text
        text = pattern.sub(r"{\1} over {\2}", text)
    return text


def latex_to_hwp(source: str) -> str:
    if not braces_balanced(source):
        raise ValueError("Unbalanced braces in source equation")
    text = source.strip().replace("\\left", "").replace("\\right", "")
    text = _replace_frac(text)
    text = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"sqrt {\1}", text)
    text = text.replace("\\sum", "sum").replace("\\int", "int")
    text = text.replace("\\lim", "Lim").replace("\\to", "->")
    text = text.replace("\\times", "times").replace("\\cdot", "cdot")
    text = text.replace("\\infty", "inf").replace("\\pm", "+-")
    text = text.replace("\\leq", "<=").replace("\\geq", ">=")
    matrix = re.fullmatch(r"\\begin\{matrix\}(.+)\\end\{matrix\}", text, flags=re.DOTALL)
    if matrix:
        body = matrix.group(1).replace("\\\\", "#")
        text = f"matrix{{{body}}}"
    unknown = re.findall(r"\\[A-Za-z]+", text)
    if unknown:
        raise ValueError(f"Unsupported LaTeX commands: {', '.join(sorted(set(unknown)))}")
    if not braces_balanced(text):
        raise ValueError("Unbalanced braces after conversion")
    return re.sub(r"\s+", " ", text).strip()
