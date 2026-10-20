"""Check that the vendored conformance corpus is the one its records describe.

The corpus under ``conformance/`` is uxid-ex's, copied byte for byte at the
tag ``conformance/SOURCE.json`` names. This check recomputes what the
reference's own generator writes into ``manifest.json``, by the rule the
corpus README states ("The format"):

- ``corpus_hash`` is the string ``sha256:`` followed by the lowercase hex
  SHA-256 of the case files' bytes concatenated in the order of the
  manifest's ``files``;
- each file's ``case_count`` is its number of cases, one JSON object per
  line, each line ended by a newline.

It fails when either differs from the manifest, when ``SOURCE.json`` does not
record the same hash, the reference repository, a tag and a commit, or when a
file the manifest lists is missing. A mismatch means the vendored copy is not
the one recorded; it is never repaired by rewriting a hash.

    uv run --frozen python scripts/check_corpus.py [DIRECTORY]

``DIRECTORY`` defaults to the repository's ``conformance/``. Exits 0 when the
corpus checks out and 1, listing every problem, when it does not.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

CORPUS = Path(__file__).resolve().parent.parent / "conformance"

# The corpus shape this check knows (``corpus_version`` in the manifest).
CORPUS_VERSION = 1

# The reference repository the corpus is vendored from.
REPO = "riddler/uxid-ex"

MANIFEST_KEYS = frozenset({"corpus_version", "files", "corpus_hash"})
ENTRY_KEYS = frozenset({"kind", "file", "case_count"})
SOURCE_KEYS = frozenset({"repo", "tag", "sha", "corpus_hash"})


def corpus_hash(contents: list[bytes]) -> str:
    """``sha256:`` and the lowercase hex SHA-256 of ``contents`` concatenated."""
    digest = hashlib.sha256()
    for content in contents:
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def case_count(content: bytes) -> int | None:
    """The number of newline-ended lines in ``content``.

    ``None`` when the content does not end in a newline, so that its last
    line is not a case the reference's generator could have written.
    """
    if content and not content.endswith(b"\n"):
        return None
    return content.count(b"\n")


def problems(directory: Path = CORPUS) -> list[str]:
    """Every way the corpus in ``directory`` differs from its records."""
    found: list[str] = []
    manifest = _read_object(directory / "manifest.json", MANIFEST_KEYS, found)
    source = _read_object(directory / "SOURCE.json", SOURCE_KEYS, found)
    if manifest is None:
        return found
    if manifest["corpus_version"] != CORPUS_VERSION:
        found.append(
            f"manifest.json: corpus_version {manifest['corpus_version']!r} is not"
            f" {CORPUS_VERSION}, the one this check knows"
        )
    contents: list[bytes] = []
    entries = manifest["files"]
    if not isinstance(entries, list) or not entries:
        found.append("manifest.json: files is not a non-empty list")
        entries = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
            found.append(f"manifest.json: a files entry is not {sorted(ENTRY_KEYS)}")
            continue
        name = entry["file"]
        path = directory / str(name)
        if not path.is_file():
            found.append(f"{name}: listed in manifest.json but missing")
            continue
        content = path.read_bytes()
        contents.append(content)
        counted = case_count(content)
        if counted is None:
            found.append(f"{name}: the last line has no newline")
        elif counted != entry["case_count"]:
            found.append(
                f"{name}: {counted} cases, but manifest.json's case_count is"
                f" {entry['case_count']!r}"
            )
    computed = corpus_hash(contents)
    if computed != manifest["corpus_hash"]:
        found.append(
            f"manifest.json: corpus_hash is {manifest['corpus_hash']!r}, but the"
            f" case files hash to {computed!r}"
        )
    if source is not None:
        found += _source_problems(source, computed)
    return found


def _source_problems(source: dict[str, object], computed: str) -> list[str]:
    """How ``SOURCE.json`` falls short of recording the corpus it names."""
    found: list[str] = []
    if source["repo"] != REPO:
        found.append(f"SOURCE.json: repo is {source['repo']!r}, not {REPO!r}")
    tag = source["tag"]
    if not isinstance(tag, str) or not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        found.append(f"SOURCE.json: tag {tag!r} is not a release tag vX.Y.Z")
    sha = source["sha"]
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        found.append(f"SOURCE.json: sha {sha!r} is not a 40-character lowercase hex")
    if source["corpus_hash"] != computed:
        found.append(
            f"SOURCE.json: corpus_hash is {source['corpus_hash']!r}, but the case"
            f" files hash to {computed!r}"
        )
    return found


def _read_object(
    path: Path, keys: frozenset[str], found: list[str]
) -> dict[str, object] | None:
    """The JSON object in ``path`` with exactly ``keys``, or ``None``."""
    try:
        value: object = json.loads(path.read_bytes())
    except FileNotFoundError:
        found.append(f"{path.name}: missing")
        return None
    except ValueError as error:
        found.append(f"{path.name}: not JSON: {error}")
        return None
    if not isinstance(value, dict) or set(value) != keys:
        found.append(f"{path.name}: not an object with exactly {sorted(keys)}")
        return None
    return value


def main(argv: list[str]) -> int:
    """Check the corpus in ``argv[1]``, or ``conformance/``, and report."""
    directory = Path(argv[1]) if len(argv) > 1 else CORPUS
    found = problems(directory)
    for problem in found:
        print(f"corpus: {problem}", file=sys.stderr)
    if found:
        return 1
    print(f"corpus: {directory.name} matches manifest.json and SOURCE.json")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
