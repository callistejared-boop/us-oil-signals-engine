"""Grade must always agree with confluence.py's own tier decision: rejected
is never tradeable regardless of score, confirmed is always tradeable,
watch is never tradeable. Score bands are checked at their boundaries."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import grade as gr  # noqa: E402


def test_rejected_is_never_tradeable_regardless_of_score():
    for score in (0, 50, 99, 100):
        g = gr.grade_for(score, "rejected")
        assert g.letter == "NO TRADE"
        assert g.tradeable is False


def test_confirmed_is_always_tradeable():
    for score in (70, 80, 90, 100):
        g = gr.grade_for(score, "confirmed")
        assert g.tradeable is True


def test_watch_is_never_tradeable():
    for score in (0, 40, 65, 100):
        g = gr.grade_for(score, "watch")
        assert g.tradeable is False


def test_confirmed_bands():
    assert gr.grade_for(100, "confirmed").letter == "A+"
    assert gr.grade_for(90, "confirmed").letter == "A+"
    assert gr.grade_for(89, "confirmed").letter == "A"
    assert gr.grade_for(80, "confirmed").letter == "A"
    assert gr.grade_for(79, "confirmed").letter == "B+"
    assert gr.grade_for(70, "confirmed").letter == "B+"


def test_watch_bands():
    assert gr.grade_for(69, "watch").letter == "B"
    assert gr.grade_for(60, "watch").letter == "B"
    assert gr.grade_for(59, "watch").letter == "C+"
    assert gr.grade_for(50, "watch").letter == "C+"
    assert gr.grade_for(49, "watch").letter == "C"
    assert gr.grade_for(0, "watch").letter == "C"


def test_score_clamped_and_none_safe():
    g = gr.grade_for(150, "confirmed")
    assert g.score == 100
    g2 = gr.grade_for(-10, "watch")
    assert g2.score == 0
    g3 = gr.grade_for(None, None)  # never raises
    assert g3.tradeable is False


def test_grade_line_format():
    line = gr.grade_line(92, "confirmed")
    assert line.startswith("Grade: A+")
    assert "92/100" in line


if __name__ == "__main__":
    fns = [g for n, g in sorted(globals().items()) if n.startswith("test_")]
    for fn in fns:
        fn()
        print("  ok ", fn.__name__)
    print(f"\n{len(fns)}/{len(fns)} grade tests passed")
