"""Tests for scripts/release_guard.py, the checks that stop a release."""

import importlib.util
import os
import re
import subprocess
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release_guard.py"
ROOT_PYPROJECT = SCRIPT.parent.parent / "pyproject.toml"


def load() -> ModuleType:
    """The guard script, loaded as a module."""
    spec = importlib.util.spec_from_file_location("release_guard", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load()
GuardError: type[Exception] = guard.GuardError
main: Callable[..., int] = guard.main


def pyproject(tmp_path: Path, body: str) -> Path:
    """A pyproject.toml holding ``body``."""
    path = tmp_path / "pyproject.toml"
    path.write_text(body)
    return path


@pytest.fixture
def stated(tmp_path: Path) -> Path:
    """A pyproject.toml stating project ``uxid`` at version 1.2.3."""
    return pyproject(tmp_path, '[project]\nname = "uxid"\nversion = "1.2.3"\n')


# --- version


# sabotage: printing the version to standard error instead of standard output fails it
def test_a_tag_naming_the_stated_version_passes_and_prints_it(
    stated: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert guard.check_version("v1.2.3", stated) == "1.2.3"
    assert (
        main(
            [
                "release_guard.py",
                "version",
                "--tag",
                "v1.2.3",
                "--pyproject",
                str(stated),
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "1.2.3\n"


# sabotage: dropping the comparison with the stated version fails it
@pytest.mark.parametrize("tag", ["v1.2.4", "v1.2", "v1.2.3.0", "v1.2.3rc1", "v01.2.3"])
def test_a_tag_naming_another_version_refuses(
    stated: Path, tag: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(
        GuardError, match=re.escape("pyproject.toml at the tagged commit says 1.2.3")
    ):
        guard.check_version(tag, stated)
    assert (
        main(["release_guard.py", "version", "--tag", tag, "--pyproject", str(stated)])
        == 1
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith(f"::error::{tag} names {tag[1:]} but")
    assert "nothing is published" in captured.err


# sabotage: accepting a tag without its leading v fails it
@pytest.mark.parametrize("tag", ["1.2.3", "v", "", "V1.2.3"])
def test_a_tag_that_is_not_v_and_a_version_refuses(stated: Path, tag: str) -> None:
    with pytest.raises(GuardError, match="is not a version tag"):
        guard.check_version(tag, stated)


# sabotage: reading the version from a [tool] table instead of [project] fails it
@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ('[tool.x]\nversion = "1.2.3"\n', "has no \\[project\\] table"),
        ('[project]\nname = "uxid"\n', "states no project version"),
        ('[project]\nname = "uxid"\nversion = ""\n', "states no project version"),
        ('[project]\nname = "uxid"\nversion = 1\n', "states no project version"),
        ('[project]\nversion = "1.2.3"\n', "states no project name"),
        ("project = [\n", "cannot read"),
    ],
)
def test_a_pyproject_without_a_usable_version_refuses(
    tmp_path: Path, body: str, reason: str
) -> None:
    with pytest.raises(GuardError, match=reason):
        guard.check_version("v1.2.3", pyproject(tmp_path, body))


# sabotage: letting OSError escape from project() fails it
def test_a_missing_pyproject_refuses(tmp_path: Path) -> None:
    with pytest.raises(GuardError, match="cannot read"):
        guard.check_version("v1.2.3", tmp_path / "pyproject.toml")


# sabotage: defaulting --pyproject to the current directory's file fails it
def test_the_default_pyproject_is_the_repositorys(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, version = guard.project(ROOT_PYPROJECT)
    assert guard.PYPROJECT == ROOT_PYPROJECT
    assert main(["release_guard.py", "version", "--tag", f"v{version}"]) == 0
    assert capsys.readouterr().out == f"{version}\n"


# --- pypi


class Recorder:
    """A fetch that answers one status and records the URLs it was asked."""

    def __init__(self, status: int) -> None:
        """Answer ``status`` to every URL."""
        self.status = status
        self.urls: list[str] = []

    def __call__(self, url: str) -> int:
        """Record ``url`` and answer the status."""
        self.urls.append(url)
        return self.status


# sabotage: treating a 404 as "already on PyPI" fails it
def test_a_version_pypi_does_not_show_passes(
    stated: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fetch = Recorder(404)
    assert guard.check_pypi("v1.2.3", stated, fetch) == "uxid 1.2.3 is not on PyPI yet"
    assert fetch.urls == ["https://pypi.org/pypi/uxid/1.2.3/json"]
    argv = ["release_guard.py", "pypi", "--tag", "v1.2.3", "--pyproject", str(stated)]
    assert main(argv, fetch) == 0
    assert "uxid 1.2.3 is not on PyPI yet" in capsys.readouterr().err


# sabotage: passing on any status below 500 fails it
def test_a_version_pypi_already_shows_refuses(
    stated: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(GuardError, match="already on PyPI; reported, not published"):
        guard.check_pypi("v1.2.3", stated, Recorder(200))
    argv = ["release_guard.py", "pypi", "--tag", "v1.2.3", "--pyproject", str(stated)]
    assert main(argv, Recorder(200)) == 1
    assert capsys.readouterr().err == (
        "::error::uxid 1.2.3 is already on PyPI; reported, not published again\n"
    )


# sabotage: passing on every status other than 200 fails it
@pytest.mark.parametrize("status", [301, 403, 410, 429, 500, 503])
def test_any_other_pypi_answer_refuses(stated: Path, status: int) -> None:
    with pytest.raises(
        GuardError, match=re.escape(f"PyPI answered {status} for uxid 1.2.3")
    ):
        guard.check_pypi("v1.2.3", stated, Recorder(status))


# sabotage: building the URL from the tag text, v included, fails it
def test_the_pypi_url_names_the_projects_name_and_the_tags_version(
    tmp_path: Path,
) -> None:
    other = pyproject(tmp_path, '[project]\nname = "other-name"\nversion = "9.9.9"\n')
    fetch = Recorder(404)
    guard.check_pypi("v2.0.0", other, fetch)
    assert fetch.urls == ["https://pypi.org/pypi/other-name/2.0.0/json"]


def respond(handler: BaseHTTPRequestHandler) -> None:
    """Send the status the request path names (`/404` answers 404)."""
    handler.send_response(int(handler.path.strip("/")))
    handler.end_headers()


def quiet(handler: BaseHTTPRequestHandler, *args: object) -> None:
    """Keep the server from logging each request to the test output."""


# The handler class, built with type() because the method name the server
# calls, do_GET, is fixed by http.server.
Answer = type(
    "Answer", (BaseHTTPRequestHandler,), {"do_GET": respond, "log_message": quiet}
)


@pytest.fixture
def server() -> Iterator[str]:
    """The base URL of a local HTTP server that answers with the path's status."""
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Answer)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


# sabotage: answering 200 for every response, error statuses included, fails it
@pytest.mark.parametrize("status", [200, 404, 500])
def test_http_status_answers_the_status_the_server_sends(
    server: str, status: int
) -> None:
    assert guard.http_status(f"{server}/{status}") == status


# sabotage: letting URLError escape instead of raising GuardError fails it
def test_no_answer_refuses() -> None:
    with pytest.raises(GuardError, match="no answer from"):
        guard.http_status("http://127.0.0.1:9/")


# --- branch


def git(cwd: Path, *args: str) -> str:
    """Run git in ``cwd`` with a fixed identity, answering standard output."""
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Example",
        "GIT_AUTHOR_EMAIL": "dev@example.com",
        "GIT_COMMITTER_NAME": "Example",
        "GIT_COMMITTER_EMAIL": "dev@example.com",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True
    )
    return done.stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A repository whose ``origin/main`` holds two commits and a side branch.

    ``HEAD`` is on the first commit of ``main``; ``side`` holds one commit
    that is not on ``main``.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "--quiet", "--initial-branch=main")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", "first")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", "second")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "--quiet", "-b", "side", "HEAD~1")
    git(repo, "commit", "--quiet", "--allow-empty", "-m", "side")
    git(repo, "checkout", "--quiet", "--detach", "main~1")
    return repo


# sabotage: testing origin/main as an ancestor of HEAD (the reverse) fails it
def test_a_commit_on_the_default_branch_passes(checkout: Path) -> None:
    commit = git(checkout, "rev-parse", "HEAD")
    assert guard.check_branch("main", checkout) == f"{commit} is on main"
    git(checkout, "checkout", "--quiet", "--detach", "main")
    assert guard.check_branch("main", checkout).endswith(" is on main")


# sabotage: treating any merge-base exit status as success fails it
def test_a_commit_off_the_default_branch_refuses(checkout: Path) -> None:
    git(checkout, "checkout", "--quiet", "--detach", "side")
    commit = git(checkout, "rev-parse", "HEAD")
    with pytest.raises(
        GuardError, match=f"{commit} is not on main; nothing is published"
    ):
        guard.check_branch("main", checkout)


# sabotage: falling back to the local branch when origin/BRANCH is missing fails it
def test_a_default_branch_that_was_not_fetched_refuses(checkout: Path) -> None:
    with pytest.raises(GuardError, match="git cannot read origin/trunk"):
        guard.check_branch("trunk", checkout)
    with pytest.raises(GuardError, match="no default branch was named"):
        guard.check_branch("", checkout)


# sabotage: skipping the HEAD read's exit status check fails it
def test_a_directory_that_is_not_a_checkout_refuses(tmp_path: Path) -> None:
    with pytest.raises(GuardError, match="git cannot read HEAD"):
        guard.check_branch("main", tmp_path)


# sabotage: running the branch check in the script's directory, not the cwd, fails it
def test_the_branch_subcommand_reads_the_current_directory(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(checkout)
    assert main(["release_guard.py", "branch", "--default-branch", "main"]) == 0
    assert capsys.readouterr().err.endswith(" is on main\n")
    git(checkout, "checkout", "--quiet", "--detach", "side")
    assert main(["release_guard.py", "branch", "--default-branch", "main"]) == 1
    assert capsys.readouterr().err.startswith("::error::")


# sabotage: making the subcommand optional fails it
def test_a_check_must_be_named() -> None:
    with pytest.raises(SystemExit):
        main(["release_guard.py"])
