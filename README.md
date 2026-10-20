# uxid

[![MIT License][badge_license_url]](https://github.com/riddler/uxid-py/blob/main/LICENSE)
[![CI][badge_ci_url]](https://github.com/riddler/uxid-py/actions/workflows/ci.yml)

User eXperience focused IDentifiers for Python: prefixed, K-sortable,
Stripe-style ids a person can read, copy and route back to their resource. An
id looks like `usr_01hf7yat0004hmasw9nf6yy093`: the prefix names the resource,
and the body carries a time and randomness in lower-case Crockford Base32. The
ids are wire-compatible with the Elixir reference implementation,
[uxid-ex](https://github.com/riddler/uxid-ex), and the package is checked
against that implementation's conformance corpus.

## Why UXID

An auto-increment key leaks how many rows a table holds and invites
enumeration; a random UUID fixes both but is long, unordered and anonymous, so
in a log line, a URL or a support thread nobody can tell what it points at, and
a double-click selects only part of it. A UXID names its resource in its
prefix, selects whole on a double-click, reads aloud without ambiguity, sorts
by creation time so it indexes well, and is generated in the application with
no coordination between nodes. Its size is tunable for low-cardinality
resources, a monotonic generator keeps a burst within one millisecond unique
and in order, and a deterministic mode maps the same input to the same id.

Because the format is shared, an id this package makes is read by the other
implementations of the format, and the other way round.

## Install

```bash
pip install uxid
```

## Basic usage

```python
import uxid

# A prefix names the resource; the body is a time and randomness.
id_ = uxid.generate(prefix="usr")
assert id_.startswith("usr_")

# Shrink the random part for low-cardinality resources.
# Sizes: "xs", "s", "m", "l" and "xl" (the default).
short = uxid.generate(prefix="cus", size="s")
assert len(short) == len("cus_") + 14

# Deterministic: the same prefix and input give the same id, every time.
named = uxid.generate(prefix="usr", from_="alice@example.com")
assert named == "usr_zcvt7epac0t1ebcsjfyf7cwz25"
assert uxid.is_deterministic(named)

# Read an id back. A malformed id is an Invalid, never an exception.
decoded = uxid.decode("cus_01hf7yat0004h1")
assert isinstance(decoded, uxid.Decoded)
assert (decoded.prefix, decoded.size, decoded.time) == ("cus", "s", 1_700_000_000_000)
assert uxid.is_valid("cus_01hf7yat0004h1", prefix="cus")
assert not uxid.is_valid("cus_01hf7yat0004h1", prefix="usr")
assert uxid.decode("cus_") == uxid.Invalid(reason="empty")

# Monotonic: ids from one generator increase strictly, also within one
# millisecond. You hold the generator; the package keeps no global state.
ids = uxid.Monotonic(prefix="usr", size="m")
first = ids.generate()
second = ids.generate()
assert first < second
```

A request the wire format refuses, such as `rand_size=11`, raises
`uxid.UXIDError`, a `ValueError` whose `code` is a stable `snake_case` name:
match on it, not on the message. A value that is simply wrong, such as an
unknown size or an empty delimiter, raises a plain `ValueError`, and one of the
wrong type a `TypeError`.

`generate` and `decode` read the system clock when they need a time, and
`generate` and `Monotonic` take their random bytes from `secrets.token_bytes`.
Each takes the clock as a `time` or `now` argument instead, and the generators
take a `byte_source`, a callable that answers that many bytes. Fixed random
bytes (`rand`) exist for test vectors: an id built from them is exactly as
guessable as those bytes.

## Upgrading from 0.0.1

Version 1.0.0 is a rewrite under the same project name, not an upgrade path.
The 0.0.1 release on PyPI was a placeholder, and nothing from its API carries
over: the package is now `uxid` with the functions and classes above, and ids
follow the shared wire format. Treat 1.0 as a fresh install and read the
docstrings named under Documentation. To stay on the placeholder, pin it with
`pip install "uxid==0.0.1"`.

## Compatibility

- **Python 3.11 or later** (`requires-python` in `pyproject.toml`). CI runs the
  tests on every minor from 3.11 through 3.14, and the full quality gate on the
  version `mise.toml` pins.
- **No runtime dependencies.** Random bytes come from `secrets.token_bytes`
  unless you give a `byte_source`, and the package never uses the `random`
  module. It ships a `py.typed` marker and is checked under `mypy --strict`.
- **Threads.** One `uxid.Monotonic` may be shared across threads: its state is
  guarded by a `threading.Lock` inside the instance, and ids from it increase
  strictly in the order the calls take the lock. Nothing is kept at module or
  class level. Ids from two generators carry no order between them within a
  millisecond. `generate`, `decode` and the validity checks hold no state and
  are safe from any thread.

## Documentation

- Look up
  - The docstrings: every public name carries one, with examples that the test
    suite runs. Read them with `help(uxid.generate)`, `help(uxid.decode)`,
    `help(uxid.Monotonic)` and the same for `uxid.is_valid`,
    `uxid.is_deterministic`, `uxid.Decoded`, `uxid.Invalid` and `uxid.UXIDError`.
  - [The wire format](https://github.com/riddler/uxid-py/blob/main/docs/wire-format.md): where the normative layout of an id
    lives, and which version of it this package follows.
  - [The changelog](https://github.com/riddler/uxid-py/blob/main/CHANGELOG.md): what changed in each version.
  - [The conformance corpus](https://github.com/riddler/uxid-py/tree/main/conformance): the cases every
    implementation of the wire format passes, vendored here from uxid-ex.
- Understand
  - [The reference spec, at v2.10.0][guide_wire_format_url]: the normative
    layout of an id - alphabet, bit packing, sizes, prefix grammar,
    deterministic and monotonic bodies, and decoding.
  - [Why a UXID has a prefix, a time and randomness][guide_why_url]: what each
    part of an id is for, and what you trade when you tune it.
  - [Why monotonic mode exists and what it costs][guide_monotonic_url]:
    same-millisecond uniqueness and ordering, and the security tradeoff.
  - [_Designing APIs for humans: object IDs_][stripe_ids_url]: the Stripe id
    design many of UXID's choices follow.

## Development

After checking out the repository, run `mise install` for the Python toolchain
and the tools `mise.toml` pins. Then `mise run gate:loop` runs the inner loop
(format, lint, the corpus check, tests), and `mise run gate` runs the full
quality gate: the inner loop plus `mypy --strict`, coverage over 90 percent and
a build. The tests include the conformance corpus, every case with no skip
list.

A release is published by CI, never from a checkout: pushing a tag `vX.Y.Z`
that names the version in `pyproject.toml` runs `.github/workflows/release.yml`,
which checks the tag and runs the gate, then publishes to
[PyPI](https://pypi.org/project/uxid/).

## Contributing

Bug reports and pull requests are welcome on GitHub at
https://github.com/riddler/uxid-py.

## License

The package is available as open source under the terms of the
[MIT License](https://opensource.org/licenses/MIT).

<!-- LINKS -->
[guide_wire_format_url]: https://github.com/riddler/uxid-ex/blob/v2.10.0/guides/wire-format.md
[guide_why_url]: https://github.com/riddler/uxid-ex/blob/v2.10.0/guides/why-prefix-time-randomness.md
[guide_monotonic_url]: https://github.com/riddler/uxid-ex/blob/v2.10.0/guides/monotonic.md
[stripe_ids_url]: https://dev.to/stripe/designing-apis-for-humans-object-ids-3o5a

<!-- BADGES -->
[badge_license_url]: https://img.shields.io/badge/license-MIT-brightgreen.svg
[badge_ci_url]: https://github.com/riddler/uxid-py/actions/workflows/ci.yml/badge.svg
