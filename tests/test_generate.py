"""Tests for uxid.generate."""

import ast
import doctest
import hashlib
import inspect
import itertools
import pickle
import secrets
import time
import typing
from pathlib import Path
from typing import Any

import pytest

import uxid
import uxid._errors
import uxid._generate

T = 1_700_000_000_000
LOWER = "0123456789abcdefghjkmnpqrstvwxyz"

# The hash characters of a deterministic body per size, from the wire-format
# spec's table.
HASH_CHARS = {"xs": 9, "s": 13, "m": 17, "l": 21, "xl": 25}


def no_source(count: int) -> bytes:
    """A byte source a test expects never to be called."""
    raise AssertionError(f"the byte source was called for {count} bytes")


def spec_body(prefix: str, from_: str, size: str, upper: bool = False) -> str:
    """A deterministic body built from the spec's steps, one bit at a time.

    A second reading of the layout, written apart from the library's: the
    hash input, its SHA-256, then the first count x 5 bits as a bit string
    cut into 5-bit groups behind the marker.
    """
    count = HASH_CHARS[size]
    data = prefix.encode() + b"\x00" + from_.encode() + b"\x00" + bytes([count])
    bits = "".join(f"{byte:08b}" for byte in hashlib.sha256(data).digest())
    groups = [int(bits[i : i + 5], 2) for i in range(0, count * 5, 5)]
    alphabet = LOWER.upper() if upper else LOWER
    return alphabet[31] + "".join(alphabet[g] for g in groups)


def decode_standard_time(body: str) -> int:
    """Read the 48-bit standard time from a body's first 10 characters."""
    value = 0
    for char in body[:10]:
        value = value * 32 + LOWER.index(char.lower())
    return value


@pytest.mark.parametrize("size", ["xs", "s", "m", "l", "xl"])
# sabotage: taking the last count x 5 bits of the digest instead of the first fails it
def test_a_deterministic_body_is_the_marker_and_the_first_hash_bits(
    size: uxid.Size,
) -> None:
    for prefix, from_ in [("usr", "alice@example.com"), ("", "x"), ("cus", "")]:
        id_ = uxid.generate(prefix=prefix, from_=from_, size=size)
        assert id_ == (f"{prefix}_" if prefix else "") + spec_body(prefix, from_, size)
        body = id_.removeprefix(f"{prefix}_")
        assert len(body) == HASH_CHARS[size] + 1
        upper = uxid.generate(prefix=prefix, from_=from_, size=size, case="upper")
        assert upper == (f"{prefix}_" if prefix else "") + spec_body(
            prefix, from_, size, upper=True
        )


# sabotage: leaving the count byte out of the hash input fails it
def test_the_size_and_the_prefix_are_in_the_hash_input() -> None:
    bodies = [
        uxid.generate(from_="alice@example.com", size=size)[1:]
        for size in ("xs", "s", "m", "l", "xl")
    ]
    for shorter, longer in itertools.pairwise(bodies):
        assert not longer.startswith(shorter)
    usr = uxid.generate(prefix="usr", from_="alice@example.com")
    cus = uxid.generate(prefix="cus", from_="alice@example.com")
    assert usr[4:] != cus[4:]


# sabotage: hashing the upper-cased from for an upper-case id fails it
def test_case_changes_only_the_spelling_of_a_deterministic_body() -> None:
    lower = uxid.generate(prefix="Usr", from_="alice@example.com", size="s")
    upper = uxid.generate(
        prefix="Usr", from_="alice@example.com", size="s", case="upper"
    )
    assert upper.startswith("Usr_Z")
    assert lower.startswith("Usr_z")
    assert upper == "Usr_" + lower[4:].upper()


# sabotage: dropping the empty-string check (an empty from read as no from) fails it
def test_an_empty_from_is_a_deterministic_id_and_none_is_not() -> None:
    assert uxid.generate(from_="", size="s") == spec_body("", "", "s")
    assert uxid.generate(from_=None, size="xs", time=T) == "01hf7yat00"


# sabotage: folding a given time into the hash input fails it
def test_a_deterministic_id_reads_no_time_or_random_options() -> None:
    expected = uxid.generate(prefix="usr", from_="alice@example.com", size="s")
    ignored: list[dict[str, Any]] = [
        {"time": 0},
        {"time": -1},
        {"time": 1 << 48},
        {"compact_time": True, "time": 31 * (1 << 35)},
        {"rand_size": 0},
        {"rand_size": 11},
        {"rand_size": -1},
    ]
    for kwargs in ignored:
        assert (
            uxid.generate(
                prefix="usr",
                from_="alice@example.com",
                size="s",
                byte_source=no_source,
                **kwargs,
            )
            == expected
        )


# sabotage: refusing rand with from only when rand is non-empty fails it
def test_rand_with_from_is_refused_whatever_its_width() -> None:
    cases: list[tuple[uxid.Size, bytes]] = [
        ("xs", b""),
        ("s", b"\x01\x23"),
        ("xl", bytes(10)),
    ]
    for size, rand in cases:
        with pytest.raises(uxid.UXIDError) as refused:
            uxid.generate(from_="x", size=size, rand=rand)
        assert refused.value.code == "rand_with_from"


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"rand": "abc"}, id="rand-str"),
        pytest.param({"rand": bytearray(2)}, id="rand-bytearray"),
        pytest.param({"rand": b"", "size": 1}, id="size-int"),
        pytest.param({"rand": b"", "case": None}, id="case-none"),
        pytest.param({"rand": b"", "prefix": None, "time": 1.5}, id="prefix-and-time"),
    ],
)
# sabotage: checking argument types before rand_with_from fails it
def test_rand_with_from_is_checked_before_any_other_argument(
    kwargs: dict[str, Any],
) -> None:
    refused: Exception | None = None
    try:
        uxid.generate(from_="x", **kwargs)
    except Exception as error:
        refused = error
    assert isinstance(refused, uxid.UXIDError), repr(refused)
    assert refused.code == "rand_with_from"


# sabotage: writing the marker as x (value 29) fails it
def test_a_deterministic_id_sorts_after_every_time_based_id() -> None:
    deterministic = uxid.generate(prefix="usr", from_="", size="xs")
    latest = uxid.generate(prefix="usr", size="xs", time=(1 << 48) - 1)
    compact = uxid.generate(
        prefix="usr",
        size="xs",
        compact_time=True,
        time=31 * (1 << 35) - 1,
        rand=b"\xff",
    )
    assert latest < deterministic
    assert compact < deterministic


# sabotage: swapping j and k in the lower-case alphabet fails it
def test_every_symbol_is_written_in_both_cases() -> None:
    for start in (0, 16):
        values = range(start, start + 16)
        rand = sum(v << (5 * (15 - i)) for i, v in enumerate(values)).to_bytes(10)
        cases: list[tuple[uxid.Case, str]] = [
            ("lower", LOWER),
            ("upper", LOWER.upper()),
        ]
        for case, alphabet in cases:
            id_ = uxid.generate(time=0, rand=rand, case=case)
            assert id_ == "0000000000" + alphabet[start : start + 16]


# sabotage: padding the short last group (shifting it left) fails it
def test_the_short_last_group_is_its_raw_value() -> None:
    assert uxid.generate(size="s", time=0, rand=b"\xff\xff") == "0000000000zzz1"
    assert uxid.generate(size="s", time=0, rand=b"\xf8\x00") == "0000000000z000"


# sabotage: defaulting size to "l" fails it
def test_the_defaults_are_xl_standard_lower_no_prefix() -> None:
    drawn: list[int] = []

    def source(count: int) -> bytes:
        drawn.append(count)
        return b"\xab" * count

    # 0xab repeated is the 5-bit groups 21 14 21 26 23 10 29 11, twice.
    assert uxid.generate(time=T, byte_source=source) == "01hf7yat00nentqaxbnentqaxb"
    assert drawn == [10]


@pytest.mark.parametrize(
    ("short", "long"),
    [
        ("xs", "xsmall"),
        ("s", "small"),
        ("m", "medium"),
        ("l", "large"),
        ("xl", "xlarge"),
    ],
)
# sabotage: mapping "large" to "m" fails it
def test_the_long_size_spellings_are_the_short_ones(
    short: uxid.Size, long: uxid.Size
) -> None:
    def zeros(count: int) -> bytes:
        return bytes(count)

    for compact in (False, True):
        assert uxid.generate(
            size=long, compact_time=compact, time=T, byte_source=zeros
        ) == uxid.generate(size=short, compact_time=compact, time=T, byte_source=zeros)


# sabotage: ignoring rand_size (always the size's width) fails it
def test_rand_size_overrides_the_size_width() -> None:
    assert uxid.generate(prefix="cus", size="s", time=T, rand_size=0) == (
        "cus_01hf7yat00"
    )
    assert uxid.generate(prefix="cus", time=T, rand_size=1, rand=b"\xff") == (
        "cus_01hf7yat00z7"
    )
    drawn: list[int] = []

    def source(count: int) -> bytes:
        drawn.append(count)
        return bytes(count)

    uxid.generate(size="xs", compact_time=True, rand_size=4, time=T, byte_source=source)
    assert drawn == [4]


# sabotage: writing the delimiter for an empty prefix fails it
def test_the_delimiter_is_written_only_after_a_prefix() -> None:
    kwargs: dict[str, Any] = {"size": "xs", "time": T}
    assert uxid.generate(prefix="usr", delimiter="-", **kwargs) == "usr-01hf7yat00"
    assert uxid.generate(prefix="usr", delimiter="::", **kwargs) == "usr::01hf7yat00"
    assert uxid.generate(prefix="", delimiter="-", **kwargs) == "01hf7yat00"
    assert uxid.generate(delimiter="-", **kwargs) == "01hf7yat00"


# sabotage: upper-casing the whole id instead of the body fails it
def test_case_applies_to_the_body_only() -> None:
    assert uxid.generate(prefix="Usr", size="xs", time=T, case="upper") == (
        "Usr_01HF7YAT00"
    )
    assert uxid.generate(prefix="Usr", size="xs", time=T, case="lower") == (
        "Usr_01hf7yat00"
    )


# sabotage: calling the byte source when rand is given fails it
def test_the_byte_source_is_called_once_and_only_when_needed() -> None:
    drawn: list[int] = []

    def source(count: int) -> bytes:
        drawn.append(count)
        return bytes(range(count))

    assert uxid.generate(prefix="cus", size="s", time=T, byte_source=source) == (
        "cus_01hf7yat000001"
    )
    assert drawn == [2]
    uxid.generate(size="s", time=T, rand=b"\x01\x23", byte_source=no_source)
    uxid.generate(size="xs", time=T, byte_source=no_source)
    assert drawn == [2]


# sabotage: defaulting byte_source to a seeded random.Random's randbytes fails it
def test_the_default_byte_source_is_secrets_token_bytes() -> None:
    default = inspect.signature(uxid.generate).parameters["byte_source"].default
    assert default is secrets.token_bytes
    first = uxid.generate(prefix="usr", time=T)
    second = uxid.generate(prefix="usr", time=T)
    assert first[:14] == second[:14] == "usr_01hf7yat00"
    assert first != second


def random_imports(source: str) -> list[str]:
    """Every import of the ``random`` module in ``source``, however it is spelt."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        elif isinstance(node, ast.Call) and node.args:
            first = node.args[0]
            names = (
                [first.value]
                if isinstance(first, ast.Constant) and isinstance(first.value, str)
                else []
            )
            func = node.func
            callee = func.attr if isinstance(func, ast.Attribute) else ""
            callee = func.id if isinstance(func, ast.Name) else callee
            if callee not in ("__import__", "import_module"):
                names = []
        else:
            names = []
        found += [n for n in names if n == "random" or n.startswith("random.")]
    return found


@pytest.mark.parametrize(
    "spelling",
    [
        "import random",
        "import os, random",
        "import random as r",
        "import random.x",
        "from random import randbytes",
        "from random import randbytes as rb",
        "if True:\n    from random import randbytes",
        "r = __import__('random')",
        "import importlib\nr = importlib.import_module('random')",
    ],
)
# sabotage: dropping the ast.ImportFrom branch from random_imports fails it
def test_the_random_import_scan_reads_every_spelling(spelling: str) -> None:
    assert random_imports(spelling)
    assert not random_imports("import secrets\nfrom secrets import token_bytes")


# sabotage: adding "import os, random" to the generate module fails it
def test_the_library_source_never_imports_random() -> None:
    source_dir = Path(uxid._generate.__file__).parent
    paths = sorted(source_dir.glob("*.py"))
    assert paths
    for path in paths:
        assert random_imports(path.read_text()) == [], path


# sabotage: making _SIZES a plain dict fails it
def test_the_size_tables_are_immutable() -> None:
    tables: list[Any] = [
        uxid._generate._SIZES,
        uxid._generate._RAND_BYTES,
        uxid._generate._HASH_CHARS,
    ]
    for table in tables:
        with pytest.raises(TypeError):
            table["xs"] = table["xs"]
    assert dict(uxid._generate._HASH_CHARS) == HASH_CHARS


# sabotage: reading the clock in seconds instead of milliseconds fails it
def test_no_time_reads_the_system_clock() -> None:
    reading = time.time_ns() // 1_000_000
    id_ = uxid.generate(size="xs")
    # One clock reading here and one inside generate: the test asserts they
    # are close, never which came first, so a clock step cannot flake it.
    assert abs(decode_standard_time(id_) - reading) < 60_000


# sabotage: raising a plain ValueError for rand_size_too_large fails it
def test_a_refusal_is_a_value_error_with_a_code_from_the_closed_set() -> None:
    assert issubclass(uxid.UXIDError, ValueError)
    assert typing.get_args(uxid.ErrorCode) == (
        "compact_time_out_of_range",
        "rand_width_mismatch",
        "rand_size_too_large",
        "from_with_monotonic",
        "rand_with_from",
        "rand_with_monotonic",
    )
    with pytest.raises(ValueError, match="rand_size") as refused:
        uxid.generate(rand_size=11)
    assert isinstance(refused.value, uxid.UXIDError)
    assert refused.value.code == "rand_size_too_large"


# sabotage: pickling a fixed code in place of the error's own fails it
def test_a_refusal_pickles_with_its_code() -> None:
    error = uxid.UXIDError("rand_width_mismatch", "rand: must be exactly 2 bytes")
    copy = pickle.loads(pickle.dumps(error))
    assert type(copy) is uxid.UXIDError
    assert copy.code == "rand_width_mismatch"
    assert str(copy) == "rand: must be exactly 2 bytes"


@pytest.mark.parametrize(
    ("kwargs", "option"),
    [
        pytest.param({"size": "huge"}, "size", id="unknown-size"),
        pytest.param({"size": "XL"}, "size", id="size-in-upper-case"),
        pytest.param({"case": "title"}, "case", id="unknown-case"),
        pytest.param({"delimiter": ""}, "delimiter", id="empty-delimiter"),
        pytest.param({"rand_size": -1}, "rand_size", id="negative-rand-size"),
        pytest.param({"from_": "\udc80"}, "from_", id="from-lone-surrogate"),
        pytest.param(
            {"from_": "x", "prefix": "\ud800"},
            "prefix",
            id="from-prefix-lone-surrogate",
        ),
        pytest.param({"from_": "x", "size": "huge"}, "size", id="from-unknown-size"),
        pytest.param({"from_": "x", "case": "title"}, "case", id="from-unknown-case"),
        pytest.param(
            {"from_": "x", "delimiter": ""}, "delimiter", id="from-empty-delim"
        ),
        pytest.param({"time": -1}, "time", id="time-before-the-epoch"),
        pytest.param({"time": 1 << 48}, "time", id="time-above-48-bits"),
        pytest.param(
            {"time": 1 << 48, "compact_time": True}, "time", id="compact-above-48-bits"
        ),
        pytest.param(
            {"byte_source": lambda n: bytes(n + 1)}, "byte_source", id="source-too-many"
        ),
        pytest.param(
            {"byte_source": lambda n: bytes(n - 1)}, "byte_source", id="source-too-few"
        ),
    ],
)
# sabotage: dropping the upper bound on time fails it
def test_other_values_raise_a_plain_value_error(
    kwargs: dict[str, Any], option: str
) -> None:
    kwargs.setdefault("time", T)
    with pytest.raises(ValueError, match=f"^{option}: ") as refused:
        uxid.generate(**kwargs)
    assert not isinstance(refused.value, uxid.UXIDError)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"prefix": None}, id="prefix-none"),
        pytest.param({"prefix": b"usr"}, id="prefix-bytes"),
        pytest.param({"size": 5}, id="size-int"),
        pytest.param({"rand_size": True}, id="rand-size-bool"),
        pytest.param({"rand_size": 2.0}, id="rand-size-float"),
        pytest.param({"compact_time": 1}, id="compact-time-int"),
        pytest.param({"case": None}, id="case-none"),
        pytest.param({"delimiter": None}, id="delimiter-none"),
        pytest.param({"time": True}, id="time-bool"),
        pytest.param({"time": 1.7e12}, id="time-float"),
        pytest.param({"rand": "0123"}, id="rand-str"),
        pytest.param({"rand": bytearray(2), "size": "s"}, id="rand-bytearray"),
        pytest.param({"rand": memoryview(bytes(2)), "size": "s"}, id="rand-memoryview"),
        pytest.param({"byte_source": None}, id="source-none"),
        pytest.param({"byte_source": lambda n: "x" * n}, id="source-returns-str"),
        pytest.param({"byte_source": bytearray}, id="source-returns-bytearray"),
        pytest.param({"from_": b"alice@example.com"}, id="from-bytes"),
        pytest.param({"from_": 1}, id="from-int"),
        pytest.param({"from_": bytearray(b"x")}, id="from-bytearray"),
        pytest.param({"from_": "x", "time": 1.5}, id="from-time-float"),
    ],
)
# sabotage: dropping the bool exclusion for time, or taking a bytearray rand, fails it
def test_wrong_types_raise_type_error(kwargs: dict[str, Any]) -> None:
    kwargs.setdefault("time", T)
    with pytest.raises(TypeError):
        uxid.generate(**kwargs)


# sabotage: taking the whole time as the compact field (no 40-bit mask) fails it
def test_compact_time_is_the_low_40_bits() -> None:
    later = T + (1 << 40)
    assert uxid.generate(size="xs", compact_time=True, time=later, rand=b"\x01") == (
        uxid.generate(size="xs", compact_time=True, time=T, rand=b"\x01")
    )
    # The guard reads the low 40 bits too: the marker's first millisecond,
    # one window later, is refused; a standard time there is not.
    guard = 31 * (1 << 35)
    with pytest.raises(uxid.UXIDError) as refused:
        uxid.generate(size="s", compact_time=True, time=guard + (1 << 40))
    assert refused.value.code == "compact_time_out_of_range"
    assert uxid.generate(size="s", time=guard + (1 << 40), rand=b"\x00\x00") == (
        "01z00000000000"
    )


# sabotage: breaking a docstring example's id (encode_integer reversed) fails it
def test_the_docstring_examples_hold() -> None:
    for module in (uxid, uxid._errors, uxid._generate):
        result = doctest.testmod(module, raise_on_error=False)
        assert result.failed == 0, module.__name__
        assert result.attempted > 0, module.__name__


# sabotage: dropping generate from __all__ fails it
def test_the_public_surface() -> None:
    assert sorted(uxid.__all__) == [
        "ByteSource",
        "Case",
        "Decoded",
        "Draws",
        "ErrorCode",
        "Invalid",
        "InvalidReason",
        "Monotonic",
        "Size",
        "UXIDError",
        "__version__",
        "decode",
        "generate",
        "is_deterministic",
        "is_valid",
    ]
    parameters = inspect.signature(uxid.generate).parameters
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    assert parameters["from_"].default is None
