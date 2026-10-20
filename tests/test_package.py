"""Tests for the package itself."""

import re
from importlib.metadata import version

import uxid


# sabotage: setting __version__ to a constant other than the metadata version fails it
def test_version_matches_the_installed_metadata() -> None:
    assert uxid.__version__ == version("uxid")
    assert re.fullmatch(r"\d+\.\d+\.\d+", uxid.__version__)
