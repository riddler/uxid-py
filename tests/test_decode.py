"""Tests for uxid.decode, uxid.is_valid and uxid.is_deterministic."""

import dataclasses
import doctest
import inspect
import time
import typing
from typing import Any

import pytest

import uxid
import uxid._decode
from _corpus import cases

T = 1_700_000_000_000
LOWER = "0123456789abcdefghjkmnpqrstvwxyz"

# The decoder clock window the corpus README states for its compact decode
# cases: 1699913600000 ms (2023-11-13T22:13:20.000Z) inclusive to
# 2164577117183 ms (2038-08-04T23:25:17.183Z) exclusive.
WINDOW_START = 1_699_913_600_000
WINDOW_END = 2_164_577_117_183

# The well-formed ids of the vendored corpus's decode cases.
VALID_IDS = [case["input"] for case in cases("decode")]


def fields(decoded: uxid.Decoded | uxid.Invalid) -> tuple[Any, ...]:
    """The five fields of a ``Decoded``, failing the test on an ``Invalid``."""
    assert isinstance(decoded, uxid.Decoded), decoded
    return (
        decoded.prefix,
        decoded.size,
        decoded.compact,
        decoded.deterministic,
        decoded.time,
    )


# sabotage: checking the alphabet before the length fails it
def test_refusals_come_in_the_spec_order() -> None:
    # An empty body is empty whatever else is wrong with the string.
    assert uxid.decode("u!_") == uxid.Invalid("empty")
    # A body of the wrong length with a bad character is invalid_length.
    assert uxid.decode("usr_01hf7yat0!!") == uxid.Invalid("invalid_length")
    assert uxid.decode("!") == uxid.Invalid("invalid_length")
    # A body of a table length with a bad character is invalid_character.
    assert uxid.decode("usr_01hf7yat0!") == uxid.Invalid("invalid_character")


# sabotage: reading the length 18 as compact m fails it
def test_the_lengths_10_and_18_read_as_standard_time() -> None:
    xs = uxid.generate(prefix="usr", size="xs", compact_time=True, time=T, rand=b"\x01")
    m = uxid.generate(
        prefix="usr", size="m", compact_time=True, time=T, rand=bytes(range(6))
    )
    for id_, size in ((xs, "xs"), (m, "m")):
        decoded = uxid.decode(id_, now=T)
        assert isinstance(decoded, uxid.Decoded)
        assert (decoded.size, decoded.compact) == (size, False)
        # The time is the first 10 characters read as a standard time, not T.
        body = id_.removeprefix("usr_")
        assert decoded.time == int_of(body[:10]) & ((1 << 48) - 1)
        assert decoded.time != T


def int_of(symbols: str) -> int:
    """``symbols`` read as one integer, 5 bits a symbol, lower case."""
    value = 0
    for symbol in symbols.lower():
        value = (value << 5) | LOWER.index(symbol)
    return value


# sabotage: comparing the compact time to the clock with >= one day fails the start
def test_the_clock_window_start_is_inclusive() -> None:
    compact = "usr_hf7yat0004hm5"
    assert fields(uxid.decode(compact, now=WINDOW_START))[4] == T
    # One millisecond earlier the case's time is more than a day ahead, so it
    # is read as one from the window before.
    assert fields(uxid.decode(compact, now=WINDOW_START - 1))[4] == T - (1 << 40)


# sabotage: dropping the window subtraction from the compact time fails the end
def test_the_clock_window_end_is_exclusive() -> None:
    guard = "usr_yzzzzzzz04hm5"
    last_valid = 1_065_151_889_407
    assert fields(uxid.decode(guard, now=WINDOW_END - 1))[4] == last_valid
    # At the end the result is exactly one day ahead, not more, so it stays in
    # the clock's window and is no longer the case's time.
    assert fields(uxid.decode(guard, now=WINDOW_END))[4] == last_valid + (1 << 40)


# sabotage: subtracting the window only when the result stays at or above 0 fails it
def test_a_compact_time_ahead_of_a_first_window_clock_is_negative() -> None:
    # The spec subtracts 2**40 from any result more than a day ahead of the
    # clock, with no exception for the first window after the Unix epoch.
    assert fields(uxid.decode("usr_yzzzzzzz04hm5", now=0))[4] == (
        1_065_151_889_407 - (1 << 40)
    )
    assert fields(uxid.decode("usr_yzzzzzzz04hm5", now=0))[4] == -34_359_738_369
    assert fields(uxid.decode("usr_0000000500000", now=0))[4] == 5


# sabotage: reading the system clock before the compact branch fails it
def test_the_clock_is_read_only_for_a_compact_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readings: list[int] = []

    def clock() -> int:
        readings.append(1)
        return T * 1_000_000

    monkeypatch.setattr(time, "time_ns", clock)
    uxid.decode("usr_01hf7yat0004h1")
    uxid.decode("usr_zcvt7epac0t1ebcsjfyf7cwz25")
    uxid.decode("usr_")
    uxid.decode("usr_hf7yat0004hm5", now=T)
    assert readings == []
    assert fields(uxid.decode("usr_hf7yat0004hm5"))[4] == T
    assert readings == [1]


# sabotage: reading the system clock in seconds instead of milliseconds fails it
def test_no_now_reads_the_system_clock() -> None:
    reading = time.time_ns() // 1_000_000
    id_ = uxid.generate(prefix="usr", size="s", compact_time=True)
    decoded_time = fields(uxid.decode(id_))[4]
    # One clock reading here and one each inside generate and decode: the
    # test asserts they are close, never their order, so a step cannot flake.
    assert abs(decoded_time - reading) < 60_000


def malformed_inputs() -> list[str]:
    """Truncated, overlong, wrong-alphabet and empty forms of every valid id."""
    bad = ["i", "l", "o", "u", "I", "L", "O", "U", "-", " ", "é", "\udc80", "\x00"]
    inputs = ["", "_", "__", "\udc80", "\x00" * 26]
    for id_ in VALID_IDS:
        inputs += [id_[:end] for end in range(len(id_))]
        inputs += [id_ + extra for extra in ("0", "00", "_", "é", id_)]
        for at in range(len(id_)):
            inputs += [id_[:at] + symbol + id_[at + 1 :] for symbol in bad]
    return inputs


# sabotage: reading the body's UTF-8 length without surrogatepass fails it
def test_decode_never_raises_on_a_str() -> None:
    inputs = malformed_inputs()
    assert len(inputs) > 5_000
    for id_ in inputs:
        for delimiter in ("_", "--", "é"):
            try:
                result = uxid.decode(id_, delimiter=delimiter, now=T)
            except Exception as error:  # the property under test
                pytest.fail(f"decode raised {error!r} on {id_!r}")
            assert isinstance(result, uxid.Decoded | uxid.Invalid), repr(id_)
            valid = isinstance(result, uxid.Decoded)
            assert uxid.is_valid(id_, delimiter=delimiter) is valid, repr(id_)
            deterministic = valid and typing.cast(uxid.Decoded, result).deterministic
            assert uxid.is_deterministic(id_, delimiter=delimiter) is deterministic


# sabotage: splitting at the first delimiter instead of the last fails it
def test_the_body_is_after_the_last_delimiter() -> None:
    assert fields(uxid.decode("a_b_c_01hf7yat00"))[0] == "a_b_c"
    assert fields(uxid.decode("a--b--01hf7yat00", delimiter="--"))[0] == "a--b"
    assert fields(uxid.decode("01hf7yat00", delimiter="--"))[0] is None
    assert uxid.decode("cus_01hf7yat00", delimiter="--") == uxid.Invalid(
        "invalid_character"
    )
    # An id that starts with the delimiter has the empty prefix.
    assert fields(uxid.decode("_01hf7yat00"))[0] == ""


# sabotage: splitting with rsplit (overlapping matches from the right) fails it
def test_delimiter_matches_do_not_overlap() -> None:
    # Under "--", "usr---01hf7yat0" splits after "usr": the body is
    # "-01hf7yat0", 10 bytes with a hyphen, not the 9-byte "01hf7yat0".
    assert uxid.decode("usr---01hf7yat0", delimiter="--") == uxid.Invalid(
        "invalid_character"
    )


# sabotage: letting i read as a symbol fails it
def test_every_symbol_reads_its_value_in_both_cases_and_nothing_else_does() -> None:
    for code in range(0x110000):
        symbol = chr(code)
        index = LOWER.find(symbol.lower()) if symbol.isascii() else -1
        expected = index if index >= 0 else None
        assert uxid._decode._VALUES.get(symbol) == expected, hex(code)


# sabotage: reading the marker as z only (not Z) fails it
def test_a_deterministic_body_has_no_time_in_either_case() -> None:
    for id_ in ("usr_zcvt7epac0t1ebcsjfyf7cwz25", "usr_ZCVT7EPAC0T1EBCSJFYF7CWZ25"):
        decoded = uxid.decode(id_)
        assert fields(decoded)[3:] == (True, None)
    # A compact-length body that starts with the marker is deterministic too.
    assert fields(uxid.decode("usr_zzzzzzzz04hm5"))[1:] == ("s", True, True, None)


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        pytest.param({"id_": b"usr_01hf7yat00"}, TypeError, id="id-bytes"),
        pytest.param({"id_": None}, TypeError, id="id-none"),
        pytest.param({"delimiter": None}, TypeError, id="delimiter-none"),
        pytest.param({"delimiter": b"_"}, TypeError, id="delimiter-bytes"),
        pytest.param({"delimiter": ""}, ValueError, id="delimiter-empty"),
        pytest.param({"now": True}, TypeError, id="now-bool"),
        pytest.param({"now": 1.7e12}, TypeError, id="now-float"),
        pytest.param({"now": "1700000000000"}, TypeError, id="now-str"),
        pytest.param({"now": -1}, ValueError, id="now-negative"),
    ],
)
# sabotage: accepting a bool for now fails it
def test_a_mistake_in_the_call_raises(kwargs: dict[str, Any], error: type) -> None:
    id_ = kwargs.pop("id_", "usr_01hf7yat00")
    with pytest.raises(error):
        uxid.decode(id_, **kwargs)


# sabotage: ignoring the prefix argument of is_valid fails it
def test_is_valid_requires_the_prefix_when_given() -> None:
    assert uxid.is_valid("cus_01hf7yat0004h1")
    assert uxid.is_valid("cus_01hf7yat0004h1", prefix="cus")
    assert uxid.is_valid("cus_01hf7yat0004h1", prefix="")
    assert not uxid.is_valid("cus_01hf7yat0004h1", prefix="usr")
    assert not uxid.is_valid("cus_01hf7yat0004h1", prefix="cu")
    assert not uxid.is_valid("01hf7yat0004h1", prefix="cus")
    assert uxid.is_valid("01hf7yat0004h1")
    assert uxid.is_valid("a_b_01hf7yat0004h1", prefix="a_b")
    assert uxid.is_valid("cus--01hf7yat0004h1", delimiter="--", prefix="cus")
    assert not uxid.is_valid("cus_01hf7yat0004h1", delimiter="--", prefix="cus")


# sabotage: is_deterministic checking only the first body character fails it
def test_is_deterministic_needs_a_well_formed_marker_body() -> None:
    assert uxid.is_deterministic("usr_zcvt7epac0t1ebcsjfyf7cwz25")
    assert uxid.is_deterministic("USR_ZCVT7EPAC0T1EBCSJFYF7CWZ25")
    assert uxid.is_deterministic("zqz4cwzgyw8ks97869")
    assert uxid.is_deterministic("usr--zt9vnyfd85bff0", delimiter="--")
    assert not uxid.is_deterministic("usr_zcvt7epac")
    assert not uxid.is_deterministic("usr_zcvt7epac0t1ebcsjfyf7cwzi5")
    assert not uxid.is_deterministic("usr_01hf7yat0004h1")
    assert not uxid.is_deterministic("usr_zt9vnyfd85bff0", delimiter="--")


# sabotage: answering True from is_valid for a value that is not a str fails it
def test_the_checks_answer_false_for_a_value_that_is_not_a_str() -> None:
    for value in (None, b"usr_01hf7yat00", 1, ["usr_01hf7yat00"]):
        assert uxid.is_valid(value) is False
        assert uxid.is_deterministic(value) is False


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        pytest.param({"delimiter": ""}, ValueError, id="delimiter-empty"),
        pytest.param({"delimiter": None}, TypeError, id="delimiter-none"),
    ],
)
# sabotage: dropping the delimiter check from is_deterministic fails it
def test_the_checks_refuse_a_bad_delimiter(kwargs: dict[str, Any], error: type) -> None:
    with pytest.raises(error, match=r"^delimiter: "):
        uxid.is_valid("usr_01hf7yat00", **kwargs)
    with pytest.raises(error, match=r"^delimiter: "):
        uxid.is_deterministic("usr_01hf7yat00", **kwargs)


# sabotage: accepting a bytes prefix in is_valid fails it
def test_is_valid_refuses_a_prefix_that_is_not_a_str() -> None:
    with pytest.raises(TypeError, match=r"^prefix: "):
        uxid.is_valid("usr_01hf7yat00", prefix=typing.cast(Any, b"usr"))


# sabotage: making Decoded a non-frozen dataclass fails it
def test_the_results_are_frozen_values() -> None:
    first = uxid.decode("cus_01hf7yat0004h1")
    refused = uxid.decode("usr_")
    for value, name in ((first, "time"), (refused, "reason")):
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, name, 0)
    assert first == uxid.decode("cus_01hf7yat0004h1")
    assert hash(first) == hash(uxid.decode("cus_01hf7yat0004h1"))
    assert first != uxid.decode("usr_01hf7yat0004h1")
    assert refused == uxid.Invalid("empty")
    assert refused != uxid.Invalid("invalid_length")
    assert [f.name for f in dataclasses.fields(uxid.Decoded)] == [
        "prefix",
        "size",
        "compact",
        "deterministic",
        "time",
    ]
    assert typing.get_args(uxid.InvalidReason) == (
        "empty",
        "invalid_length",
        "invalid_character",
    )


# sabotage: making _LENGTHS a plain dict fails it
def test_the_decode_tables_are_immutable() -> None:
    for table, key in ((uxid._decode._LENGTHS, 10), (uxid._decode._VALUES, "0")):
        with pytest.raises(TypeError):
            typing.cast(Any, table)[key] = 0
    assert sorted(uxid._decode._LENGTHS) == [10, 13, 14, 18, 21, 22, 24, 26]


# sabotage: reading the 13 length as standard time fails it
def test_the_decode_docstring_examples_hold() -> None:
    result = doctest.testmod(uxid._decode, raise_on_error=False)
    assert result.failed == 0
    assert result.attempted > 0


# sabotage: making delimiter positional in decode fails it
def test_the_options_are_keyword_only_and_default_to_the_spec() -> None:
    for function in (uxid.decode, uxid.is_valid, uxid.is_deterministic):
        parameters = list(inspect.signature(function).parameters.values())
        assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters[1:])
        assert inspect.signature(function).parameters["delimiter"].default == "_"
    assert inspect.signature(uxid.decode).parameters["now"].default is None
    assert inspect.signature(uxid.is_valid).parameters["prefix"].default is None
