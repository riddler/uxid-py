"""Id generation, time-based or deterministic, under an optional prefix."""

import hashlib
import secrets
import time as _time
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Literal

from uxid._base32 import LOWER, UPPER, encode_bytes, encode_integer
from uxid._errors import UXIDError

Size = Literal[
    "xs", "s", "m", "l", "xl", "xsmall", "small", "medium", "large", "xlarge"
]
"""An id's size: ``xs``, ``s``, ``m``, ``l`` or ``xl``, or the long spellings
``xsmall``, ``small``, ``medium``, ``large`` and ``xlarge``."""

Case = Literal["lower", "upper"]
"""The letter case of an id's body."""

ByteSource = Callable[[int], bytes]
"""A source of random bytes: called with a count, it returns that many bytes."""

_SIZES: Mapping[str, str] = MappingProxyType(
    {
        "xs": "xs",
        "xsmall": "xs",
        "s": "s",
        "small": "s",
        "m": "m",
        "medium": "m",
        "l": "l",
        "large": "l",
        "xl": "xl",
        "xlarge": "xl",
    }
)

# The random field's width in bytes per size: standard time, then compact time.
_RAND_BYTES: Mapping[str, tuple[int, int]] = MappingProxyType(
    {
        "xs": (0, 1),
        "s": (2, 3),
        "m": (5, 6),
        "l": (7, 8),
        "xl": (10, 10),
    }
)

# The hash characters of a deterministic body per size, after the marker.
_HASH_CHARS: Mapping[str, int] = MappingProxyType(
    {"xs": 9, "s": 13, "m": 17, "l": 21, "xl": 25}
)

_MAX_RAND_BYTES = 10
_MAX_TIME = (1 << 48) - 1
_COMPACT_MASK = (1 << 40) - 1
_MARKER = 31


def generate(
    *,
    prefix: str = "",
    size: Size = "xl",
    rand_size: int | None = None,
    compact_time: bool = False,
    case: Case = "lower",
    delimiter: str = "_",
    time: int | None = None,
    rand: bytes | None = None,
    byte_source: ByteSource = secrets.token_bytes,
    from_: str | None = None,
) -> str:
    """Generate an id: the prefix, the delimiter, then the body.

    The body is in Crockford Base32, laid out as uxid-ex's wire-format spec
    defines it. It is time-based, a time field followed by a random field,
    unless ``from_`` is given; then it is deterministic, the marker character
    and then a hash, so the same arguments always give the same id. Every
    argument is a keyword argument and every one has a default:

    - ``prefix``: written before the delimiter exactly as given (case never
      applies to it), and it may contain the delimiter. An empty string, the
      default, is no prefix: the id is then the bare body, with no delimiter.
    - ``size``: ``xs``, ``s``, ``m``, ``l`` or ``xl``, or the long spellings
      ``xsmall``, ``small``, ``medium``, ``large`` and ``xlarge``. It fixes
      the random field's width: 0, 2, 5, 7 and 10 bytes in standard time, and
      1, 3, 6, 8 and 10 in compact time. Defaults to ``xl``.
    - ``rand_size``: an explicit random field width in bytes, from 0 to 10,
      in place of the size's. A body of a width the size table does not list
      has the same layout, but its length is one a decoder refuses.
    - ``compact_time``: ``True`` for compact time, the low 40 bits of the
      time in 8 characters; ``False``, the default, for standard time, 48
      bits in 10. Compact time hands the freed byte to the random field,
      except at ``xl``.
    - ``case``: ``lower``, the default, or ``upper``, the case of every body
      character. An upper-case body and its lower-case spelling are the same
      id.
    - ``delimiter``: the non-empty string between the prefix and the body,
      ``_`` by default.
    - ``time``: milliseconds since the Unix epoch, from 0 to 2**48 - 1.
      ``None``, the default, reads the system clock.
    - ``rand``: fixed random field bytes, exactly the random width of the
      request; ``byte_source`` is then not called. This exists for
      reproducible ids such as test vectors, never as a source of
      randomness: an id built from fixed bytes is exactly as guessable as
      those bytes. Leave it ``None`` for real ids.
    - ``byte_source``: where the random field's bytes come from, a callable
      that takes a count and returns exactly that many bytes. It is called
      at most once per id, and never when the random width is 0 or ``rand``
      is given. Defaults to ``secrets.token_bytes``; a source for real ids
      must be cryptographically secure.
    - ``from_``: the string a deterministic body is the hash of (the trailing
      underscore because ``from`` is a Python keyword). ``None``, the
      default, gives a time-based id; any string, the empty string included,
      gives a deterministic one. Its body is the marker, ``z`` (``Z`` in an
      upper-case id), then the first 5 x count bits of the SHA-256 of the
      prefix, a zero byte, ``from_``, a zero byte and one byte holding count,
      the prefix and ``from_`` as UTF-8. Count is the size's number of hash
      characters, 9, 13, 17, 21 and 25 from ``xs`` to ``xl``, so the body has
      the size's standard length. ``time``, ``compact_time``, ``rand_size``
      and ``byte_source`` do not apply: their values are not read and the
      byte source is not called, though each is still type-checked. A
      deterministic id sorts after every time-based id with its prefix and
      case, and it is exactly as guessable as ``from_``.

    Every width and length here is counted in bytes.

    >>> import uxid
    >>> uxid.generate(prefix="usr", size="xs", time=1_700_000_000_000)
    'usr_01hf7yat00'
    >>> uxid.generate(
    ...     prefix="cus", size="s", time=1_700_000_000_000, rand=bytes([0x01, 0x23])
    ... )
    'cus_01hf7yat0004h1'
    >>> def zeros(count: int) -> bytes:
    ...     return bytes(count)
    >>> uxid.generate(size="m", time=1_700_000_000_000, byte_source=zeros)
    '01hf7yat0000000000'
    >>> len(uxid.generate(prefix="usr"))
    30
    >>> uxid.generate(prefix="cus", from_="acme-corp", size="s")
    'cus_zt9vnyfd85bff0'

    Raises ``uxid.UXIDError``, with its ``code``, for a refusal the wire
    format names: ``rand_size_too_large`` for a ``rand_size`` above 10,
    ``rand_width_mismatch`` for ``rand`` bytes whose count is not the random
    width, ``compact_time_out_of_range`` for a compact time whose first
    character would be the deterministic marker (the low 40 bits of the time
    at or above 31 x 2**35, the last thirty-second of every 2**40 millisecond
    window; in the current window, from mid-2038 until it rolls over in
    2039), and ``rand_with_from`` for ``rand`` given with ``from_``. Raises a
    plain ``ValueError`` for any other value it refuses: an unknown size or
    case, an empty delimiter, a negative ``rand_size``, a time outside 0 to
    2**48 - 1, a byte source that returns the wrong number of bytes, and, for
    a deterministic id, a prefix or ``from_`` that has no UTF-8 form (one
    holding a lone surrogate). Raises ``TypeError`` for an argument of the
    wrong type, ``bool`` included where an ``int`` is asked for, and for a
    byte source that does not return bytes.
    """
    _check_types(
        prefix, rand_size, compact_time, delimiter, time, rand, byte_source, from_
    )
    if from_ is not None and rand is not None:
        raise UXIDError(
            "rand_with_from",
            "rand: cannot be given with from_: a deterministic body has no"
            " random field",
        )
    canonical = _canonical_size(size)
    alphabet = _alphabet(case)
    if not delimiter:
        raise ValueError("delimiter: must be a non-empty string")
    if from_ is not None:
        body = _deterministic_body(prefix, from_, canonical, alphabet)
        return f"{prefix}{delimiter}{body}" if prefix else body
    millis = _now_millis() if time is None else time
    if not 0 <= millis <= _MAX_TIME:
        raise ValueError(
            f"time: must be from 0 to 2**48 - 1 milliseconds, got {millis}"
        )
    width = _width(canonical, compact_time, rand_size)
    if rand is not None and len(rand) != width:
        raise UXIDError(
            "rand_width_mismatch",
            f"rand: must be exactly {width} bytes, the random width of this request,"
            f" got {len(rand)}",
        )
    if compact_time:
        time_field = millis & _COMPACT_MASK
        if time_field >> 35 == _MARKER:
            raise UXIDError(
                "compact_time_out_of_range",
                f"compact_time: cannot encode {millis}: its first character would be"
                " the deterministic marker; use standard time",
            )
        body = encode_integer(time_field, 8, alphabet)
    else:
        body = encode_integer(millis, 10, alphabet)
    random_field = rand if rand is not None else _draw(byte_source, width)
    body += encode_bytes(random_field, alphabet)
    return f"{prefix}{delimiter}{body}" if prefix else body


def _check_types(
    prefix: object,
    rand_size: object,
    compact_time: object,
    delimiter: object,
    time: object,
    rand: object,
    byte_source: object,
    from_: object,
) -> None:
    """Raise ``TypeError`` for an argument of the wrong type."""
    if not isinstance(prefix, str):
        raise TypeError(f"prefix: must be a str, got {prefix!r}")
    if rand_size is not None and not _is_int(rand_size):
        raise TypeError(f"rand_size: must be an int or None, got {rand_size!r}")
    if not isinstance(compact_time, bool):
        raise TypeError(f"compact_time: must be a bool, got {compact_time!r}")
    if not isinstance(delimiter, str):
        raise TypeError(f"delimiter: must be a str, got {delimiter!r}")
    if time is not None and not _is_int(time):
        raise TypeError(f"time: must be an int of milliseconds or None, got {time!r}")
    if rand is not None and not isinstance(rand, bytes):
        raise TypeError(f"rand: must be bytes or None, got {rand!r}")
    if not callable(byte_source):
        raise TypeError(f"byte_source: must be callable, got {byte_source!r}")
    if from_ is not None and not isinstance(from_, str):
        raise TypeError(f"from_: must be a str or None, got {from_!r}")


def _is_int(value: object) -> bool:
    """Whether ``value`` is an ``int`` and not a ``bool``."""
    return isinstance(value, int) and not isinstance(value, bool)


def _canonical_size(size: object) -> str:
    """The short spelling of ``size``."""
    if not isinstance(size, str):
        raise TypeError(f"size: must be a str, got {size!r}")
    try:
        return _SIZES[size]
    except KeyError:
        raise ValueError(
            "size: must be one of xs, s, m, l, xl, xsmall, small, medium, large"
            f" or xlarge, got {size!r}"
        ) from None


def _alphabet(case: object) -> str:
    """The alphabet for ``case``."""
    if not isinstance(case, str):
        raise TypeError(f"case: must be a str, got {case!r}")
    if case == "lower":
        return LOWER
    if case == "upper":
        return UPPER
    raise ValueError(f"case: must be lower or upper, got {case!r}")


def _width(size: str, compact_time: bool, rand_size: int | None) -> int:
    """The random field's width in bytes."""
    if rand_size is None:
        return _RAND_BYTES[size][1 if compact_time else 0]
    if rand_size < 0:
        raise ValueError(f"rand_size: must be from 0 to 10 bytes, got {rand_size}")
    if rand_size > _MAX_RAND_BYTES:
        raise UXIDError(
            "rand_size_too_large",
            f"rand_size: must be at most {_MAX_RAND_BYTES} bytes, got {rand_size}",
        )
    return rand_size


def _deterministic_body(prefix: str, from_: str, size: str, alphabet: str) -> str:
    """The marker, then the first 5 x count bits of the hash input's SHA-256."""
    count = _HASH_CHARS[size]
    data = b"".join(
        [
            _utf8("prefix", prefix),
            b"\x00",
            _utf8("from_", from_),
            b"\x00",
            bytes([count]),
        ]
    )
    digest = int.from_bytes(hashlib.sha256(data).digest(), "big")
    hash_bits = digest >> (256 - 5 * count)
    return alphabet[_MARKER] + encode_integer(hash_bits, count, alphabet)


def _utf8(name: str, text: str) -> bytes:
    """The UTF-8 bytes of ``text``, the value of the argument ``name``."""
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(
            f"{name}: must have a UTF-8 form for a deterministic id, got {text!r}"
        ) from None


def _now_millis() -> int:
    """The system clock in milliseconds since the Unix epoch."""
    return _time.time_ns() // 1_000_000


def _draw(byte_source: ByteSource, width: int) -> bytes:
    """Draw the random field's ``width`` bytes from ``byte_source``."""
    if width == 0:
        return b""
    drawn: object = byte_source(width)
    if not isinstance(drawn, bytes):
        raise TypeError(f"byte_source: must return bytes, got {drawn!r}")
    if len(drawn) != width:
        raise ValueError(
            f"byte_source: must return exactly {width} bytes, got {len(drawn)}"
        )
    return drawn
