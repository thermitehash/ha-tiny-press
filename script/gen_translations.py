"""Generate translations/en.json from strings.json (resolves [%key:...%] refs).

Run: python script/gen_translations.py
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parent.parent / "custom_components" / "tiny_press"

COMMON = {
    "common::config_flow::data::host": "Host",
    "common::config_flow::data::port": "Port",
    "common::config_flow::error::cannot_connect": "Failed to connect",
    "common::config_flow::abort::already_configured_device": "Device is already configured",
}


def build() -> dict[str, Any]:
    """Return the resolved English translations."""
    strings = json.loads((ROOT / "strings.json").read_text())

    def lookup(key: str) -> str:
        if key in COMMON:
            return COMMON[key]
        node: Any = strings
        for part in key.split("::")[2:]:
            node = node[part]
        return resolve(node)

    def resolve(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, str):
            return re.sub(r"\[%key:([^%]+)%\]", lambda m: lookup(m.group(1)), value)
        return value

    return resolve(strings)


def main() -> None:
    """Write en.json."""
    out = ROOT / "translations" / "en.json"
    out.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
