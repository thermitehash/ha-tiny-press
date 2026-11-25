"""Fail when custom_components/ changed but manifest.json's version wasn't bumped.

The version must be greater than the latest ``v*`` tag. Run in CI on pull
requests:

    python script/check_version_bump.py origin/main
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "custom_components" / "tiny_press" / "manifest.json"
WATCHED = "custom_components/"
_SEMVER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(value: str) -> tuple[int, int, int] | None:
    """Parse ``1.2.3`` or ``v1.2.3``; None for anything else."""
    match = _SEMVER.match(value.strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def latest_tag(tags: list[str]) -> tuple[int, int, int] | None:
    """Highest SemVer tag, ignoring non-version tags."""
    versions = [v for t in tags if (v := parse_version(t))]
    return max(versions) if versions else None


def check(changed: list[str], version: str, tags: list[str]) -> tuple[bool, str]:
    """Return (ok, message)."""
    touched = [f for f in changed if f.startswith(WATCHED)]
    if not touched:
        return True, "No integration files changed; no version bump needed."
    current = parse_version(version)
    if current is None:
        return False, f"manifest.json version {version!r} is not SemVer."
    released = latest_tag(tags)
    if released is None:
        return True, f"No release tags yet; {version} will be the first."
    if current > released:
        return True, f"Version {version} is newer than v{'.'.join(map(str, released))}."
    return False, (
        f"{len(touched)} file(s) under {WATCHED} changed, but manifest.json "
        f"version {version} is not greater than the latest tag "
        f"v{'.'.join(map(str, released))}. Bump it (minor for features, patch for fixes)."
    )


def _git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout
    return [line for line in out.splitlines() if line]


def main() -> int:
    """Compare HEAD with the base ref given on the command line."""
    base = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    changed = _git("diff", "--name-only", f"{base}...HEAD")
    version = json.loads(MANIFEST.read_text())["version"]
    ok, message = check(changed, version, _git("tag", "--list", "v*"))
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
