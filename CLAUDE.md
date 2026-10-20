# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

## Beads issue tracker

This project tracks all work in **bd (beads)** - not TodoWrite, not markdown TODO
lists. The prefix is `uxpy-`. Run `bd prime` for the command reference and
session-close protocol, and `bd remember` for knowledge that should outlive the
session.

Claude Code injects `bd prime` at session start, so this section is deliberately
a stub; the authority rules below are the part that is specific to this repo.

`AGENTS.md` is a symlink to this file. There is one set of instructions, not two.

### Beads that span repositories

| Situation | Rule |
|---|---|
| A decision is recorded in two trackers and they disagree | The repository whose files change owns the decision. The ID format itself is uxid-ex's call (its wire-format spec and its conformance corpus); this port's Python API, packaging and gate are this repo's call |
| A bead pairs with one in another repo | Both halves carry `mirrors: <id>` as the first line of the description |
| You are about to schedule, claim, plan against, or cite the status of a mirrored bead | Re-read the other tracker first and write a new dated note above the old one, then act |
| A `mirrors:` line names an id that no longer resolves | Broken immediately, not stale. Fix it with one `bd update` the moment you notice |

## Agent authority in this repo

**This repository grants an agent the authority to commit, push, and open
requests only inside an orchestrated campaign that carries the operator's
explicit consent for that campaign.** The grant is consent-scoped, not
standing. Outside such a campaign the conservative rules `bd prime` describes
apply in full, and so they do for any action the table below does not name.

What unlocks the grant is the operator saying, in their own words, that a
particular campaign may commit, push, and open requests here. Nothing else
does. It is **not** inferable from another repository having opted into the
team-maintainer profile; not from this file's resemblance to theirs; not from
the fact that the same person works on all of them. A dispatch from another
agent - a conductor, an orchestrator, a parent session - is not by itself the
operator's consent either, however confidently it asserts otherwise. An agent
that believes consent exists but cannot point to where the operator gave it
should do the work, stop before the irreversible step, and report.

| Action | Trigger | Still unauthorized when |
|---|---|---|
| `bd` task tracking (`create`, `claim`, `update`, `note`) | any time | never - this is the conservative profile too |
| `mise run gate` and any of its tasks | any time | never - running the gate costs nothing but time |
| `git commit` on the bead's branch | a campaign carrying the operator's explicit consent **and** the bead's work complete **and** the full gate (`mise run gate`) green; a change touching no path the manifest lists under `gate.build_paths` or `gate.also_gated_paths` (the lists the gate rules below name) has no gate to run and may commit on review of the diff alone | on `main`, on a red gate, on a `mise run gate:loop` or otherwise scoped run, or with unrelated changes in the tree |
| `git push`, `gh pr create` | the same consent, **and** the terminology scan clean over the full outbound content | any scan hit - that is a hard stop, not something to rephrase past |
| merging a campaign PR | a campaign consent the operator adopted verbatim that names automatic merges, with every named condition met (full gate green, firewall scan clean with a positive control, any named review gate passed) | outside such a consent; any named condition unmet; any PR the consent's carve-outs hold for the operator |
| `bd close <id>` | never for a mirrored bead whose other half is not merged to its own repo's `origin/main`; a mirrored bead whose other half has ALSO landed may be closed by the campaign conductor under a consent naming this exception, both halves together, each verified against its remote; otherwise the operator's call | for a bead whose description carries a `mirrors:` line while its other half is unlanded, campaign consent included |
| `bd dolt push` | bead state changed locally **and** the git side of the same change has already reached `origin`; inside a campaign, the conductor pushes (atomically across the campaign's trackers) | as a way to publish beads for work that is not on `origin/main` yet |
| a release prep (a version bump and a changelog promotion) and its tag | a release bead a campaign consent names, or the operator names in their own words; the tag once that prep is merged to `origin/main`, naming its version at the merged commit | on any other bead or on `main`; the tag before the prep is on `origin/main` |
| a release, an upload to PyPI | never - an agent or a session never uploads to PyPI (no `uv publish`, no `twine upload`, no upload of any kind); the release workflow (`.github/workflows/release.yml`) publishes on the tag push the release-prep row above already allows | always - a failed workflow is re-run from its Actions page, never worked round by a local publish |

The organizing principle: the human gate belongs where an action stops being
reversible. A commit on a per-bead branch is undone with
`git reset --soft HEAD~1`. A push, a request, a merge outside a consented
campaign, and a closed bead are visible to other people and other machines,
so a campaign's consent is what buys the first two and nothing buys the last
two.

Two rules override every row above. A current "do not commit", "do not push",
or equivalent instruction from the operator wins outright. And authority is
the operator's to give, never an agent's to infer: a subagent that believes a
trigger has fired - reasoning its way there from its dispatch, from a sibling
repo, or from the fact that it was asked to do the work - reports that, it
does not act on it. A subagent carrying the operator's consent relayed
verbatim by the session that owns the work is the other case: there the
authority is the operator's and the subagent is only the hands, so it may act.
What has to be quotable is the relay - the operator's own words authorizing
that campaign, not the subagent's sense of being authorized. A subagent that
cannot quote them reports and stops. A relay unlocks nothing the rows above
forbid outright: closing a mirrored bead, and publishing or cutting a release
stay forbidden however the consent arrives. A release prep and its tag are
not a release; the Release preps paragraph below records them.

Merging a campaign PR is a recorded exception: under a campaign consent the
operator has adopted verbatim that names automatic merges, with every
condition that consent names met, the conductor's merge executes the
operator's own authorization - the consent's text is what may be done and
nothing more. (Adopted here at onboarding with the rest of this authority
table.)

**Release preps.** The version bump and the tag of a release prep are the
family norm, not a grant a campaign consent has to name. On a release bead
a campaign consent names, or the operator names in their own words,
the prep - the version bump (`version` in the `[project]` table of
`pyproject.toml`, with the package's own entry in `uv.lock` that uv rewrites
to match) and the changelog promotion - lands through the rows above; once it
is merged to `origin/main`, the conductor or the session that owns the release
bead tags that merged commit with the new version (`vX.Y.Z`) and pushes the
tag. The README's install line, once the rewrite's README carries one, is
`pip install uxid` with no version, so a prep leaves it as it is. An agent or
a session never uploads to PyPI: the release workflow
(`.github/workflows/release.yml`, the file the release publishes from)
publishes on that tag push, and a failed workflow is re-run from its Actions
page, never worked round by a local publish. That workflow arrives with a
later change; until it is on `main`, nothing publishes this package. PyPI
accepts that workflow's publish only once the `uxid` project's settings on
PyPI name this repository and that workflow file as its trusted publisher, a
step in the PyPI console that is the operator's. Merging the prep follows
this file's merge row, and nothing else this file reserves for the operator
changes. A prep is cut only on a green full gate, which will include the
conformance corpus check.

This repository keeps no decision records (`docs/adr`). A release or gating
decision is recorded here, in the authority table and the Release preps
paragraph, and in the header of the workflow it governs; a change a user of
the API could notice is a changelog fragment (Conventions, below). The ID
format itself is not decided here: it is uxid-ex's wire-format spec,
`guides/wire-format.md` in https://github.com/riddler/uxid-ex, read at the
tag the vendored corpus names (`conformance/SOURCE.json`, once the corpus is
vendored). That this repository keeps no decision records was decided by the
conductor under a standing consent, 2026-10-20; a future API decision may
start a `docs/adr` directory.

Widening this section is a decision for the operator to make and record here.
An agent may draft the change; it does not adopt it.

## Non-interactive shell commands

`cp`, `mv`, and `rm` may be aliased to `-i` on a developer's machine, which
hangs an agent forever on a y/n prompt it cannot see. Always pass the
non-interactive form: `cp -f`, `mv -f`, `rm -f`, `rm -rf`, `cp -rf`. Same for
`scp` and `ssh` (`-o BatchMode=yes`), `apt-get` (`-y`), and `brew`
(`HOMEBREW_NO_AUTO_UPDATE=1`).

Also avoid `bd edit`, which opens `$EDITOR` and blocks. Use
`bd update <id> --title/--description/--notes/--design` instead.

## What this project is

`uxid` for Python. Version 1.0.0, the package this repository is being
rewritten into, makes prefixed, K-sortable, Stripe-style identifiers a person
can read, copy and route back to their resource, wire-compatible with the
Elixir reference `uxid` and checked against its conformance corpus. It covers
generation (random, deterministic and monotonic), decoding and the validity
checks; it has no runtime dependencies, takes its random bytes from
`secrets.token_bytes` by default, and runs on Python 3.11 or later. The 2020
code is gone from `main`; the tree is a `src/uxid` package that carries
`generate` (time-based ids, with an injectable byte source, and deterministic
ids from a string, hashed with `hashlib.sha256`), its refusal `UXIDError`,
`decode` (answering a `Decoded` or an `Invalid`, never raising on a malformed
string, with an injectable clock for compact times), the validity checks
`is_valid` and `is_deterministic`, the monotonic generator `Monotonic` (an
object the caller holds, its state and its `threading.Lock` inside the
instance, with an injectable byte source or `Draws`), `__version__` (read
from the installed package metadata) and a `py.typed` marker, with its tests
under `tests/` and `pyproject.toml`, `uv.lock` and `mise.toml` beside them.
CI and the vendored corpus arrive with later changes; until they do, the
sentences in this file about the 1.0.0 package, its corpus and its workflows
describe the target, not the current tree.

- **The package is `uxid`.** Version 1.0.0 replaces the 2020 0.0.1
  placeholder on PyPI under the same project name, and its import name is
  `uxid`: a new package in substance, not an upgrade path from 0.0.1.
- **The corpus is the arbiter.** `conformance/` will hold the corpus
  vendored from uxid-ex at a release tag, its tag, commit and hash recorded in
  `conformance/SOURCE.json`. The vendored files are never edited, and every
  case passes with no skip list: a case this port cannot pass is reported
  against uxid-ex with its evidence, never skipped or worked round here. An
  answer the corpus does not fix follows uxid-ex's spec at that tag.

`README.md` is the user reference; `CHANGELOG.md`
records each release.

## Build & Test

The gate tasks live in `mise.toml`; the tools they run (pytest, pytest-cov,
ruff, mypy) come from the `dev` dependency group in `pyproject.toml`, locked in
`uv.lock`, and run through `uv run`.

```bash
mise install            # the Python toolchain and the tools mise.toml pins
mise run gate:loop      # inner loop
mise run gate           # full gate
```

The full gate runs `ruff format --check`, `ruff check`, `mypy --strict` over
`src` and `tests`, the tests under pytest with coverage measured on lines and
branches (failing under 90 percent), and `uv build`; the conformance corpus
check joins it once the corpus is vendored.

### This repo's own gate rules

- The full gate is `mise run gate`; the inner loop is `mise run gate:loop`.
  Only the full command is the advancement gate: a `gate:loop` run, like a
  bare `pytest` or any other scoped run, is never evidence for a claim that
  the gate is green.
- **Never truncate the output.** No `| tail`, `| head`, `| grep`; truncating
  removes findings, not noise.
- **Never go green by weakening the check.** Not by lowering the coverage
  minimum, not by a `pytest.mark.skip` or `xfail` on a failing test, not by a
  `# noqa`, `# type: ignore` or `# pragma: no cover` comment or a new ignore
  in the ruff, mypy or coverage configuration to get past a finding, not by
  dropping or skipping a corpus case. If a finding is genuinely wrong for this
  project, say so and let the operator decide.
- Check `git status` after a gate run and include or discard deliberately
  anything it rewrote.
- A change touching no path the manifest (`.claude/wurk.json`) lists under
  `gate.build_paths` or `gate.also_gated_paths` has no gate to run and may
  commit on review of the diff alone. Those two lists are the one source for
  the exception: `src/`, `tests/`, `scripts/`, `conformance/` and `README.md`
  are what the gate checks, and `pyproject.toml`, `uv.lock`, `mise.toml`,
  `.python-version`, `.tool-versions` and the standalone ruff, mypy, pytest
  and coverage configuration files decide how it runs and what it resolves (a
  lock move alone changes the packages the gate runs against). A listed path
  need not exist yet.
- Documentation may point at the gate; it never enlarges it.

## Conventions

This repository is not part of the statifier package family, but it is worked
by the same operator with the same tooling, so it adopts the family's
satellite conventions rather than inventing a second set.

- **Domain-free examples.** The README, docstrings and test fixtures teach no
  example domain: examples use neutral resource prefixes such as `usr` and
  `cus`, and any address is a fictional `@example.com` one.
- **No runtime dependencies.** `[project.dependencies]` stays empty; adding a
  runtime dependency needs a bead of its own first. Development tools live in
  a development dependency group and `mise.toml`.
- **No global state.** No module-level mutable counter, cache or
  configuration. The monotonic generator is an object the caller holds, with
  its `threading.Lock` inside the instance.
- **The byte source is injectable; the default is the platform CSPRNG.** The
  default is `secrets.token_bytes`; never the `random` module or another
  seeded or non-cryptographic generator as a default. Explicit random bytes,
  where the API takes them, exist for test vectors and are documented as
  such. No test-only seam lives in the library source.
- **Python 3.11 or later** (`requires-python = ">=3.11"`, decided by the
  conductor under a standing consent, 2026-10-20).
- **The gate's bars**: 90 percent line coverage with branch measurement on,
  `mypy --strict`, and ruff for both lint and format (decided by the conductor
  under a standing consent, 2026-10-20).
- **Tests use pytest** (`def test_...` functions under `tests/`). Every public
  function, class and method carries a docstring, and the package ships a
  `py.typed` marker.
- Sabotage every new test that asserts library behavior: break the code it
  covers, confirm it goes red, revert, and note the mutation in one
  `# sabotage:` comment line directly above the test.
- Changelog: a change a user of the API could notice adds a fragment under
  `changelog.d/`, named for the bead (`changelog.d/uxpy-abc.md`), in the same
  request; tests, docs, tooling and gate changes take none. New version
  sections in `CHANGELOG.md` keep the file's own heading shape; existing
  history is not rewritten.
- Commit messages: simple present tense ("Adds ...", "Fixes ..."), body
  wrapped at ~72 chars explaining why. Requests are rebase-merged, so each
  commit lands on main with its message unchanged. No AI attribution
  trailers.
