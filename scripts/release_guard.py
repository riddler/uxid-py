"""The checks the release workflow runs before it builds or publishes anything.

``.github/workflows/release.yml`` runs on the push of a version tag and calls
this script, with the runner's own Python and nothing else installed, for the
three refusals that stop a release:

- ``branch``: the tagged commit (``HEAD``) is on the default branch, read as
  the remote-tracking ref ``origin/BRANCH`` the workflow fetched;
- ``version``: the tag is ``v`` followed by the version ``pyproject.toml``
  states in its ``[project]`` table, exactly; on success the version is
  printed, alone, on standard output;
- ``pypi``: PyPI's JSON API does not already show that version of the
  project ``pyproject.toml`` names. A 404 is "not there yet"; a 200 means the
  version is already on PyPI, which is reported and stops the run, because a
  version PyPI has seen can never be uploaded again; any other answer, or no
  answer, stops the run too.

    python3 scripts/release_guard.py branch --default-branch BRANCH
    python3 scripts/release_guard.py version --tag TAG [--pyproject PATH]
    python3 scripts/release_guard.py pypi --tag TAG [--pyproject PATH]

Each subcommand exits 0 when its check holds and 1, with one ``::error::``
line (a GitHub Actions error annotation) on standard error, when it does not.
The script uses the standard library only (Python 3.11 or later, for
``tomllib``), so it runs before any toolchain is installed.
"""

import argparse
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

# PyPI's JSON API: one version of one project.
PYPI_VERSION_URL = "https://pypi.org/pypi/{name}/{version}/json"

USER_AGENT = "uxid-py release workflow (https://github.com/riddler/uxid-py)"


class GuardError(Exception):
    """A check that refuses the release, with the reason as its message."""


def project(pyproject: Path) -> tuple[str, str]:
    """The ``name`` and ``version`` from ``pyproject``'s ``[project]`` table.

    Raises ``GuardError`` when the file cannot be read or either field is
    missing or not a non-empty string.
    """
    try:
        with pyproject.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise GuardError(f"cannot read {pyproject}: {error}") from error
    table = data.get("project")
    if not isinstance(table, dict):
        raise GuardError(f"{pyproject} has no [project] table")
    fields = []
    for key in ("name", "version"):
        value = table.get(key)
        if not isinstance(value, str) or not value:
            raise GuardError(f"{pyproject} states no project {key}")
        fields.append(value)
    return fields[0], fields[1]


def tag_version(tag: str) -> str:
    """The version a tag names: the tag without its leading ``v``.

    Raises ``GuardError`` when the tag does not start with ``v`` or names
    nothing after it.
    """
    if not tag.startswith("v") or len(tag) == 1:
        raise GuardError(f"{tag!r} is not a version tag (v followed by a version)")
    return tag[1:]


def check_version(tag: str, pyproject: Path) -> str:
    """The version, when ``tag`` names exactly the version ``pyproject`` states.

    Raises ``GuardError`` otherwise.
    """
    wanted = tag_version(tag)
    _, stated = project(pyproject)
    if wanted != stated:
        raise GuardError(
            f"{tag} names {wanted} but pyproject.toml at the tagged commit says"
            f" {stated}; nothing is published"
        )
    return stated


def http_status(url: str) -> int:
    """The HTTP status a GET of ``url`` answers with.

    Raises ``GuardError`` when no answer arrives (a network error or a
    timeout).
    """
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status: int = response.status
            return status
    except urllib.error.HTTPError as error:
        return error.code
    except (urllib.error.URLError, TimeoutError) as error:
        raise GuardError(
            f"no answer from {url}: {error}; nothing is published"
        ) from error


def check_pypi(
    tag: str, pyproject: Path, fetch: Callable[[str], int] = http_status
) -> str:
    """A report line, when PyPI does not show the version ``tag`` names.

    The project name is ``pyproject``'s, so the version checked is the
    version of the package the release would publish. ``fetch`` answers the
    HTTP status of a URL. Raises ``GuardError`` when PyPI shows the version
    (200) or answers anything other than 404.
    """
    version = tag_version(tag)
    name, _ = project(pyproject)
    status = fetch(PYPI_VERSION_URL.format(name=name, version=version))
    if status == 404:
        return f"{name} {version} is not on PyPI yet"
    if status == 200:
        raise GuardError(
            f"{name} {version} is already on PyPI; reported, not published again"
        )
    raise GuardError(
        f"PyPI answered {status} for {name} {version}; nothing is published"
    )


def check_branch(default_branch: str, cwd: Path | None = None) -> str:
    """A report line, when ``HEAD`` is on ``origin/default_branch``.

    ``cwd`` is the checkout to ask (the current directory when ``None``).
    Raises ``GuardError`` when ``HEAD`` is not an ancestor of that ref, or
    when git cannot answer.
    """
    if not default_branch:
        raise GuardError("no default branch was named")
    ref = f"origin/{default_branch}"

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
        )

    head = git("rev-parse", "--verify", "HEAD^{commit}")
    if head.returncode != 0:
        raise GuardError(f"git cannot read HEAD: {head.stderr.strip()}")
    commit = head.stdout.strip()
    known = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    if known.returncode != 0:
        raise GuardError(f"git cannot read {ref}: {known.stderr.strip()}")
    ancestor = git("merge-base", "--is-ancestor", commit, ref)
    if ancestor.returncode == 1:
        raise GuardError(f"{commit} is not on {default_branch}; nothing is published")
    if ancestor.returncode != 0:
        raise GuardError(
            f"git cannot compare {commit} with {ref}: {ancestor.stderr.strip()}"
        )
    return f"{commit} is on {default_branch}"


def parser() -> argparse.ArgumentParser:
    """The command line: one subcommand per check."""
    top = argparse.ArgumentParser(
        prog="release_guard.py",
        description="The checks that stop a release before it is built.",
    )
    checks = top.add_subparsers(dest="check", required=True)
    branch = checks.add_parser("branch", help="HEAD is on the default branch")
    branch.add_argument("--default-branch", required=True)
    for name, text in (
        ("version", "the tag names pyproject.toml's version"),
        ("pypi", "PyPI does not already show the version"),
    ):
        sub = checks.add_parser(name, help=text)
        sub.add_argument("--tag", required=True)
        sub.add_argument("--pyproject", type=Path, default=PYPROJECT)
    return top


def main(argv: list[str], fetch: Callable[[str], int] = http_status) -> int:
    """Run the check ``argv`` names (``argv[0]`` is the program); 0 or 1.

    0 when the check holds and 1, with an ``::error::`` line on standard
    error, when it refuses.
    """
    args = parser().parse_args(argv[1:])
    try:
        if args.check == "branch":
            print(check_branch(args.default_branch), file=sys.stderr)
        elif args.check == "version":
            print(check_version(args.tag, args.pyproject))
        else:
            print(check_pypi(args.tag, args.pyproject, fetch), file=sys.stderr)
    except GuardError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
