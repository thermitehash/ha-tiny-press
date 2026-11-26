"""Math strip generator."""

from __future__ import annotations

import pytest

from custom_components.tiny_press.generators import math_strip as ms


@pytest.mark.parametrize("grade", ["K", "1", "2", "3", "4", "5"])
@pytest.mark.parametrize("seed", range(10))
def test_answers_are_correct(grade: str, seed: int) -> None:
    sheet = ms.generate(grade, seed)
    assert len(sheet.problems) == 10
    for problem in [*sheet.problems, sheet.bonus]:
        assert problem.check(), problem
        assert problem.answer >= 0
    keys = [(p.a, p.op, p.b) for p in sheet.problems]
    assert len(set(keys)) == len(keys)


@pytest.mark.parametrize("seed", range(20))
def test_grade_2_regroups_within_100(seed: int) -> None:
    sheet = ms.generate("2", seed)
    for p in sheet.problems:
        assert 10 <= p.a <= 99 and 10 <= p.b <= 99
        if p.op == ms.ADD:
            assert p.a % 10 + p.b % 10 >= 10
            assert p.answer <= 99
        else:
            assert p.op == ms.SUB
            assert p.a % 10 < p.b % 10
    assert not any(p.text for p in sheet.problems)


@pytest.mark.parametrize("seed", range(20))
def test_grade_3_has_facts_and_word_problems(seed: int) -> None:
    sheet = ms.generate("3", seed)
    ops = {p.op for p in sheet.problems}
    assert {ms.MUL, ms.DIV} <= ops
    words = [p for p in sheet.problems if p.text]
    assert len(words) == 2
    assert all(str(p.a) in p.text and str(p.b) in p.text for p in words)
    for p in sheet.problems:
        if p.op == ms.MUL and not p.text:
            assert 2 <= p.a <= 10 and 2 <= p.b <= 10
        if p.op == ms.DIV and not p.text:
            assert 2 <= p.b <= 10 and 2 <= p.answer <= 10


def test_k_and_1_stay_small() -> None:
    for seed in range(20):
        for p in ms.generate("K", seed).problems:
            assert max(p.a, p.b, p.answer) <= 10
        for p in ms.generate("1", seed).problems:
            assert max(p.a, p.b, p.answer) <= 20


def test_bonus_is_harder_and_order() -> None:
    sheet = ms.generate("2", 4)
    assert max(sheet.bonus.a, sheet.bonus.b) >= 15
    flags = [0 if p.vertical else (2 if p.text else 1) for p in sheet.problems]
    assert flags == sorted(flags)


def test_deterministic_and_answer_dict() -> None:
    assert ms.generate("3", 5) == ms.generate("3", 5)
    data = ms.generate("3", 5).answer()
    assert data["grade"] == "3"
    assert len(data["problems"]) == 10
    assert "answer" in data["bonus"]


def test_check_rejects_wrong() -> None:
    assert not ms.Problem(2, ms.ADD, 2, 5).check()
    assert not ms.Problem(7, ms.DIV, 0, 0).check()
    assert not ms.Problem(1, "?", 1, 1).check()
