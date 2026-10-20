# Changelog

## 1.0.0 - 2026-10-20

A rewrite under the existing project name, and a breaking release: the 0.0.1
placeholder's API is gone, and nothing from it carries over. The package now
implements the wire format of the Elixir reference implementation,
[uxid-ex](https://github.com/riddler/uxid-ex), and passes every case of that
implementation's conformance corpus at the tag `v2.10.0`, vendored under
`conformance/` (`conformance/SOURCE.json` records the tag, its commit and the
corpus hash). It requires Python 3.11 or later and has no runtime
dependencies. To stay on the placeholder, pin `uxid==0.0.1`; the README's
"Upgrading from 0.0.1" says what a caller does.

### Added

- `uxid.generate(...)` builds a time-based id from the keyword arguments
  `prefix`, `size`, `rand_size`, `compact_time`, `case`, `delimiter` and
  `time`. Sizes are `xs`, `s`, `m`, `l` and `xl` (the default), with the long
  spellings `xsmall` to `xlarge`; the body is lower-case Crockford Base32 unless
  `case="upper"`. Random bytes come from `byte_source`, a callable answering
  that many bytes (default `secrets.token_bytes`); `rand` fixes the random
  field for test vectors only.
- `uxid.generate(from_="...")` builds a deterministic id: the marker `z` and
  then the first bits of the SHA-256 of the prefix, the string and the size, so
  the same arguments always give the same id, and it sorts after every
  time-based id with the same prefix and case.
- `uxid.decode(id_, delimiter="_", now=None)` reads an id back and never raises
  on a malformed string: a well-formed id gives a frozen `Decoded` with
  `prefix`, `size`, `compact`, `deterministic`, `time` and `negative`, and
  anything else a frozen `Invalid` whose `reason` is `empty`,
  `invalid_length` or `invalid_character`. A compact time takes its high bits
  from `now` (default the system clock), so the clock is injectable.
- `uxid.is_valid(id_, prefix=None, delimiter="_")` is whether the id decodes
  and, when `prefix` is given, carries exactly that prefix;
  `uxid.is_deterministic(id_, delimiter="_")` is whether it decodes to a
  deterministic body. Neither raises on the id.
- `uxid.Monotonic(...)` is a generator whose ids increase strictly, within one
  millisecond and when the clock moves back, by the monotonic rule of the wire
  format. Its state and its `threading.Lock` belong to the instance, so one
  generator may be shared across threads; the package keeps no module-level
  state. `draws` replays recorded random draws.
- `uxid.UXIDError`, a `ValueError` whose `code` names a refusal the wire format
  defines: `compact_time_out_of_range`, `rand_width_mismatch`,
  `rand_size_too_large`, `from_with_monotonic`, `rand_with_from` and
  `rand_with_monotonic`. A value that is simply wrong raises a plain
  `ValueError`, and one of the wrong type a `TypeError`.
- The type aliases `Size`, `Case`, `ByteSource`, `ErrorCode` and
  `InvalidReason`, the protocol `Draws`, `uxid.__version__`, and a `py.typed`
  marker; the package is checked under `mypy --strict`.

### Removed

- Breaking: the 0.0.1 placeholder's API is removed. Call `uxid.generate`,
  `uxid.decode`, `uxid.is_valid`, `uxid.is_deterministic` and `uxid.Monotonic`
  as above, or pin `uxid==0.0.1`.

## 0.0.1 - 2020-06-18

- Placeholder release that reserved the project name.
