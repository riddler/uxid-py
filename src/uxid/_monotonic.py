"""Monotonic generation: ids that increase strictly from one generator."""

import secrets
import threading
from typing import Protocol

from uxid._base32 import encode_bytes, encode_integer
from uxid._errors import UXIDError
from uxid._generate import (
    _COMPACT_MASK,
    _MARKER,
    _MAX_TIME,
    ByteSource,
    Case,
    Size,
    _alphabet,
    _canonical_size,
    _draw,
    _is_int,
    _now_millis,
    _width,
)


class Draws(Protocol):
    """Where a monotonic generator's random values come from, in place of bytes.

    Any object with these two methods will do. It exists to replay recorded
    draws, such as the conformance corpus's, never as a source of randomness:
    ids built from known draws are exactly as guessable as those draws.
    """

    def seed(self, width: int) -> int:
        """A fresh random value for a ``width``-byte field.

        An int from 0 to 2**(8 x ``width``) - 1, the field read as one
        big-endian unsigned integer.
        """
        ...

    def step(self, width: int) -> int:
        """A step for a ``width``-byte field, drawn uniformly.

        An int from 1 to 2**(4 x ``width``), half the field's bit width.
        """
        ...


class Monotonic:
    """A monotonic generator: the ids it makes increase strictly.

    They increase in string order as in time order, also when several fall in
    one millisecond and when the clock moves back. It follows the "Monotonic
    generation" rule of uxid-ex's wire-format spec. A monotonic id is an
    ordinary time-based id of its size: nothing in it says how it was made,
    and ``uxid.decode`` reads it as any other.

    A generator is made for one prefix and one random width, so its state is
    kept per prefix and random width: the last time ``T`` it gave and the last
    random value ``R``, the random field read as one big-endian unsigned
    integer of ``w`` bytes. For a call at time ``now``:

    1. with no last id, or ``now`` later than ``T``, the id carries ``now``
       and a fresh random value, the seed;
    2. with ``now`` equal to or earlier than ``T``, the id carries ``T`` and
       ``R + step``, the step drawn uniformly from 1 to 2**(4w) inclusive,
       half the field's bit width;
    3. when ``R + step`` is 2**(8w) or more, the id carries ``T + 1`` and a
       fresh seed instead.

    The step is not a plus-one counter: consecutive ids in a millisecond are
    spread over a window of 2**(4w) values. That stops trivial enumeration
    but is a mitigation, not unpredictability, and a small random field stays
    small: a standard ``s`` id has 16 random bits, a standard ``m`` id 40. A
    compact time holds only the low 40 bits of the time, so compact ids keep
    their order only within one 2**40 millisecond window, as every compact id
    does.

    **Safe to share across threads.** The state lives in the instance alone,
    guarded by a ``threading.Lock`` inside it, so one generator may be called
    from several threads at once and its ids still increase strictly, in the
    order the calls take the lock; the byte source or ``draws`` is called
    with the lock held. Nothing is kept at module or class level, and two
    generators never affect each other: ids from two generators (one per
    thread, say) carry no order between them within a millisecond. A
    generator is never copied, so its state is never duplicated by accident.

    >>> import uxid
    >>> ids = uxid.Monotonic(prefix="usr", size="s")
    >>> first = ids.generate(time=1_700_000_000_000)
    >>> second = ids.generate(time=1_700_000_000_000)
    >>> third = ids.generate(time=1_699_999_999_995)
    >>> first < second < third
    True
    """

    def __init__(
        self,
        *,
        prefix: str = "",
        size: Size = "xl",
        rand_size: int | None = None,
        compact_time: bool | None = None,
        case: Case = "lower",
        delimiter: str = "_",
        byte_source: ByteSource = secrets.token_bytes,
        draws: Draws | None = None,
        from_: str | None = None,
        rand: bytes | None = None,
    ) -> None:
        """Make a generator for one prefix and one random width.

        Every argument is a keyword argument. ``prefix``, ``size``,
        ``rand_size``, ``case``, ``delimiter`` and ``byte_source`` mean what
        they mean to ``uxid.generate``, with its defaults. The others:

        - ``compact_time``: ``True`` for compact time, ``False`` for standard
          time. ``None``, the default, is compact time at size ``xs`` and
          standard time at every other size, because a standard ``xs`` has
          no random field to step and a compact ``xs`` has a one-byte field.
          The random width (the size's, or ``rand_size``) must be at least
          one byte, so an ``xs`` with ``compact_time=False`` and no
          ``rand_size`` is refused, and so is ``rand_size=0``.
        - ``byte_source``: where the seeds and the steps come from when
          ``draws`` is ``None``. A seed is ``w`` bytes read big-endian; a
          step is the low 4w bits of ceil(4w / 8) bytes, read big-endian,
          plus one. The range holds a power of two values, so the masked
          bits are exactly uniform over it, with no modulo bias and nothing
          redrawn. Defaults to ``secrets.token_bytes``; a source for real
          ids must be cryptographically secure.
        - ``draws``: an object with the ``seed`` and ``step`` methods
          ``uxid.Draws`` names, the random values themselves in place of the
          byte source, which is then never called. It exists to replay
          recorded draws, such as the conformance corpus's, never as a
          source of randomness. ``None``, the default, draws from the byte
          source.
        - ``from_`` and ``rand``: always refused unless ``None``. A
          monotonic generator makes neither a deterministic id nor one with
          a fixed random field; they are taken so that the refusal has its
          name.

        Raises ``uxid.UXIDError`` with ``from_with_monotonic`` for a
        ``from_`` and ``rand_with_monotonic`` for a ``rand`` that is not
        ``None``, checked in that order before every other argument, the
        type of each included; and with ``rand_size_too_large`` for a
        ``rand_size`` above 10. Raises a plain ``ValueError`` for a random
        width of 0, and for the other values ``uxid.generate`` refuses here:
        an unknown size or case, an empty delimiter, a negative
        ``rand_size``. Raises ``TypeError`` for an argument of the wrong
        type, and for a ``draws`` without callable ``seed`` and ``step``
        methods.

        >>> import uxid
        >>> len(uxid.Monotonic(prefix="usr", size="xs").generate())
        14
        >>> try:
        ...     uxid.Monotonic(prefix="usr", from_="alice@example.com")
        ... except uxid.UXIDError as error:
        ...     print(error.code)
        from_with_monotonic
        """
        if from_ is not None:
            raise UXIDError(
                "from_with_monotonic",
                "from_: cannot be given to a monotonic generator: a deterministic"
                " id has no random field to step",
            )
        if rand is not None:
            raise UXIDError(
                "rand_with_monotonic",
                "rand: cannot be given to a monotonic generator: the generator"
                " chooses the random field",
            )
        _check_types(prefix, rand_size, compact_time, delimiter, byte_source, draws)
        canonical = _canonical_size(size)
        alphabet = _alphabet(case)
        if not delimiter:
            raise ValueError("delimiter: must be a non-empty string")
        compact = canonical == "xs" if compact_time is None else compact_time
        width = _width(canonical, compact, rand_size)
        if width == 0:
            raise ValueError(
                "rand_size: a monotonic id needs a random field to step, but this"
                " generator's random width is 0 bytes; leave compact_time unset"
                " at size xs, or give a rand_size from 1 to 10"
            )
        self._head = f"{prefix}{delimiter}" if prefix else ""
        self._alphabet = alphabet
        self._compact = compact
        self._width = width
        self._byte_source = byte_source
        self._draws = draws
        self._lock = threading.Lock()
        self._last: tuple[int, int] | None = None

    def generate(self, *, time: int | None = None) -> str:
        """Generate the next id, under the rule the class describes.

        - ``time``: the current time, milliseconds since the Unix epoch, from
          0 to 2**48 - 1. ``None``, the default, reads the system clock. The
          id carries this time, the last id's time, or the millisecond after
          it, as the rule says; giving it is how a test fixes the clock.

        Safe to call from several threads at once on one generator. A call
        that raises leaves the generator as it was.

        Raises ``uxid.UXIDError`` with ``compact_time_out_of_range`` for a
        compact time the id would carry whose first character would be the
        deterministic marker. When that time is the millisecond after the
        last id's, reached by an overflow, the refused call leaves the
        generator as it was: a later call at or before the last id's time
        draws a new step, and is refused again only while the last value
        plus that step still overflows the field; a smaller step answers an
        id at the last id's time. Raises a plain ``ValueError`` for a
        time outside 0 to 2**48 - 1, a step that overflows the field in
        millisecond 2**48 - 1 (the last a time field holds), a byte source
        that returns the wrong number of bytes and a draw outside its range.
        Raises ``TypeError`` for a ``time`` that is not an int (``bool``
        included) and for a byte source or a draw of the wrong type.

        >>> import uxid
        >>> def zeros(count: int) -> bytes:
        ...     return bytes(count)
        >>> ids = uxid.Monotonic(prefix="usr", size="s", byte_source=zeros)
        >>> ids.generate(time=1_700_000_000_000)
        'usr_01hf7yat000000'
        >>> ids.generate(time=1_700_000_000_000)
        'usr_01hf7yat000001'
        """
        if time is not None and not _is_int(time):
            raise TypeError(
                f"time: must be an int of milliseconds or None, got {time!r}"
            )
        with self._lock:
            millis = _now_millis() if time is None else time
            if not 0 <= millis <= _MAX_TIME:
                raise ValueError(
                    f"time: must be from 0 to 2**48 - 1 milliseconds, got {millis}"
                )
            last = self._last
            if last is not None and millis <= last[0]:
                value = last[1] + self._step()
                if value < 1 << (8 * self._width):
                    nxt = (last[0], value)
                elif last[0] == _MAX_TIME:
                    raise ValueError(
                        "time: the random field overflowed in millisecond"
                        " 2**48 - 1, the last a time field holds"
                    )
                else:
                    nxt = (last[0] + 1, self._seed())
            else:
                nxt = (millis, self._seed())
            id_ = self._head + self._body(*nxt)
            self._last = nxt
        return id_

    def __copy__(self) -> "Monotonic":
        """Refuse a copy: two copies of one state would repeat its ids."""
        raise TypeError("a uxid.Monotonic is never copied: its copies would repeat ids")

    def __deepcopy__(self, memo: dict[int, object]) -> "Monotonic":
        """Refuse a copy: two copies of one state would repeat its ids."""
        return self.__copy__()

    def _seed(self) -> int:
        """A fresh random value for the field."""
        if self._draws is None:
            drawn = _draw(self._byte_source, self._width)
            return int.from_bytes(drawn, "big")
        value: object = self._draws.seed(self._width)
        return _check_draw("seed", value, 0, (1 << (8 * self._width)) - 1)

    def _step(self) -> int:
        """A step from 1 to 2**(4w), uniform over it."""
        bits = 4 * self._width
        if self._draws is None:
            drawn = _draw(self._byte_source, (bits + 7) // 8)
            return (int.from_bytes(drawn, "big") & ((1 << bits) - 1)) + 1
        value: object = self._draws.step(self._width)
        return _check_draw("step", value, 1, 1 << bits)

    def _body(self, millis: int, value: int) -> str:
        """The body for the time ``millis`` and the random value ``value``."""
        if self._compact:
            time_field = millis & _COMPACT_MASK
            if time_field >> 35 == _MARKER:
                raise UXIDError(
                    "compact_time_out_of_range",
                    f"compact_time: cannot encode {millis}: its first character"
                    " would be the deterministic marker; use standard time",
                )
            body = encode_integer(time_field, 8, self._alphabet)
        else:
            body = encode_integer(millis, 10, self._alphabet)
        return body + encode_bytes(value.to_bytes(self._width, "big"), self._alphabet)


def _check_types(
    prefix: object,
    rand_size: object,
    compact_time: object,
    delimiter: object,
    byte_source: object,
    draws: object,
) -> None:
    """Raise ``TypeError`` for an argument of the wrong type."""
    if not isinstance(prefix, str):
        raise TypeError(f"prefix: must be a str, got {prefix!r}")
    if rand_size is not None and not _is_int(rand_size):
        raise TypeError(f"rand_size: must be an int or None, got {rand_size!r}")
    if compact_time is not None and not isinstance(compact_time, bool):
        raise TypeError(f"compact_time: must be a bool or None, got {compact_time!r}")
    if not isinstance(delimiter, str):
        raise TypeError(f"delimiter: must be a str, got {delimiter!r}")
    if not callable(byte_source):
        raise TypeError(f"byte_source: must be callable, got {byte_source!r}")
    if draws is not None and not (
        callable(getattr(draws, "seed", None))
        and callable(getattr(draws, "step", None))
    ):
        raise TypeError(
            "draws: must have callable seed and step methods, or be None,"
            f" got {draws!r}"
        )


def _check_draw(name: str, value: object, low: int, high: int) -> int:
    """Check that the draw ``name`` returned an int from ``low`` to ``high``."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"draws: {name} must return an int, got {value!r}")
    if not low <= value <= high:
        raise ValueError(
            f"draws: {name} must return an int from {low} to {high}, got {value}"
        )
    return value
