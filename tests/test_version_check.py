"""The CI version-bump check."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "check_version_bump", ROOT / "script" / "check_version_bump.py"
)
assert spec and spec.loader
check_version_bump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_version_bump)
check = check_version_bump.check

CC = ["custom_components/tiny_press/sensor.py"]


def test_docs_only_change_needs_no_bump() -> None:
    assert check(["README.md", ".github/workflows/validate.yml"], "0.1.0", ["v0.1.0"])[
        0
    ]


def test_first_release_passes() -> None:
    assert check(CC, "0.1.0", [])[0]


def test_bumped_version_passes() -> None:
    assert check(CC, "0.2.0", ["v0.1.0", "v0.1.1"])[0]
    assert check(CC, "0.1.2", ["v0.1.0", "v0.1.1"])[0]


def test_unbumped_version_fails() -> None:
    ok, message = check(CC, "0.1.1", ["v0.1.0", "v0.1.1"])
    assert not ok
    assert "v0.1.1" in message
    assert not check(CC, "0.1.0", ["v0.1.1"])[0]


def test_semver_compares_numerically() -> None:
    assert check(CC, "0.10.0", ["v0.9.0"])[0]
    assert not check(CC, "0.9.9", ["v0.10.0"])[0]


def test_ignores_odd_tags_and_bad_versions() -> None:
    assert check_version_bump.latest_tag(["latest", "v1.2", "v0.3.0"]) == (0, 3, 0)
    assert not check(CC, "1.0", [])[0]


def test_manifest_is_single_source() -> None:
    manifest = json.loads(
        (ROOT / "custom_components/tiny_press/manifest.json").read_text()
    )
    assert check_version_bump.parse_version(manifest["version"])
    release_notes = ROOT / "docs" / "releases" / f"v{manifest['version']}.md"
    assert release_notes.read_text().startswith(f"# v{manifest['version']} — ")
