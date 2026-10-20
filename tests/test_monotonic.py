"""Tests for uxid.Monotonic."""

import copy
import doctest
import inspect
import pickle
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

import uxid
import uxid._monotonic

T = 1_700_000_000_000
LOWER = "0123456789abcdefghjkmnpqrstvwxyz"

# Monotonic cases copied from uxid-ex's conformance corpus at v2.10.0
# (conformance/monotonic.json), each with its case id, until the corpus is
# vendored and run whole. A corpus prefix of null is an absent prefix here.
MONOTONIC_CASES: list[tuple[str, dict[str, Any], list[str]]] = [
    (
        "monotonic/xl-same-millisecond",
        {
            "compact": False,
            "initial_seed": 123456789,
            "overflow_seed": None,
            "prefix": "usr",
            "size": "xl",
            "steps": [1, 1099511627776, 42],
            "times": [T, T, T, T],
        },
        [
            "usr_01hf7yat0000000000003nqk8n",
            "usr_01hf7yat0000000000003nqk8p",
            "usr_01hf7yat0000000001003nqk8p",
            "usr_01hf7yat0000000001003nqka0",
        ],
    ),
    (
        "monotonic/m-clock-moves-back",
        {
            "compact": False,
            "initial_seed": 1000,
            "overflow_seed": None,
            "prefix": "usr",
            "size": "m",
            "steps": [5, 1048576, 7],
            "times": [T, T - 1, T - 10, T],
        },
        [
            "usr_01hf7yat00000000z8",
            "usr_01hf7yat00000000zd",
            "usr_01hf7yat00000100zd",
            "usr_01hf7yat00000100zm",
        ],
    ),
    (
        "monotonic/s-overflow-bumps-time",
        {
            "compact": False,
            "initial_seed": 65000,
            "overflow_seed": 1234,
            "prefix": "usr",
            "size": "s",
            "steps": [200, 250, 100, 7, 3],
            "times": [T, T, T, T, T, T + 1],
        },
        [
            "usr_01hf7yat00zqm0",
            "usr_01hf7yat00ztr0",
            "usr_01hf7yat00zyn0",
            "usr_01hf7yat010k90",
            "usr_01hf7yat010kc1",
            "usr_01hf7yat010ke0",
        ],
    ),
    (
        "monotonic/xs-compact-overflow-clock-back",
        {
            "compact": True,
            "initial_seed": 250,
            "overflow_seed": 9,
            "prefix": "usr",
            "size": "xs",
            "steps": [5, 16],
            "times": [T, T, T - 1],
        },
        ["usr_hf7yat00z2", "usr_hf7yat00z7", "usr_hf7yat0111"],
    ),
    (
        "monotonic/l-compact-single",
        {
            "compact": True,
            "initial_seed": 0,
            "overflow_seed": None,
            "prefix": "usr",
            "size": "l",
            "steps": [],
            "times": [T],
        },
        ["usr_hf7yat000000000000000"],
    ),
    (
        "monotonic/s-compact-no-prefix-largest-step",
        {
            "compact": True,
            "initial_seed": 0,
            "overflow_seed": None,
            "prefix": None,
            "size": "s",
            "steps": [4096],
            "times": [T, T],
        },
        ["hf7yat0000000", "hf7yat0000800"],
    ),
]

CASE_IDS = [case_id for case_id, _, _ in MONOTONIC_CASES]

# The random width in bytes per size and time form, from the wire format.
WIDTHS = {
    ("xs", False): 0,
    ("s", False): 2,
    ("m", False): 5,
    ("l", False): 7,
    ("xl", False): 10,
    ("xs", True): 1,
    ("s", True): 3,
    ("m", True): 6,
    ("l", True): 8,
    ("xl", True): 10,
}


class Recorded:
    """Replays a monotonic case's draws and records the calls made for them."""

    def __init__(self, inputs: dict[str, Any]) -> None:
        self.seeds: list[int] = [inputs["initial_seed"]]
        if inputs["overflow_seed"] is not None:
            self.seeds.append(inputs["overflow_seed"])
        self.steps: list[int] = list(inputs["steps"])
        self.calls: list[tuple[str, int, int]] = []

    def seed(self, width: int) -> int:
        assert self.seeds, "a seed was drawn that the case does not name"
        value = self.seeds.pop(0)
        self.calls.append(("seed", width, value))
        return value

    def step(self, width: int) -> int:
        assert self.steps, "a step was drawn that the case does not name"
        value = self.steps.pop(0)
        self.calls.append(("step", width, value))
        return value


class Fixed:
    """Draws that always seed and step by the same values."""

    def __init__(self, seed: Any, step: Any, pause: bool = False) -> None:
        self.seed_value = seed
        self.step_value = step
        self.pause = pause

    def seed(self, width: int) -> Any:
        return self.seed_value

    def step(self, width: int) -> Any:
        if self.pause:
            # Hand the interpreter to another thread between reading the
            # state and writing it, the window a missing lock would expose.
            time.sleep(0)
        return self.step_value


def generator(inputs: dict[str, Any], **kwargs: Any) -> uxid.Monotonic:
    """A generator for a corpus case's prefix, size and time form."""
    return uxid.Monotonic(
        prefix=inputs["prefix"] or "",
        size=inputs["size"],
        compact_time=inputs["compact"],
        **kwargs,
    )


def queue_source(chunks: list[bytes]) -> Callable[[int], bytes]:
    """A byte source that hands out ``chunks`` in order, checking each count."""

    def source(count: int) -> bytes:
        assert chunks, "the byte source was called more often than the draws"
        chunk = chunks.pop(0)
        assert len(chunk) == count
        return chunk

    return source


@pytest.mark.parametrize(
    ("case_id", "inputs", "expected"), MONOTONIC_CASES, ids=CASE_IDS
)
# sabotage: reseeding on a time equal to the last (millis < last time) fails these cases
def test_the_corpus_monotonic_cases_replay_through_draws(
    case_id: str, inputs: dict[str, Any], expected: list[str]
) -> None:
    draws = Recorded(inputs)
    ids = generator(inputs, draws=draws)
    assert [ids.generate(time=t) for t in inputs["times"]] == expected, case_id
    assert draws.seeds == []
    assert draws.steps == []


@pytest.mark.parametrize(
    ("case_id", "inputs", "expected"), MONOTONIC_CASES, ids=CASE_IDS
)
# sabotage: dropping the step's mask (taking every drawn bit) fails the odd-width cases
def test_the_corpus_monotonic_cases_replay_through_the_byte_source(
    case_id: str, inputs: dict[str, Any], expected: list[str]
) -> None:
    # The draws a case names, written as the bytes the default draws read: a
    # seed as w bytes, a step as ceil(4w / 8) bytes holding the step less
    # one. Where those bytes hold more than 4w bits, the spare high bits are
    # set, which the mask must drop.
    draws = Recorded(inputs)
    first = generator(inputs, draws=draws)
    for t in inputs["times"]:
        first.generate(time=t)
    chunks: list[bytes] = []
    for kind, width, value in draws.calls:
        if kind == "seed":
            chunks.append(value.to_bytes(width, "big"))
        else:
            count = (4 * width + 7) // 8
            spare = ((1 << (8 * count)) - 1) ^ ((1 << (4 * width)) - 1)
            chunks.append(((value - 1) | spare).to_bytes(count, "big"))
    ids = generator(inputs, byte_source=queue_source(chunks))
    assert [ids.generate(time=t) for t in inputs["times"]] == expected, case_id
    assert chunks == []


# sabotage: carrying the last time, not the next millisecond, on overflow fails it
def test_an_overflow_carries_the_next_millisecond_and_a_fresh_seed() -> None:
    ids = uxid.Monotonic(prefix="usr", size="s", draws=Fixed(seed=0xFFFF - 1, step=1))

    def plain(time: int, rand: bytes) -> str:
        return uxid.generate(prefix="usr", size="s", time=time, rand=rand)

    assert ids.generate(time=T) == plain(T, b"\xff\xfe") == "usr_01hf7yat00zzz0"
    # 0xfffe + 1 is 0xffff, the largest value: it fits.
    assert ids.generate(time=T) == plain(T, b"\xff\xff")
    # 0xffff + 1 is 2**16: the field overflows into T + 1 with a fresh seed.
    assert ids.generate(time=T) == plain(T + 1, b"\xff\xfe")


@pytest.mark.parametrize(
    ("size", "body_length", "compact"),
    [
        ("xs", 10, True),
        ("xsmall", 10, True),
        ("s", 14, False),
        ("m", 18, False),
        ("l", 22, False),
        ("xl", 26, False),
    ],
)
# sabotage: defaulting compact time on at s as well as xs fails it
def test_compact_time_defaults_on_at_xs_alone(
    size: Any, body_length: int, compact: bool
) -> None:
    ids = uxid.Monotonic(size=size, byte_source=bytes)
    body = ids.generate(time=T)
    assert len(body) == body_length
    assert body.startswith("hf7yat00" if compact else "01hf7yat00")


@pytest.mark.parametrize("size", ["s", "m", "l", "xl"])
@pytest.mark.parametrize("compact", [False, True])
# sabotage: taking the standard width whatever compact_time says fails it
def test_every_size_and_time_form_steps_its_own_width(size: Any, compact: bool) -> None:
    width = WIDTHS[(size, compact)]
    widths: list[int] = []

    class Width(Fixed):
        def seed(self, width: int) -> int:
            widths.append(width)
            return 0

    ids = uxid.Monotonic(size=size, compact_time=compact, draws=Width(0, 1))
    first = ids.generate(time=T)
    second = ids.generate(time=T)
    assert widths == [width]
    assert first < second
    decoded = uxid.decode(second)
    assert isinstance(decoded, uxid.Decoded)
    assert decoded.size == size


# sabotage: dropping the random width 0 refusal fails it
def test_a_random_width_of_zero_is_refused_with_a_plain_value_error() -> None:
    for kwargs in ({"size": "xs", "compact_time": False}, {"rand_size": 0}):
        with pytest.raises(ValueError, match=r"^rand_size: ") as refused:
            uxid.Monotonic(**kwargs)
        assert not isinstance(refused.value, uxid.UXIDError)
    ids = uxid.Monotonic(size="xs", compact_time=False, rand_size=1, byte_source=bytes)
    assert ids.generate(time=T) == "01hf7yat0000"


# sabotage: raising the rand_size bound from 10 to 11 fails it
def test_a_rand_size_above_ten_is_refused_with_its_code() -> None:
    with pytest.raises(uxid.UXIDError) as refused:
        uxid.Monotonic(rand_size=11)
    assert refused.value.code == "rand_size_too_large"
    with pytest.raises(ValueError, match=r"^rand_size: ") as negative:
        uxid.Monotonic(rand_size=-1)
    assert not isinstance(negative.value, uxid.UXIDError)


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        pytest.param(
            {"prefix": "usr", "from_": "alice@example.com"},
            "from_with_monotonic",
            id="invalid/generate-from-with-monotonic",
        ),
        pytest.param(
            {"prefix": "usr", "size": "s", "rand": bytes.fromhex("0102")},
            "rand_with_monotonic",
            id="invalid/generate-rand-with-monotonic",
        ),
        pytest.param({"from_": ""}, "from_with_monotonic", id="empty-from"),
        pytest.param({"rand": b""}, "rand_with_monotonic", id="empty-rand"),
        pytest.param(
            {"from_": "x", "rand": b"\x01"}, "from_with_monotonic", id="both-from-first"
        ),
        pytest.param(
            {"from_": 1, "size": 5}, "from_with_monotonic", id="from-before-types"
        ),
        pytest.param(
            {"rand": "0102", "prefix": None},
            "rand_with_monotonic",
            id="rand-before-types",
        ),
    ],
)
# sabotage: checking rand before from_ fails it
def test_from_and_rand_are_refused_with_their_codes(
    kwargs: dict[str, Any], code: str
) -> None:
    with pytest.raises(uxid.UXIDError) as refused:
        uxid.Monotonic(**kwargs)
    assert refused.value.code == code


@pytest.mark.parametrize(
    ("kwargs", "option"),
    [
        pytest.param({"size": "huge"}, "size", id="unknown-size"),
        pytest.param({"case": "title"}, "case", id="unknown-case"),
        pytest.param({"delimiter": ""}, "delimiter", id="empty-delimiter"),
    ],
)
# sabotage: dropping the empty delimiter check fails it
def test_other_construction_values_raise_a_plain_value_error(
    kwargs: dict[str, Any], option: str
) -> None:
    with pytest.raises(ValueError, match=f"^{option}: ") as refused:
        uxid.Monotonic(**kwargs)
    assert not isinstance(refused.value, uxid.UXIDError)


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"prefix": None}, id="prefix-none"),
        pytest.param({"size": 5}, id="size-int"),
        pytest.param({"rand_size": True}, id="rand-size-bool"),
        pytest.param({"compact_time": 1}, id="compact-time-int"),
        pytest.param({"case": None}, id="case-none"),
        pytest.param({"delimiter": None}, id="delimiter-none"),
        pytest.param({"byte_source": None}, id="source-none"),
        pytest.param({"draws": object()}, id="draws-without-methods"),
        pytest.param({"draws": "seed"}, id="draws-a-str"),
    ],
)
# sabotage: taking any draws without checking its methods fails it
def test_wrong_construction_types_raise_type_error(kwargs: dict[str, Any]) -> None:
    with pytest.raises(TypeError):
        uxid.Monotonic(**kwargs)


# sabotage: dropping the bool exclusion for time fails it
def test_wrong_time_types_raise_type_error() -> None:
    ids = uxid.Monotonic(byte_source=bytes)
    bad: Any
    for bad in (True, 1.7e12, "1700000000000"):
        with pytest.raises(TypeError, match=r"^time: "):
            ids.generate(time=bad)


@pytest.mark.parametrize("bad", [-1, 1 << 48])
# sabotage: dropping the upper bound on time fails it
def test_a_time_outside_48_bits_is_refused(bad: int) -> None:
    ids = uxid.Monotonic(byte_source=bytes)
    with pytest.raises(ValueError, match=r"^time: "):
        ids.generate(time=bad)


# sabotage: overflowing millisecond 2**48 - 1 into 2**48 fails it
def test_an_overflow_in_the_last_millisecond_is_refused_and_leaves_the_state() -> None:
    last = (1 << 48) - 1
    ids = uxid.Monotonic(size="s", draws=Fixed(seed=0xFFFF, step=1))
    assert ids.generate(time=last) == "7zzzzzzzzzzzz1"
    with pytest.raises(ValueError, match=r"^time: "):
        ids.generate(time=last)
    with pytest.raises(ValueError, match=r"^time: "):
        ids.generate(time=last)


# sabotage: storing the new state before building the body fails it
def test_a_compact_marker_time_is_refused_and_leaves_the_state() -> None:
    guard = 31 * (1 << 35)
    draws = Recorded({"initial_seed": 0xFFFFFF, "overflow_seed": 0, "steps": [1, 1, 1]})
    draws.seeds += [0, 0]
    ids = uxid.Monotonic(size="s", compact_time=True, draws=draws)
    assert ids.generate(time=guard - 1) == uxid.generate(
        size="s", compact_time=True, time=guard - 1, rand=b"\xff\xff\xff"
    )
    # The step overflows into the guard's first millisecond, which the
    # compact form cannot write: refused, and again while the time stays
    # put, each time from the first id's state (a step, then a fresh seed).
    for _ in range(2):
        with pytest.raises(uxid.UXIDError) as refused:
            ids.generate(time=guard - 1)
        assert refused.value.code == "compact_time_out_of_range"
    assert [kind for kind, _, _ in draws.calls] == ["seed"] + ["step", "seed"] * 2
    with pytest.raises(uxid.UXIDError):
        uxid.Monotonic(size="s", compact_time=True, byte_source=bytes).generate(
            time=guard
        )
    # A time in the next 2**40 window is later than the state's, and fits.
    assert ids.generate(time=(1 << 40) + 5)[:8] == "00000005"


@pytest.mark.parametrize(
    ("seed", "error"),
    [
        pytest.param(1 << 16, ValueError, id="too-large"),
        pytest.param(-1, ValueError, id="negative"),
        pytest.param(True, TypeError, id="bool"),
        pytest.param("0", TypeError, id="str"),
    ],
)
# sabotage: a seed bound of 2**(8w) in place of 2**(8w) - 1 fails it
def test_a_seed_outside_its_range_is_refused(seed: Any, error: type[Exception]) -> None:
    ids = uxid.Monotonic(size="s", draws=Fixed(seed=seed, step=1))
    # Any exception is caught so that a missing check, which fails later and
    # otherwise, fails the assertions below rather than erroring.
    refused: Exception | None = None
    try:
        ids.generate(time=T)
    except Exception as caught:
        refused = caught
    assert type(refused) is error
    assert str(refused).startswith("draws: seed ")


@pytest.mark.parametrize(
    ("step", "error"),
    [
        pytest.param(0, ValueError, id="zero"),
        pytest.param((1 << 8) + 1, ValueError, id="too-large"),
        pytest.param(True, TypeError, id="bool"),
        pytest.param(1.0, TypeError, id="float"),
    ],
)
# sabotage: taking a step of 0 (a low bound of 0) fails it
def test_a_step_outside_its_range_is_refused_and_leaves_the_state(
    step: Any, error: type[Exception]
) -> None:
    draws = Fixed(seed=0, step=step)
    ids = uxid.Monotonic(size="s", draws=draws)
    assert ids.generate(time=T) == "01hf7yat000000"
    with pytest.raises(error, match=r"^draws: step "):
        ids.generate(time=T)
    draws.step_value = 1 << 8
    assert ids.generate(time=T) == uxid.generate(size="s", time=T, rand=b"\x01\x00")


# sabotage: calling the byte source for a step when draws is given fails it
def test_draws_replace_the_byte_source() -> None:
    def no_source(count: int) -> bytes:
        raise AssertionError("the byte source was called")

    ids = uxid.Monotonic(size="s", byte_source=no_source, draws=Fixed(seed=0, step=2))
    assert ids.generate(time=T) == "01hf7yat000000"
    assert ids.generate(time=T) == "01hf7yat000010"


@pytest.mark.parametrize(
    ("fill", "step"),
    [(0x00, 1), (0xFF, 1 << 8)],
)
# sabotage: drawing the step from w bytes instead of ceil(4w / 8) fails it
def test_the_default_step_is_the_masked_bits_plus_one(fill: int, step: int) -> None:
    counts: list[int] = []

    def source(count: int) -> bytes:
        counts.append(count)
        return bytes([fill]) * count if counts[1:] else bytes(count)

    ids = uxid.Monotonic(size="s", byte_source=source)
    first = ids.generate(time=T)
    second = ids.generate(time=T)
    assert counts == [2, 1]
    assert first == "01hf7yat000000"
    assert second == uxid.generate(size="s", time=T, rand=step.to_bytes(2, "big"))


# sabotage: defaulting byte_source to bytes in place of secrets.token_bytes fails it
def test_the_default_byte_source_is_secrets_token_bytes() -> None:
    parameters = inspect.signature(uxid.Monotonic).parameters
    assert parameters["byte_source"].default is secrets.token_bytes
    assert parameters["draws"].default is None
    assert parameters["compact_time"].default is None
    assert parameters["size"].default == "xl"
    assert parameters["prefix"].default == ""
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    first = uxid.Monotonic(prefix="usr").generate(time=T)
    second = uxid.Monotonic(prefix="usr").generate(time=T)
    assert first[:14] == second[:14] == "usr_01hf7yat00"
    assert first != second


# sabotage: reading the clock in seconds instead of milliseconds fails it
def test_no_time_reads_the_system_clock() -> None:
    reading = time.time_ns() // 1_000_000
    id_ = uxid.Monotonic(size="m").generate()
    decoded = uxid.decode(id_)
    assert isinstance(decoded, uxid.Decoded)
    assert decoded.time is not None
    assert abs(decoded.time - reading) < 60_000


# sabotage: writing the delimiter for an empty prefix fails it
def test_the_prefix_delimiter_and_case_apply() -> None:
    upper = uxid.Monotonic(prefix="usr", size="s", case="upper", draws=Fixed(0, 11))
    assert upper.generate(time=T) == "usr_01HF7YAT000000"
    assert upper.generate(time=T) == uxid.generate(
        prefix="usr", size="s", case="upper", time=T, rand=bytes([0, 11])
    )
    other = uxid.Monotonic(prefix="a_b", delimiter="-", size="s", byte_source=bytes)
    assert other.generate(time=T) == "a_b-01hf7yat000000"
    bare = uxid.Monotonic(size="s", byte_source=bytes)
    assert bare.generate(time=T) == "01hf7yat000000"


# sabotage: adding a module-level dict to the monotonic module fails it
def test_two_generators_keep_their_own_state() -> None:
    one = uxid.Monotonic(prefix="usr", size="s", draws=Fixed(seed=0, step=1))
    two = uxid.Monotonic(prefix="usr", size="s", draws=Fixed(seed=0, step=1))
    assert one.generate(time=T) == two.generate(time=T) == "usr_01hf7yat000000"
    assert one.generate(time=T) == "usr_01hf7yat000001"
    assert one.generate(time=T) == "usr_01hf7yat000010"
    assert two.generate(time=T) == "usr_01hf7yat000001"
    mutable = (dict, list, set, bytearray)
    for name, value in vars(uxid._monotonic).items():
        if not name.startswith("__"):
            assert not isinstance(value, mutable), name


# sabotage: generating without the lock (the with statement made an if True) fails it
def test_one_generator_shared_across_threads_increases_strictly() -> None:
    threads, per_thread = 8, 200
    ids = uxid.Monotonic(size="m", draws=Fixed(seed=0, step=1, pause=True))
    start = threading.Barrier(threads)
    made: list[list[str]] = [[] for _ in range(threads)]

    def work(index: int) -> None:
        start.wait()
        for _ in range(per_thread):
            made[index].append(ids.generate(time=T))

    workers = [threading.Thread(target=work, args=(i,)) for i in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    for own in made:
        assert own == sorted(own)
        assert len(set(own)) == per_thread
    every = sorted(i for own in made for i in own)
    # Seeded at 0 and stepped by 1, the ids are exactly the first values of
    # the field, each made once: no two threads read the same state.
    alone = uxid.Monotonic(size="m", draws=Fixed(seed=0, step=1))
    assert every == [alone.generate(time=T) for _ in range(threads * per_thread)]


# sabotage: removing the lock sentence from the class docstring fails it
def test_the_docs_say_one_generator_is_safe_to_share_across_threads() -> None:
    doc = inspect.getdoc(uxid.Monotonic) or ""
    assert "Safe to share across threads" in doc
    assert "threading.Lock" in doc
    assert "Safe to call from several threads" in (
        inspect.getdoc(uxid.Monotonic.generate) or ""
    )
    assert isinstance(uxid.Monotonic()._lock, type(threading.Lock()))


# sabotage: dropping __copy__ (a shallow copy sharing the lock) fails it
def test_a_generator_is_never_copied() -> None:
    ids = uxid.Monotonic()
    with pytest.raises(TypeError, match="never copied"):
        copy.copy(ids)
    with pytest.raises(TypeError, match="never copied"):
        copy.deepcopy(ids)
    with pytest.raises(TypeError):
        pickle.dumps(ids)


# sabotage: breaking a docstring example's id (the step added twice) fails it
def test_the_docstring_examples_hold() -> None:
    result = doctest.testmod(uxid._monotonic, raise_on_error=False)
    assert result.failed == 0
    assert result.attempted > 0
