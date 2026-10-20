"""Tests for scripts/check_corpus.py, the corpus hash and case-count check."""

import hashlib
import importlib.util
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from _corpus import CORPUS

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_corpus.py"


def load() -> ModuleType:
    """The check script, loaded as a module."""
    spec = importlib.util.spec_from_file_location("check_corpus", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load()
problems: Callable[[Path], list[str]] = check.problems
main: Callable[[list[str]], int] = check.main


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A copy of the vendored corpus a test may change."""
    copy = tmp_path / "conformance"
    shutil.copytree(CORPUS, copy)
    return copy


def rewrite(path: Path, change: Callable[[dict[str, object]], None]) -> None:
    """Apply ``change`` to the JSON object in ``path``."""
    value = json.loads(path.read_bytes())
    change(value)
    path.write_text(json.dumps(value) + "\n")


# sabotage: hashing the manifest's files in reverse order fails it
def test_the_vendored_corpus_checks_out(capsys: pytest.CaptureFixture[str]) -> None:
    assert problems(CORPUS) == []
    assert main(["check_corpus.py"]) == 0
    assert "matches manifest.json and SOURCE.json" in capsys.readouterr().out


# sabotage: returning the first file's hash alone from corpus_hash fails it
def test_the_hash_is_the_case_files_concatenated_in_manifest_order() -> None:
    manifest = json.loads((CORPUS / "manifest.json").read_bytes())
    data = b"".join(
        (CORPUS / entry["file"]).read_bytes() for entry in manifest["files"]
    )
    expected = "sha256:" + hashlib.sha256(data).hexdigest()
    assert manifest["corpus_hash"] == expected
    contents = [(CORPUS / entry["file"]).read_bytes() for entry in manifest["files"]]
    assert check.corpus_hash(contents) == expected


# sabotage: comparing the computed hash to SOURCE.json's alone fails it
def test_one_changed_byte_in_a_case_file_fails(
    corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = corpus / "encode.json"
    content = bytearray(path.read_bytes())
    content[content.index(b"usr_01hf7yat00")] ^= 0x01
    path.write_bytes(bytes(content))
    found = problems(corpus)
    assert any(p.startswith("manifest.json: corpus_hash is") for p in found), found
    assert any(p.startswith("SOURCE.json: corpus_hash is") for p in found), found
    assert main(["check_corpus.py", str(corpus)]) == 1
    assert "corpus: manifest.json: corpus_hash is" in capsys.readouterr().err


# sabotage: dropping the case_count comparison fails it
def test_a_case_count_that_differs_from_the_lines_fails(corpus: Path) -> None:
    def bump(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, list)
        files[1]["case_count"] += 1

    rewrite(corpus / "manifest.json", bump)
    assert problems(corpus) == [
        "deterministic.json: 12 cases, but manifest.json's case_count is 13"
    ]


# sabotage: counting a last line with no newline as a case fails it
def test_a_case_file_whose_last_line_has_no_newline_fails(corpus: Path) -> None:
    path = corpus / "monotonic.json"
    path.write_bytes(path.read_bytes().removesuffix(b"\n"))
    found = problems(corpus)
    assert "monotonic.json: the last line has no newline" in found


# sabotage: skipping a files entry whose file is missing without a problem fails it
def test_a_case_file_the_manifest_lists_but_is_missing_fails(corpus: Path) -> None:
    (corpus / "decode.json").unlink()
    assert "decode.json: listed in manifest.json but missing" in problems(corpus)


# sabotage: not checking SOURCE.json's repo fails it
def test_a_source_json_naming_another_repo_tag_or_sha_fails(corpus: Path) -> None:
    def other(source: dict[str, object]) -> None:
        source.update(repo="riddler/uxid-rs", tag="main", sha="57235777")

    rewrite(corpus / "SOURCE.json", other)
    found = problems(corpus)
    assert found == [
        "SOURCE.json: repo is 'riddler/uxid-rs', not 'riddler/uxid-ex'",
        "SOURCE.json: tag 'main' is not a release tag vX.Y.Z",
        "SOURCE.json: sha '57235777' is not a 40-character lowercase hex",
    ]


# sabotage: checking SOURCE.json's keys as a subset rather than exactly fails it
def test_a_source_json_with_another_key_set_fails(corpus: Path) -> None:
    rewrite(corpus / "SOURCE.json", lambda source: source.update(note="x"))
    assert problems(corpus) == [
        "SOURCE.json: not an object with exactly ['corpus_hash', 'repo', 'sha', 'tag']"
    ]


# sabotage: not checking corpus_version fails it
def test_a_corpus_version_this_check_does_not_know_fails(corpus: Path) -> None:
    rewrite(corpus / "manifest.json", lambda m: m.update(corpus_version=2))
    assert problems(corpus) == [
        "manifest.json: corpus_version 2 is not 1, the one this check knows"
    ]


# sabotage: reading SOURCE.json before manifest.json fails it
def test_a_missing_or_malformed_record_fails(corpus: Path) -> None:
    (corpus / "SOURCE.json").unlink()
    assert problems(corpus) == ["SOURCE.json: missing"]
    (corpus / "manifest.json").write_text("{")
    found = problems(corpus)
    assert found[0].startswith("manifest.json: not JSON:"), found
    assert found[1:] == ["SOURCE.json: missing"]


# sabotage: accepting a files entry with an extra key fails it
def test_a_malformed_files_list_fails(corpus: Path) -> None:
    def extra(manifest: dict[str, object]) -> None:
        files = manifest["files"]
        assert isinstance(files, list)
        files[0]["note"] = "x"

    rewrite(corpus / "manifest.json", extra)
    found = problems(corpus)
    assert "manifest.json: a files entry is not ['case_count', 'file', 'kind']" in found
    rewrite(corpus / "manifest.json", lambda m: m.update(files=[]))
    assert "manifest.json: files is not a non-empty list" in problems(corpus)
