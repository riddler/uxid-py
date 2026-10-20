"""The README's Python examples run, and every public name has a docstring."""

import inspect
import re
from pathlib import Path

import uxid

_README = Path(__file__).resolve().parent.parent / "README.md"
_FENCE = re.compile(r"^```python\n(.*?)^```$", re.DOTALL | re.MULTILINE)


# sabotage: change an expected value in a README python block; this goes red.
def test_every_readme_python_block_runs() -> None:
    blocks = _FENCE.findall(_README.read_text(encoding="utf-8"))
    assert blocks
    for block in blocks:
        exec(compile(block, str(_README), "exec"), {})


# sabotage: delete the docstring of one public function; this goes red.
def test_every_public_function_class_and_method_has_a_docstring() -> None:
    # The type aliases (Size, Case, ByteSource, ErrorCode, InvalidReason) carry
    # their documentation as a string beside the assignment, which a running
    # program cannot read back.
    checked = 0
    for name in uxid.__all__:
        obj = getattr(uxid, name)
        if not (inspect.isfunction(obj) or inspect.isclass(obj)):
            continue
        assert inspect.getdoc(obj), name
        checked += 1
        if inspect.isclass(obj):
            for member, value in vars(obj).items():
                if member.startswith("_") and member != "__init__":
                    continue
                if inspect.isfunction(value) and value.__qualname__.startswith(name):
                    assert inspect.getdoc(value), f"{name}.{member}"
                    checked += 1
    assert checked >= 8
