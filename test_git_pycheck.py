#!/usr/bin/env python3
"""Manual test suite for git-pychecker.

Runs the checker against sample files with known issues and verifies
exit codes and output contain the expected markers.

Usage:
    ./test_git_pycheck.py                    # run all tests
    ./test_git_pycheck.py test_clean         # run a single test
    ./test_git_pycheck.py -v                 # show checker output too
"""

import subprocess
import sys
import tempfile
from pathlib import Path

CHECKER = Path(__file__).resolve().parent / "git-pycheck.py"
VERBOSE = "-v" in sys.argv[1:]

passed = 0
failed = 0


def run(*args: str, expect: int = 0, markers: list[str] | None = None) -> None:
    global passed, failed
    name = sys._getframe(1).f_code.co_name

    result = subprocess.run(
        [sys.executable, str(CHECKER)] + list(args),
        capture_output=True,
        text=True,
    )
    ok = result.returncode == expect

    if markers:
        for m in markers:
            if m not in result.stderr:
                ok = False

    status = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1

    print(f"  [{status}] {name}")
    if not ok or VERBOSE:
        for line in result.stderr.splitlines():
            print(f"         {line}")
    if not ok:
        print(f"         (expected exit {expect}, got {result.returncode})")


def test_clean() -> None:
    """File with valid syntax and no style issues."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1\n")
        f.write("y = 2\n")
    try:
        run(f.name)
    finally:
        Path(f.name).unlink()


def test_syntax_error() -> None:
    """File with invalid syntax."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x =\n")
    try:
        run(f.name, expect=1, markers=["FAIL", "SyntaxError"])
    finally:
        Path(f.name).unlink()


def test_trailing_whitespace() -> None:
    """File with trailing spaces."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1   \n")
        f.write("y = 2\n")
    try:
        run(f.name, markers=["1 passed, 0 failed, 1 warnings"])
    finally:
        Path(f.name).unlink()


def test_trailing_whitespace_w_flag() -> None:
    """Trailing whitespace shown with -w flag."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1   \n")
    try:
        run("-w", f.name, markers=["WARN", "trailing whitespace"])
    finally:
        Path(f.name).unlink()


def test_missing_eof_newline() -> None:
    """File missing trailing newline."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1")
    try:
        run(f.name, markers=["1 passed, 0 failed, 1 warnings"])
    finally:
        Path(f.name).unlink()


def test_missing_eof_newline_w_flag() -> None:
    """Missing EOF newline shown with -w flag."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1")
    try:
        run("-w", f.name, markers=["WARN", "missing trailing newline"])
    finally:
        Path(f.name).unlink()


def test_syntax_only_skips_style() -> None:
    """--syntax-only suppresses style warnings."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1   \n")
    try:
        run("--syntax-only", f.name, markers=["[syntax]"])
    finally:
        Path(f.name).unlink()


def test_quiet_suppresses_ok() -> None:
    """-q hides OK lines but still shows results."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1\n")
    try:
        result = subprocess.run(
            [sys.executable, str(CHECKER), "-q", f.name],
            capture_output=True, text=True,
        )
        ok = "OK" not in result.stderr
        ok = ok and result.returncode == 0
        global passed, failed
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  [{'PASS' if ok else 'FAIL'}] test_quiet_suppresses_ok")
        if not ok or VERBOSE:
            for line in result.stderr.splitlines():
                print(f"         {line}")
    finally:
        Path(f.name).unlink()


def test_mixed_issues() -> None:
    """File with syntax error + trailing whitespace + missing newline."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("x = 1   ")
    try:
        run("-w", f.name,
            markers=["WARN", "trailing whitespace", "missing trailing newline"])
    finally:
        Path(f.name).unlink()


def test_directory_scan() -> None:
    """Recursive scan of a directory."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "a.py").write_text("x = 1\n")
        (d / "sub").mkdir()
        (d / "sub" / "b.py").write_text("y = 2\n")
        run(str(d), markers=["2 passed, 0 failed"])


def test_good_imports() -> None:
    """Valid imports pass with --check-imports."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("import os\nimport sys\nfrom pathlib import Path\n")
    try:
        run("--check-imports", f.name)
    finally:
        Path(f.name).unlink()


def test_bad_import() -> None:
    """Missing import fails with --check-imports."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("import doesnt_exist_xyz\n")
    try:
        run("--check-imports", f.name, expect=1, markers=["FAIL", "cannot resolve import"])
    finally:
        Path(f.name).unlink()


def test_bad_from_import() -> None:
    """Missing from-import fails with --check-imports."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("from doesnt_exist_foo import bar\n")
    try:
        run("--check-imports", f.name, expect=1, markers=["FAIL", "cannot resolve import"])
    finally:
        Path(f.name).unlink()


def test_import_not_enabled() -> None:
    """Without --check-imports, missing imports are ignored."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("import doesnt_exist_xyz\n")
    try:
        run(f.name, markers=["OK"])
    finally:
        Path(f.name).unlink()


def test_project_local_import() -> None:
    """Local package imports resolve with --check-imports."""
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "mypkg").mkdir()
        (d / "mypkg" / "__init__.py").write_text("x = 1\n")
        target = d / "test_local.py"
        target.write_text("from mypkg import x\nimport os\n")
        run("--check-imports", str(target))


if __name__ == "__main__":
    tests = [v for k, v in globals().items()
             if k.startswith("test_") and callable(v)]

    # Filter to specific test if given as positional argument
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        name = sys.argv[1]
        tests = [t for t in tests if t.__name__ == name]

    print(f"Running {len(tests)} test(s) …\n")
    for t in tests:
        t()

    print(f"\n{'=' * 40}")
    print(f"  {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
