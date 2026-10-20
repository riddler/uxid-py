"""The vendored conformance corpus, read through its manifest.

``conformance/`` holds uxid-ex's corpus at the tag ``conformance/SOURCE.json``
names. Tests that want the corpus's cases read them from here, never from a
copy, so a corpus bump reaches every test that reads it.
"""

import json
from pathlib import Path
from typing import Any

CORPUS = Path(__file__).resolve().parent.parent / "conformance"


def manifest() -> dict[str, Any]:
    """The corpus manifest, ``manifest.json``."""
    value: dict[str, Any] = json.loads((CORPUS / "manifest.json").read_bytes())
    return value


def lines(file: str) -> list[str]:
    """The case lines of the case file ``file``, one case a line.

    Lines are split on the newline alone, as the corpus README defines them;
    ``str.splitlines`` would also split on separators a case string may hold.
    """
    text = (CORPUS / file).read_text(encoding="utf-8")
    if not text:
        return []
    if not text.endswith("\n"):
        raise ValueError(f"{file}: the last line has no newline")
    return text[:-1].split("\n")


def cases(kind: str) -> list[dict[str, Any]]:
    """Every case of the case file the manifest lists for ``kind``."""
    for entry in manifest()["files"]:
        if entry["kind"] == kind:
            return [json.loads(line) for line in lines(entry["file"])]
    raise LookupError(f"the manifest lists no case file of kind {kind!r}")
