"""Every case of the vendored conformance corpus, run by its kind.

The corpus under ``conformance/`` is uxid-ex's at the tag
``conformance/SOURCE.json`` names, and each case is run as the corpus
README's "Running the cases" says. The cases are read through
``manifest.json``, so every file and every line it lists is a test and
nothing is skipped. A case is read strictly: a key the runner does not know,
a missing key or a value of the wrong type fails the case, so a later corpus
cannot be half-read. ``scripts/check_corpus.py`` checks the files' hash and
case counts.
"""

import json
from collections.abc import Callable
from collections.abc import Set as AbstractSet
from typing import Any

import pytest

import uxid
from _corpus import lines, manifest

# The corpus shape this runner knows (``corpus_version`` in the manifest).
CORPUS_VERSION = 1

# The time passed to a generate call that names none: no encode or
# deterministic case reads it, and an invalid case is refused whatever it is.
NOW = 1_700_000_000_000

# The decoder clock window the corpus README bounds its compact decode cases
# by: from 1699913600000 ms inclusive to 2164577117183 ms exclusive, so the
# last clock inside it is one less.
WINDOW_START = 1_699_913_600_000
WINDOW_LAST = 2_164_577_117_182

SIZES = frozenset({"xs", "s", "m", "l", "xl"})
CASES = frozenset({"lower", "upper"})


class CaseError(Exception):
    """Why a corpus case failed."""


def strict(
    value: object, required: AbstractSet[str], optional: AbstractSet[str] = frozenset()
) -> Any:
    """``value`` as an object with every key in ``required`` and no other key
    outside ``optional``."""
    if not isinstance(value, dict):
        raise CaseError(f"not an object: {value!r}")
    missing = sorted(required - value.keys())
    if missing:
        raise CaseError(f"missing key {missing[0]!r}")
    unknown = sorted(value.keys() - required - optional)
    if unknown:
        raise CaseError(f"unknown key {unknown[0]!r}")
    return value


def typed(value: object, kind: type, key: str) -> Any:
    """``value``, checked to be a ``kind`` and not a ``bool`` standing in for
    an ``int``."""
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise CaseError(f"{key!r} is not a {kind.__name__}: {value!r}")
    return value


def nullable(value: object, kind: type, key: str) -> Any:
    """``value`` as ``typed`` checks it, or ``None``."""
    return None if value is None else typed(value, kind, key)


def one_of(value: object, allowed: frozenset[str], key: str) -> Any:
    """``value``, checked to be one of the strings ``allowed``."""
    if value not in allowed:
        raise CaseError(f"{key!r} is not one of {sorted(allowed)}: {value!r}")
    return value


def hex_bytes(value: object, key: str) -> bytes:
    """Lowercase hex to bytes."""
    text = typed(value, str, key)
    if len(text) % 2 or any(c not in "0123456789abcdef" for c in text):
        raise CaseError(f"{key!r} is not lowercase hex: {text!r}")
    return bytes.fromhex(text)


def same(what: str, actual: object, expected: object) -> None:
    """Fail the case, naming ``what``, when ``actual`` is not ``expected``."""
    if actual != expected:
        raise CaseError(f"{what}: got {actual!r}, expected {expected!r}")


def not_called(count: int) -> bytes:
    """The byte source of a request whose random field is fixed or absent."""
    raise CaseError(f"the byte source was called for {count} bytes")


def zeros(count: int) -> bytes:
    """The byte source of a refused request: one that is not refused builds an
    id, and the case fails on it."""
    return bytes(count)


def options(request: dict[str, Any]) -> dict[str, Any]:
    """The keyword arguments a corpus request spells.

    An absent option takes its default, and a prefix written ``null`` is no
    prefix, so it is left out too.
    """
    kwargs: dict[str, Any] = {}
    if request.get("prefix") is not None:
        kwargs["prefix"] = typed(request["prefix"], str, "prefix")
    elif "prefix" in request:
        nullable(request["prefix"], str, "prefix")
    if "size" in request:
        kwargs["size"] = one_of(request["size"], SIZES, "size")
    if "compact" in request:
        kwargs["compact_time"] = typed(request["compact"], bool, "compact")
    if "case" in request:
        kwargs["case"] = one_of(request["case"], CASES, "case")
    if "time" in request:
        kwargs["time"] = typed(request["time"], int, "time")
    if "rand_size" in request:
        kwargs["rand_size"] = typed(request["rand_size"], int, "rand_size")
    if "rand" in request:
        kwargs["rand"] = hex_bytes(request["rand"], "rand")
    if "from" in request:
        kwargs["from_"] = typed(request["from"], str, "from")
    return kwargs


def run_encode(case: dict[str, Any]) -> None:
    """The id built from the input, its random field fixed to ``rand``, is
    ``expected``."""
    request = strict(
        case["input"], {"prefix", "size", "compact", "case", "time", "rand"}
    )
    expected = typed(case["expected"], str, "expected")
    same("id", uxid.generate(byte_source=not_called, **options(request)), expected)


def run_deterministic(case: dict[str, Any]) -> None:
    """The deterministic id of ``from`` under the prefix, size and case is
    ``expected``."""
    request = strict(case["input"], {"prefix", "from", "size", "case"})
    expected = typed(case["expected"], str, "expected")
    id_ = uxid.generate(byte_source=not_called, time=NOW, **options(request))
    same("id", id_, expected)


def run_decode(case: dict[str, Any]) -> None:
    """The input decodes to the expected prefix, size, compact flag,
    deterministic flag and time, at both ends of the README's clock window and
    inside it; and it is valid, and deterministic as its flag says."""
    id_ = typed(case["input"], str, "input")
    expected = strict(
        case["expected"], {"prefix", "size", "compact", "deterministic", "time"}
    )
    want = uxid.Decoded(
        prefix=nullable(expected["prefix"], str, "prefix"),
        size=one_of(expected["size"], SIZES, "size"),
        compact=typed(expected["compact"], bool, "compact"),
        deterministic=typed(expected["deterministic"], bool, "deterministic"),
        time=nullable(expected["time"], int, "time"),
    )
    for now in (WINDOW_START, NOW, WINDOW_LAST):
        same(f"decoded at {now}", uxid.decode(id_, now=now), want)
    same("is_valid", uxid.is_valid(id_), True)
    same("is_deterministic", uxid.is_deterministic(id_), want.deterministic)


def run_invalid(case: dict[str, Any]) -> None:
    """The string is refused on decode, or the generate request is refused,
    with the error ``expected_error`` names."""
    expected = typed(case["expected_error"], str, "expected_error")
    request = strict(case["input"], set(), {"decode", "generate"})
    if set(request) == {"decode"}:
        id_ = typed(request["decode"], str, "decode")
        decoded = uxid.decode(id_, now=NOW)
        if not isinstance(decoded, uxid.Invalid):
            raise CaseError(f"decoded to {decoded!r}")
        same("reason", decoded.reason, expected)
        same("is_valid", uxid.is_valid(id_), False)
    elif set(request) == {"generate"}:
        same("error", refusal(request["generate"]), expected)
    else:
        raise CaseError("input holds neither decode nor generate, or both")


def refusal(value: object) -> str:
    """The code the generate request ``value`` is refused with.

    With ``monotonic`` true the request is a call to a monotonic generator
    made from its options.
    """
    request = strict(
        value,
        set(),
        {
            "prefix",
            "size",
            "compact",
            "case",
            "time",
            "rand",
            "rand_size",
            "from",
            "monotonic",
        },
    )
    monotonic = typed(request.get("monotonic", False), bool, "monotonic")
    kwargs = options(request)
    try:
        if monotonic:
            time = kwargs.pop("time", None)
            id_ = uxid.Monotonic(byte_source=zeros, **kwargs).generate(time=time)
        else:
            id_ = uxid.generate(byte_source=zeros, **kwargs)
    except uxid.UXIDError as error:
        return error.code
    raise CaseError(f"built {id_!r}")


class Replay:
    """A monotonic case's draws, handed out in the order the README gives.

    The first call draws ``initial_seed``; each later call draws the next of
    ``steps``; the call whose step overflows the field also draws
    ``overflow_seed``. Any other draw, or a draw left unread, fails the case.
    """

    def __init__(self, request: dict[str, Any]) -> None:
        self.initial_seed: int | None = typed(
            request["initial_seed"], int, "initial_seed"
        )
        steps = typed(request["steps"], list, "steps")
        self.steps: list[int] = [typed(step, int, "steps") for step in steps]
        self.overflow_seed: int | None = nullable(
            request["overflow_seed"], int, "overflow_seed"
        )
        self.call = 0
        self.drawn: list[str] = []

    def start(self, call: int) -> None:
        """Mark the start of the generate call numbered ``call``."""
        self.call = call
        self.drawn = []

    def seed(self, width: int) -> int:
        """The first call's seed, or an overflowing call's second draw."""
        if self.call == 0 and not self.drawn and self.initial_seed is not None:
            value, self.initial_seed = self.initial_seed, None
        elif self.drawn == ["step"] and self.overflow_seed is not None:
            value, self.overflow_seed = self.overflow_seed, None
        else:
            raise CaseError(f"call {self.call}: a seed the case does not name")
        self.drawn.append("seed")
        return value

    def step(self, width: int) -> int:
        """A later call's first draw, the next step."""
        if self.call == 0 or self.drawn or not self.steps:
            raise CaseError(f"call {self.call}: a step the case does not name")
        self.drawn.append("step")
        return self.steps.pop(0)

    def spent(self) -> bool:
        """Whether every draw the case names was read."""
        return (
            self.initial_seed is None and not self.steps and self.overflow_seed is None
        )


def run_monotonic(case: dict[str, Any]) -> None:
    """One generator, lower case, for the prefix, size and time form, its draws
    the case's, called once per time, emits the expected ids in order and reads
    every draw."""
    request = strict(
        case["input"],
        {
            "prefix",
            "size",
            "compact",
            "times",
            "initial_seed",
            "steps",
            "overflow_seed",
        },
    )
    expected = [
        typed(id_, str, "expected") for id_ in typed(case["expected"], list, "expected")
    ]
    times = [typed(t, int, "times") for t in typed(request["times"], list, "times")]
    draws = Replay(request)
    generator = uxid.Monotonic(
        prefix=nullable(request["prefix"], str, "prefix") or "",
        size=one_of(request["size"], SIZES, "size"),
        compact_time=typed(request["compact"], bool, "compact"),
        draws=draws,
    )
    ids = []
    for call, time in enumerate(times):
        draws.start(call)
        ids.append(generator.generate(time=time))
    same("ids", ids, expected)
    if not draws.spent():
        raise CaseError("draws left unread")


RUNNERS: dict[str, Callable[[dict[str, Any]], None]] = {
    "encode": run_encode,
    "deterministic": run_deterministic,
    "decode": run_decode,
    "invalid": run_invalid,
    "monotonic": run_monotonic,
}


def run_case(kind: str, line: str) -> None:
    """Run one case line of a file of ``kind``.

    The line holds exactly ``id``, ``input`` and the expected answer, and the
    id starts with the kind. Raises ``CaseError``, naming the case's id, when
    the case fails.
    """
    value = json.loads(line)
    answer = "expected_error" if kind == "invalid" else "expected"
    case_id = value.get("id") if isinstance(value, dict) else None
    try:
        case = strict(value, {"id", "input", answer})
        if not typed(case_id, str, "id").startswith(f"{kind}/"):
            raise CaseError(f"the id does not start with {kind}/")
        runner = RUNNERS.get(kind)
        if runner is None:
            raise CaseError(f"a case kind this runner does not know: {kind!r}")
        runner(case)
    except (CaseError, uxid.UXIDError, LookupError, ValueError, TypeError) as error:
        raise CaseError(f"{case_id}: {error}") from error


def corpus_cases() -> list[Any]:
    """One test parameter per case line of every file the manifest lists."""
    params = []
    for entry in manifest()["files"]:
        for number, line in enumerate(lines(entry["file"]), start=1):
            case_id = json.loads(line).get("id") or f"{entry['file']}:{number}"
            params.append(pytest.param(entry["kind"], line, id=case_id))
    return params


# sabotage: listing invalid before decode in RUNNERS fails it
def test_the_manifest_is_the_shape_this_runner_knows() -> None:
    value = strict(manifest(), {"corpus_version", "files", "corpus_hash"})
    assert value["corpus_version"] == CORPUS_VERSION
    seen: set[str] = set()
    for entry in value["files"]:
        strict(entry, {"kind", "file", "case_count"})
        assert entry["kind"] in RUNNERS, entry
        assert len(lines(entry["file"])) == entry["case_count"], entry
        for line in lines(entry["file"]):
            case_id = json.loads(line)["id"]
            assert case_id not in seen, f"the case id {case_id} is not unique"
            seen.add(case_id)
    assert [entry["kind"] for entry in value["files"]] == list(RUNNERS)


@pytest.mark.parametrize(("kind", "line"), corpus_cases())
# sabotage: swapping h and j in the lower-case alphabet fails the encode cases
def test_every_corpus_case_passes(kind: str, line: str) -> None:
    try:
        run_case(kind, line)
    except CaseError as failure:
        pytest.fail(str(failure), pytrace=False)


# sabotage: dropping the unknown-key loop in strict fails it
def test_a_case_with_a_key_the_runner_does_not_know_fails() -> None:
    known = (
        '{"expected":"usr_01hf7yat00","id":"encode/extra","input":{"case":"lower",'
        '"compact":false,"prefix":"usr","rand":"","size":"xs","time":1700000000000}}'
    )
    run_case("encode", known)
    in_input = known.replace('"case":"lower",', '"case":"lower","delimiter":"-",')
    with pytest.raises(CaseError, match="encode/extra: unknown key 'delimiter'"):
        run_case("encode", in_input)
    in_case = known.replace('"id":', '"note":"x","id":')
    with pytest.raises(CaseError, match="encode/extra: unknown key 'note'"):
        run_case("encode", in_case)
    in_expected = (
        '{"expected":{"compact":false,"deterministic":false,"prefix":"usr",'
        '"size":"xs","time":1700000000000,"rand":""},"id":"decode/extra",'
        '"input":"usr_01hf7yat00"}'
    )
    with pytest.raises(CaseError, match="decode/extra: unknown key 'rand'"):
        run_case("decode", in_expected)


# sabotage: dropping the missing-key loop in strict fails it
def test_a_case_missing_a_key_fails() -> None:
    line = (
        '{"expected":"usr_01hf7yat00","id":"encode/short","input":{"case":"lower",'
        '"compact":false,"prefix":"usr","size":"xs","time":1700000000000}}'
    )
    with pytest.raises(CaseError, match="encode/short: missing key 'rand'"):
        run_case("encode", line)


# sabotage: running a case of an unknown kind as an encode case fails it
def test_a_case_of_a_kind_the_runner_does_not_know_fails() -> None:
    with pytest.raises(CaseError, match="does not know"):
        run_case("future", '{"expected":"x","id":"future/one","input":{}}')


# sabotage: comparing only the first id of a monotonic case fails it
def test_a_case_whose_answer_differs_fails_with_its_id() -> None:
    line = (
        '{"expected":["hf7yat0000000","hf7yat0000801"],"id":"monotonic/wrong",'
        '"input":{"compact":true,"initial_seed":0,"overflow_seed":null,'
        '"prefix":null,"size":"s","steps":[4096],"times":[1700000000000,'
        "1700000000000]}}"
    )
    with pytest.raises(CaseError, match=r"^monotonic/wrong: ids:"):
        run_case("monotonic", line)


# sabotage: not checking that every draw was read fails it
def test_a_monotonic_case_with_a_draw_left_unread_fails() -> None:
    line = (
        '{"expected":["hf7yat0000000"],"id":"monotonic/unread",'
        '"input":{"compact":true,"initial_seed":0,"overflow_seed":null,'
        '"prefix":null,"size":"s","steps":[7],"times":[1700000000000]}}'
    )
    with pytest.raises(CaseError, match="draws left unread"):
        run_case("monotonic", line)


# sabotage: accepting a refusal of any code for an invalid case fails it
def test_an_invalid_case_refused_with_another_error_fails() -> None:
    line = (
        '{"expected_error":"rand_size_too_large","id":"invalid/other",'
        '"input":{"generate":{"prefix":"usr","rand":"010203","size":"s",'
        '"time":1700000000000}}}'
    )
    with pytest.raises(CaseError, match="error: got 'rand_width_mismatch'"):
        run_case("invalid", line)
    accepted = '{"expected_error":"empty","id":"invalid/ok","input":{"decode":"usr"}}'
    with pytest.raises(CaseError, match="reason: got 'invalid_length'"):
        run_case("invalid", accepted)
