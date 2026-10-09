import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from math_to_hwp import braces_balanced, is_formula_candidate, latex_to_hwp
from math_to_hwp import contains_math_marker
import pytest


def test_basic_equations():
    assert latex_to_hwp(r"\frac{x+1}{x-2}") == "{x+1} over {x-2}"
    assert latex_to_hwp(r"\sqrt{x+1}") == "sqrt {x+1}"
    assert latex_to_hwp(r"\lim_{x \to 0}") == "Lim_{x -> 0}"


def test_matrix():
    assert latex_to_hwp(r"\begin{matrix}a&b\\c&d\end{matrix}") == "matrix{a&b#c&d}"


def test_candidate_and_braces():
    assert is_formula_candidate("f(x)=x^2+1")
    assert not is_formula_candidate("Find the minimum value of f(x)=x^2+1")
    assert not is_formula_candidate("다음 물음에 답하여라")
    assert braces_balanced("{a}/{b}")
    assert not braces_balanced("{a/{b}")


@pytest.mark.parametrize('text', ['Note', 'Example', 'Solution', 'EBS', 'A', 'I', 'O', '1', 'x축', 'x=2일 때', r'Find \\frac{x}{2}', r'값 \\frac{x}{2}', 'www.ebsi.co.kr/math_x=2', 'teacher_x@example.com'])
def test_prose_is_not_an_automatic_equation(text):
    assert not is_formula_candidate(text)


@pytest.mark.parametrize('text', ['x=2', 'a^n', 'log_a x', 'sin x', 'ln(x)', r'\frac{x}{2}', r'\begin{matrix}a&b\\c&d\end{matrix}'])
def test_mathematical_expressions_are_candidates(text):
    assert is_formula_candidate(text)


def test_addresses_do_not_trigger_mixed_math_review():
    assert not contains_math_marker('www.ebsi.co.kr/math_x=2')
    assert not contains_math_marker('teacher_x@example.com')
    assert contains_math_marker('Find x when x=2')
