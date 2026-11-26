"""Profile helpers."""

from __future__ import annotations

from custom_components.tiny_press.profiles import (
    DEFAULT_ADULT,
    DEFAULT_KID,
    Profile,
    find_any_profile,
    find_profile,
    grade_label,
    grade_number,
    profiles_of,
    slugify,
)

OPTIONS = {
    "profiles": [
        {"id": "rosie", "kind": "kid", "name": "Rosie", "grade": "2", "stretch": True},
        {"id": "max", "kind": "kid", "name": "Max", "grade": "K"},
        {"id": "sam", "kind": "adult", "name": "Sam", "difficulty": "hard"},
    ]
}


def test_grades() -> None:
    assert grade_number("K") == 0
    assert grade_number("k") == 0
    assert grade_number(4) == 4
    assert grade_number("9") == 5
    assert grade_number("junk") == 3
    assert grade_label(-1) == "K"
    assert grade_label(7) == "5"


def test_stretch() -> None:
    rosie = find_profile(OPTIONS, "kid", "rosie", None)
    assert rosie.puzzle_grade == "3"
    assert rosie.reading_grade == "2"
    top = Profile(id="x", kind="kid", name="X", grade="5", stretch=True)
    assert top.puzzle_grade == "5"


def test_find_profile() -> None:
    assert find_profile(OPTIONS, "kid", "MAX", None).id == "max"
    assert find_profile(OPTIONS, "kid", None, "max").id == "max"
    assert find_profile(OPTIONS, "kid", "nobody", None).id == "rosie"
    assert find_profile({}, "kid", None, None) == DEFAULT_KID
    assert profiles_of({}, "adult") == [DEFAULT_ADULT]
    assert find_any_profile(OPTIONS, "sam").kind == "adult"
    assert find_any_profile(OPTIONS, "zed") is None


def test_round_trip_and_defaults() -> None:
    p = Profile.from_dict({"name": "Lily Mae", "grade": "x", "kind": "weird"})
    assert p.id == "lily_mae" and p.kind == "kid" and p.grade == "3"
    assert Profile.from_dict(p.as_dict()) == p
    assert slugify("!!!") == "profile"
