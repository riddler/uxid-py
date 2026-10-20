"""Crockford Base32 as the wire format writes it.

Thirty-two symbols in ASCII order, with ``I``, ``L``, ``O`` and ``U`` left out,
no padding and no check symbol.
"""

LOWER = "0123456789abcdefghjkmnpqrstvwxyz"
UPPER = LOWER.upper()


def encode_integer(value: int, count: int, alphabet: str) -> str:
    """Write the low ``count`` 5-bit groups of ``value``, most significant first.

    The first group holds whatever bits remain above the others, which is how
    the standard 48-bit time writes its 3-bit first group.
    """
    return "".join(alphabet[(value >> (5 * i)) & 31] for i in range(count - 1, -1, -1))


def encode_bytes(data: bytes, alphabet: str) -> str:
    """Write ``data`` as 5-bit groups, most significant bit first.

    When the bit count is not a multiple of 5 the last group is short, and it
    is written as its raw value, never shifted or padded: ``ff ff`` is
    ``zzz1``.
    """
    bits = len(data) * 8
    value = int.from_bytes(data, "big")
    short = bits % 5
    body = encode_integer(value >> short, bits // 5, alphabet)
    if short:
        body += alphabet[value & ((1 << short) - 1)]
    return body
