"""Reading an id back: ``decode`` and the validity checks built on it."""

import time as _time
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

from uxid._base32 import LOWER, UPPER
from uxid._generate import Size

InvalidReason = Literal["empty", "invalid_length", "invalid_character"]
"""Why ``uxid.decode`` refused a string: one of the wire format's refusals.

- ``empty``: the body is empty, an empty string or one ending in the
  delimiter.
- ``invalid_length``: the body's length in UTF-8 bytes is not one the length
  table lists (10, 13, 14, 18, 21, 22, 24 or 26).
- ``invalid_character``: a body character is not a Crockford Base32 symbol in
  either case.

The names are the ones uxid-ex's wire-format spec and its conformance corpus
give these refusals. The set is closed: a reason is always one of these three.
"""

# Body length in UTF-8 bytes to the size and whether the time is compact. The
# lengths 10 and 18 are also those of compact xs and compact m; the wire
# format reads both as standard.
_LENGTHS: Mapping[int, tuple[Size, bool]] = MappingProxyType(
    {
        10: ("xs", False),
        13: ("s", True),
        14: ("s", False),
        18: ("m", False),
        21: ("l", True),
        22: ("l", False),
        24: ("xl", True),
        26: ("xl", False),
    }
)

# Each symbol of the alphabet, in either case, to its 5-bit value.
_VALUES: Mapping[str, int] = MappingProxyType(
    {
        symbol: value
        for alphabet in (LOWER, UPPER)
        for value, symbol in enumerate(alphabet)
    }
)

_MARKERS = frozenset("zZ")
_COMPACT_WINDOW = 1 << 40
_ONE_DAY = 86_400_000


@dataclass(frozen=True, slots=True)
class Decoded:
    """What ``uxid.decode`` reads from a well-formed id.

    Its prefix, the size and time form its body length gives, whether its
    body is deterministic, and the time it carries. The random field, and a
    deterministic body's hash, are not read back. A frozen value: two
    decodings of the same id, under the same clock, are equal.

    >>> import uxid
    >>> decoded = uxid.decode("cus_01hf7yat0004h1")
    >>> decoded.prefix, decoded.size, decoded.compact, decoded.time
    ('cus', 's', False, 1700000000000)
    """

    prefix: str | None
    """Everything before the last delimiter, or ``None`` when the id has no
    delimiter. An id that starts with the delimiter, which no producer emits,
    has the prefix ``''``, best read as no prefix."""

    size: Size
    """The size the body length gives, always a short spelling: ``xs``,
    ``s``, ``m``, ``l`` or ``xl``."""

    compact: bool
    """Whether the body length is a compact-time one (13, 21 or 24). The
    lengths 10 and 18 always read as standard time, so a compact xs or compact
    m id decodes with this ``False``."""

    deterministic: bool
    """Whether the body starts with the deterministic marker, ``z`` or
    ``Z``."""

    time: int | None
    """The time in milliseconds since the Unix epoch, or ``None`` for a
    deterministic body, which carries none. A compact time's high bits come
    from the decoder's clock, ``uxid.decode``'s ``now``, and it can be
    negative: a compact time more than a day ahead of a clock in the first
    2**40 ms window after the Unix epoch is read as one from the window
    before it."""


@dataclass(frozen=True, slots=True)
class Invalid:
    """What ``uxid.decode`` answers for a string it refuses: the reason.

    >>> import uxid
    >>> uxid.decode("usr_")
    Invalid(reason='empty')
    """

    reason: InvalidReason
    """The refusal's name, one of the closed set ``InvalidReason`` lists."""


def decode(
    id_: str, *, delimiter: str = "_", now: int | None = None
) -> Decoded | Invalid:
    """Read an id back to a ``Decoded``, or refuse it with an ``Invalid``.

    The reading is uxid-ex's wire-format spec's. The body is everything after
    the last delimiter found reading left to right, matches not overlapping,
    and the prefix everything before it; a string with no delimiter is a body
    with no prefix. Under ``--``, ``usr---01hf7yat00`` splits after ``usr``,
    not at the last ``--``. The delimiter is not recorded in an id, so it must
    be the one the id was generated with.

    The body's length in UTF-8 bytes gives the size and the time form:

    ============  ====  ========
    Body length   Size  Time
    ============  ====  ========
    10            xs    standard
    13            s     compact
    14            s     standard
    18            m     standard
    21            l     compact
    22            l     standard
    24            xl    compact
    26            xl    standard
    ============  ====  ========

    The lengths 10 and 18 are also those of a compact xs and a compact m body,
    and they are always read as standard time, as the spec states: such an id
    decodes to its size, ``compact`` ``False``, with a time read from its
    first 10 characters, which is not the time it was generated at. A body
    that starts with ``z`` or ``Z`` is deterministic and has no time. Either
    case reads the same.

    A compact body carries only the low 40 bits of its time; the high bits are
    the clock's, less one 2**40 millisecond window when the result would be
    more than one day (86400000 ms) ahead of the clock, even when that makes
    the time negative. So the time comes back exact while the id and the clock fall in
    the same 2**40 ms window (about 34.8 years) and the id is no more than one
    day ahead of the clock.

    - ``id_``: the string to read (the trailing underscore because ``id`` is a
      Python built-in).
    - ``delimiter``: the non-empty string between the prefix and the body,
      ``_`` by default.
    - ``now``: the decoder's clock for a compact time, an int of milliseconds
      since the Unix epoch, 0 or more. ``None``, the default, reads the system
      clock, and only for a compact body; a standard or deterministic body
      reads no clock.

    >>> import uxid
    >>> decoded = uxid.decode("usr_hf7yat0004hm5", now=1_700_000_000_000)
    >>> decoded.size, decoded.compact, decoded.time
    ('s', True, 1700000000000)
    >>> uxid.decode("usr_zcvt7epac0t1ebcsjfyf7cwz25").deterministic
    True
    >>> uxid.decode("usr_01hf7yat000")
    Invalid(reason='invalid_length')
    >>> uxid.decode("usr_01hu7yat00")
    Invalid(reason='invalid_character')

    A string is refused, as an ``Invalid`` and never by raising, with the
    first of these it fails: ``empty`` for an empty body, ``invalid_length``
    for a body whose length in UTF-8 bytes is not in the table above, and
    ``invalid_character`` for a body character that is not a Crockford Base32
    symbol in either case. A lone surrogate in ``id_``, which has no UTF-8
    form, counts as the 3 bytes of its code point and is never a symbol.

    Raises ``TypeError`` for an ``id_`` that is not a ``str``, a ``delimiter``
    that is not a ``str``, or a ``now`` that is not an ``int`` or ``None``
    (``bool`` included), and ``ValueError`` for an empty delimiter or a
    negative ``now``: those are mistakes in the call, not malformed input.
    """
    _check(id_, delimiter, now)
    return _decode(id_, delimiter, now)


def is_valid(id_: object, *, delimiter: str = "_", prefix: str | None = None) -> bool:
    """Whether ``id_`` is a well-formed id, carrying ``prefix`` when given.

    That is, whether ``uxid.decode`` answers a ``Decoded`` for it under
    ``delimiter`` and, when ``prefix`` is a non-empty string, whether that
    ``Decoded``'s prefix is exactly ``prefix``. ``None``, the default, and
    ``''`` accept any prefix or none; an id with no delimiter has no prefix,
    so it fails any other. Validity does not depend on the clock, so this
    reads none. A value that is not a ``str`` is not valid.

    >>> import uxid
    >>> uxid.is_valid("cus_01hf7yat0004h1")
    True
    >>> uxid.is_valid("cus_01hf7yat0004h1", prefix="usr")
    False
    >>> uxid.is_valid("cus--01hf7yat0004h1", delimiter="--", prefix="cus")
    True
    >>> uxid.is_valid("usr_01hu7yat00")
    False

    Raises ``TypeError`` for a ``delimiter`` that is not a ``str`` or a
    ``prefix`` that is not a ``str`` or ``None``, and ``ValueError`` for an
    empty delimiter.
    """
    _check_delimiter(delimiter)
    if prefix is not None and not isinstance(prefix, str):
        raise TypeError(f"prefix: must be a str or None, got {prefix!r}")
    if not isinstance(id_, str):
        return False
    decoded = _decode(id_, delimiter, 0)
    if not isinstance(decoded, Decoded):
        return False
    return not prefix or decoded.prefix == prefix


def is_deterministic(id_: object, *, delimiter: str = "_") -> bool:
    """Whether ``id_`` is a well-formed deterministic id.

    That is, whether ``uxid.decode`` answers a ``Decoded`` for it under
    ``delimiter`` whose body starts with the marker ``z`` or ``Z``: one
    ``uxid.generate`` made with ``from_``. A malformed string is not one,
    whatever its first body character, and neither is a value that is not a
    ``str``. It reads no clock.

    >>> import uxid
    >>> uxid.is_deterministic("usr_zcvt7epac0t1ebcsjfyf7cwz25")
    True
    >>> uxid.is_deterministic("usr_01hf7yat0004h1")
    False
    >>> uxid.is_deterministic("usr_zcvt7epac")
    False

    Raises ``TypeError`` for a ``delimiter`` that is not a ``str``, and
    ``ValueError`` for an empty delimiter.
    """
    _check_delimiter(delimiter)
    if not isinstance(id_, str):
        return False
    decoded = _decode(id_, delimiter, 0)
    return isinstance(decoded, Decoded) and decoded.deterministic


def _check(id_: object, delimiter: object, now: object) -> None:
    """Raise for an argument of ``decode`` that is a mistake in the call."""
    if not isinstance(id_, str):
        raise TypeError(f"id_: must be a str, got {id_!r}")
    _check_delimiter(delimiter)
    if now is None:
        return
    if not isinstance(now, int) or isinstance(now, bool):
        raise TypeError(f"now: must be an int of milliseconds or None, got {now!r}")
    if now < 0:
        raise ValueError(f"now: must be 0 or more milliseconds, got {now}")


def _check_delimiter(delimiter: object) -> None:
    """Raise for a delimiter that is not a non-empty ``str``."""
    if not isinstance(delimiter, str):
        raise TypeError(f"delimiter: must be a str, got {delimiter!r}")
    if not delimiter:
        raise ValueError("delimiter: must be a non-empty string")


def _decode(id_: str, delimiter: str, now: int | None) -> Decoded | Invalid:
    """Decode checked arguments, reading the clock only for a compact body."""
    parts = id_.split(delimiter)
    body = parts[-1]
    prefix = delimiter.join(parts[:-1]) if len(parts) > 1 else None
    if not body:
        return Invalid("empty")
    form = _LENGTHS.get(len(body.encode("utf-8", "surrogatepass")))
    if form is None:
        return Invalid("invalid_length")
    if not all(symbol in _VALUES for symbol in body):
        return Invalid("invalid_character")
    size, compact = form
    deterministic = body[0] in _MARKERS
    if deterministic:
        time = None
    elif compact:
        time = _compact_time(_read(body[:8]), _now_millis() if now is None else now)
    else:
        time = _standard_time(body)
    return Decoded(prefix, size, compact, deterministic, time)


def _read(symbols: str) -> int:
    """Read ``symbols`` as one integer, 5 bits each, most significant first."""
    value = 0
    for symbol in symbols:
        value = (value << 5) | _VALUES[symbol]
    return value


def _standard_time(body: str) -> int:
    """The 48-bit time: the first symbol's low 3 bits, then nine 5-bit groups.

    A producer never writes a first symbol above 7; its higher bits are not
    read.
    """
    return ((_VALUES[body[0]] & 7) << 45) | _read(body[1:10])


def _compact_time(low: int, now: int) -> int:
    """The low 40 bits from the id and the high bits from the clock ``now``.

    A result more than a day ahead of the clock is from the window before,
    with no exception: in the first window after the Unix epoch that time is
    negative.
    """
    time = ((now >> 40) << 40) | low
    if time - now > _ONE_DAY:
        return time - _COMPACT_WINDOW
    return time


def _now_millis() -> int:
    """The system clock in milliseconds since the Unix epoch."""
    return _time.time_ns() // 1_000_000
