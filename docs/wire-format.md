# Wire format

This package does not restate the format. The normative layout of a uxid - the
alphabet, the bit packing, the sizes, the prefix grammar, the time and
deterministic bodies, monotonic generation and decoding - is the reference
implementation's guide, read at the release tag this package's vendored corpus
names:

[UXID wire format, at v2.10.0](https://github.com/riddler/uxid-ex/blob/v2.10.0/guides/wire-format.md)

The tag is the one recorded in `conformance/SOURCE.json`, beside the commit it
names and the hash of the corpus. A change that re-vendors the corpus at
another tag updates this pointer and the README's links to the reference in
the same change; no test checks them.

## The corpus is the arbiter

The conformance corpus is vendored under `conformance/`, byte for byte from
the same tag. The test suite runs every case in it with no skip list
(`tests/test_conformance.py`), and `scripts/check_corpus.py`, part of the gate,
checks the vendored files against the recorded hash. This package is held to
the corpus: a case it cannot pass is a bug here or a question for the
reference implementation, never a skip, and a difference between the guide and
the corpus is raised there rather than worked round here. An answer the corpus
does not fix follows the guide at the tag.

## What this package decides for itself

The Python API: the function, class and argument names, the injectable byte
source and clock, and the `UXIDError` codes and `Invalid` reasons where the
guide names no refusal. Those are documented in the docstrings of `src/uxid/`.
