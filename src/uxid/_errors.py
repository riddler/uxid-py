"""The error a refused request raises, and the closed set of its codes."""

from typing import Literal

ErrorCode = Literal[
    "compact_time_out_of_range",
    "rand_width_mismatch",
    "rand_size_too_large",
    "from_with_monotonic",
    "rand_with_from",
    "rand_with_monotonic",
]
"""The name of a refusal: one of the wire format's generation errors.

- ``compact_time_out_of_range``: a compact time whose first character would be
  the deterministic marker (the low 40 bits of the time at or above 31 x 2**35).
- ``rand_width_mismatch``: fixed random bytes whose count is not the random
  width of the request.
- ``rand_size_too_large``: an explicit random width above 10 bytes.
- ``from_with_monotonic``: a deterministic id asked for with monotonic
  generation.
- ``rand_with_from``: fixed random bytes asked for with a deterministic id.
- ``rand_with_monotonic``: fixed random bytes asked for with monotonic
  generation.

The names are the ones uxid-ex's wire-format spec and its conformance corpus
give these refusals. The set is closed: a code is always one of these six.
"""


class UXIDError(ValueError):
    """A request the wire format refuses, named by its ``code``.

    It is a ``ValueError``, so a caller that catches ``ValueError`` also
    catches the values ``uxid.generate`` refuses for other reasons (an unknown
    size, an empty delimiter, a time outside 0 to 2**48 - 1), which are plain
    ``ValueError`` and carry no code. Match on ``code``, never on the message,
    which is a sentence for a person and may change.

    >>> import uxid
    >>> try:
    ...     uxid.generate(prefix="usr", rand_size=11)
    ... except uxid.UXIDError as error:
    ...     print(error.code)
    rand_size_too_large
    """

    code: ErrorCode
    """The refusal's name, one of the closed set ``ErrorCode`` lists."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        """Create the error for the refusal ``code``, described by ``message``."""
        super().__init__(message)
        self.code = code

    def __reduce__(self) -> tuple[type["UXIDError"], tuple[ErrorCode, str]]:
        """Pickle the error with its code and its message."""
        return (type(self), (self.code, str(self)))
