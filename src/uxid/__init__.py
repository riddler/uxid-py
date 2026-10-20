"""Prefixed, K-sortable, human-readable identifiers.

``uxid`` makes ids such as ``usr_01hf7yat0004hmasw9nf6yy093``: an optional
prefix, a delimiter, and a body that starts with a millisecond time and ends
with random bytes, in Crockford Base32; or, given a string to hash, a
deterministic body that is the same for the same arguments. It follows the
wire format of the Elixir ``uxid`` package (uxid-ex's
``guides/wire-format.md``), so the two produce the same strings for the same
inputs. ``uxid.decode`` reads an id back, and ``uxid.is_valid`` and
``uxid.is_deterministic`` check one.

>>> import uxid
>>> uxid.generate(prefix="usr", size="xs", time=1_700_000_000_000)
'usr_01hf7yat00'
>>> uxid.generate(prefix="usr", from_="alice@example.com")
'usr_zcvt7epac0t1ebcsjfyf7cwz25'
>>> uxid.decode("usr_01hf7yat00").time
1700000000000
>>> uxid.is_valid("usr_01hf7yat00", prefix="usr")
True
"""

from importlib.metadata import version

from uxid._decode import (
    Decoded,
    Invalid,
    InvalidReason,
    decode,
    is_deterministic,
    is_valid,
)
from uxid._errors import ErrorCode, UXIDError
from uxid._generate import ByteSource, Case, Size, generate

__version__ = version("uxid")

__all__ = [
    "ByteSource",
    "Case",
    "Decoded",
    "ErrorCode",
    "Invalid",
    "InvalidReason",
    "Size",
    "UXIDError",
    "__version__",
    "decode",
    "generate",
    "is_deterministic",
    "is_valid",
]
