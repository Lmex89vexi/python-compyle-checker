#!/usr/bin/env python3
"""Syntax-check Python files changed since the last Git commit.

When run inside a Git repository, scans *all* changed Python files:

  - modified tracked files  (``git diff HEAD --name-only``)
  - new untracked files     (``git ls-files --others --exclude-standard``)

Works from any subdirectory inside the repository.

When no Git repository is found, or when one or more *paths* are given on
the command line, checks the specified files instead (directories are
scanned recursively for ``.py`` files).

By default, each file is checked for:

* **syntax errors**        — via ``py_compile`` (catches ``SyntaxError``,
  ``IndentationError``, ``TabError``, and ``from __future__`` ordering)
* **trailing whitespace**  — space/tab characters at end of line
* **missing EOF newline**  — file must end with ``\\n``

Use ``--syntax-only`` to skip the style checks.

Exit codes:
    0   all files passed (or nothing to check)
    1   one or more files have syntax errors
"""

import argparse
import logging
import py_compile
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("git-pycheck")


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _in_git_repo() -> bool:
    """Return ``True`` if CWD is inside a Git repository.

    Uses ``git rev-parse --git-dir`` which exits 0 when the working
    tree is inside a valid Git repository.  Returns ``False`` (rather
    than crashing) when ``git`` itself is not installed.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _git_root() -> Path:
    """Return the absolute path to the repository root.

    Calls ``git rev-parse --show-toplevel`` and resolves the result
    to an absolute :class:`Path`.  This is the anchor used by
    :func:`get_changed_py_files` to build absolute paths from the
    relative paths returned by Git.

    Raises
    ------
    subprocess.CalledProcessError
        If not in a Git repository.
    FileNotFoundError
        If ``git`` is not installed.
    """
    raw = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(raw.stdout.strip())


def get_changed_py_files(*, include_untracked: bool = True) -> list[Path]:
    """Return sorted list of changed .py files still present on disk.

    Discovers Python files via two git commands:

    * ``git diff HEAD --name-only``                 — modified tracked files
    * ``git ls-files --others --exclude-standard``  — new untracked files

    Every returned path is absolute and resolved against the repository
    root, so the function works correctly from *any* working directory.

    Files that no longer exist (e.g. deletions) are silently skipped
    since they cannot be checked.

    Parameters
    ----------
    include_untracked
        When *True* (default), also include untracked ``.py`` files.

    Returns
    -------
    list[Path]
        Existing ``.py`` files with changes since HEAD, sorted.
    """
    root = _git_root()
    raw = subprocess.run(
        ["git", "diff", "HEAD", "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    )
    changed: set[str] = {f for f in raw.stdout.strip().splitlines() if f.endswith(".py")}

    if include_untracked:
        raw = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--full-name"],
            capture_output=True,
            text=True,
            check=True,
        )
        changed.update(f for f in raw.stdout.strip().splitlines() if f.endswith(".py"))

    existing = sorted(root / f for f in changed if (root / f).is_file())
    skipped = len(changed) - len(existing)
    if skipped:
        log.info("Skipped %d deleted .py file(s)", skipped)
    return existing


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def collect_py_files(paths: list[Path]) -> list[Path]:
    """Collect and return all ``.py`` files from *paths*.

    Directories are walked recursively; plain files are kept if they
    end with ``.py``.  Duplicates are removed so a file listed both
    directly and via a directory argument is checked only once.

    Returns
    -------
    list[Path]
        Sorted unique existing Python files.
    """
    files: list[Path] = []
    for p in paths:
        p = p.resolve()
        if p.is_dir():
            files.extend(sorted(p.rglob("*.py")))
        elif p.is_file() and p.suffix == ".py":
            files.append(p)
    return sorted(set(files))


# ---------------------------------------------------------------------------
# Style checks  (optional, controlled by --syntax-only)
# ---------------------------------------------------------------------------


def _check_trailing_whitespace(filepath: Path) -> list[str]:
    """Return warning messages for lines ending with space or tab.

    Reads the file line by line and records every line (except blank
    lines) that ends with an unquoted space (`` ``) or tab (``\\t``)
    character.

    Trailing whitespace is cosmetic but widely considered a code smell:
    it creates noisy diffs, can be flagged by linters like
    ``flake8`` (W291/W293), and many editors strip it automatically.

    Returns
    -------
    list[str]
        Human-readable warnings, one per offending line.
        Empty when the file is clean.
    """
    warnings: list[str] = []
    try:
        with open(filepath, encoding="utf-8", newline="") as f:
            for lineno, line in enumerate(f, start=1):
                content = line.rstrip("\n\r")
                if content and content.endswith((" ", "\t")):
                    warnings.append(f"line {lineno}: trailing whitespace")
    except Exception as exc:
        warnings.append(f"could not read file: {exc}")
    return warnings


def _check_eof_newline(filepath: Path) -> list[str]:
    """Return warning if file does not end with a newline (``\\n``).

    POSIX convention and many toolchains (``diff``, ``git diff``,
    compilers) expect every text file to end with a newline character.
    A missing final ``\\n`` can produce spurious ``No newline at end
    of file`` diffs and break tools that assume the convention.

    Returns
    -------
    list[str]
        A single-element list with a warning message, or empty if
        the file satisfies the convention.  Empty files are skipped.
    """
    try:
        with open(filepath, "rb") as f:
            f.seek(0, 2)
            if f.tell() == 0:
                return []
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                return ["missing trailing newline"]
    except Exception as exc:
        return [f"could not read file: {exc}"]
    return []


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def check_file(filepath: Path, *, check_style: bool = True) -> tuple[bool, list[str]]:
    """Check a single Python file for syntax and style issues.

    Runs ``py_compile`` to detect fatal syntax errors, then optionally
    checks for common style problems (trailing whitespace, missing EOF
    newline).  Output is written to the log immediately per file so
    the user sees incremental progress.

    Parameters
    ----------
    filepath
        Path to the ``.py`` file to check.
    check_style
        When *True* (default), also run style checks.

    Returns
    -------
    tuple[bool, list[str]]
        ``(syntax_ok, style_warnings)`` where *syntax_ok* is ``True``
        when the file passes ``py_compile``, and *style_warnings*
        lists any non-fatal policy violations found.
    """
    style_warnings: list[str] = []

    # Syntax — the only check that produces a hard failure
    try:
        py_compile.compile(str(filepath), doraise=True)
        syntax_ok = True
    except py_compile.PyCompileError as exc:
        log.error("FAIL   %s — %s", filepath, exc)
        syntax_ok = False

    # Style — warnings only, never cause a non-zero exit
    if check_style:
        style_warnings.extend(_check_trailing_whitespace(filepath))
        style_warnings.extend(_check_eof_newline(filepath))
        for w in style_warnings:
            log.warning("WARN   %s — %s", filepath, w)

    if syntax_ok and not style_warnings:
        log.info("OK     %s", filepath)

    return syntax_ok, style_warnings


def _run_checks(files: list[Path], *, check_style: bool = True) -> int:
    """Check all *files*, log summary, return exit code.

    Iterates over *files*, runs :func:`check_file` on each, aggregates
    pass/fail/warning counts, and prints a one-line summary.  Only
    syntax errors count as failures — style warnings do not affect the
    exit code.

    Returns
    -------
    int
        ``0`` when all files pass syntax, ``1`` if any has a syntax error.
    """
    if not files:
        log.info("No .py files to check.")
        return 0

    checks = ["syntax"]
    if check_style:
        checks.append("style (trailing-whitespace, eof-newline)")
    log.info("Checking %d file(s) [%s] …", len(files), ", ".join(checks))

    results = [check_file(f, check_style=check_style) for f in files]
    passed = sum(1 for ok, _ in results if ok)
    failed = len(results) - passed
    total_warnings = sum(len(w) for _, w in results)

    if failed:
        log.warning("DONE — %d passed, %d FAILED, %d warnings", passed, failed, total_warnings)
    elif total_warnings:
        log.info("DONE — %d passed, 0 failed, %d warnings", passed, total_warnings)
    else:
        log.info("DONE — %d passed, 0 failed", passed)

    return 1 if failed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser.

    Adds all supported CLI flags and positional arguments to an
    :class:`argparse.ArgumentParser`.  This function is separated
    from :func:`main` so it can be tested in isolation or extended
    by callers who want to add subcommands.
    """
    parser = argparse.ArgumentParser(
        description="Syntax-check Python files changed since HEAD.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="path",
        help="One or more .py files or directories (recursive). "
             "When omitted, scans git-tracked changes.",
    )
    parser.add_argument(
        "--syntax-only",
        action="store_true",
        help="Skip style checks (trailing whitespace, EOF newline)",
    )
    parser.add_argument(
        "--no-untracked",
        action="store_false",
        dest="untracked",
        help="Exclude untracked .py files (included by default)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Only show failures and summary (suppress OK/WARN lines)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show every checked file (this is the default)",
    )
    parser.set_defaults(verbose=True)
    return parser


def setup_logging(*, quiet: bool, verbose: bool) -> None:
    """Configure root logger for the script.

    Controls what gets written to stderr:

    * **quiet** — only ``WARNING`` and above (failures, summary)
    * **verbose** — ``INFO`` and above (the default, shows ``OK`` lines)
    * **neither** — falls back to ``WARNING`` (same as quiet)

    The format is ``%(message)s`` — bare log text with no extra fields.
    """
    level = logging.WARNING if quiet else (logging.INFO if verbose else logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point: discover changed files, run checks, report result.

    Two modes:

    1. **Explicit paths** — one or more files/directories on the CLI.
    2. **Git mode** (default) — discovers changed ``.py`` files since
       HEAD via ``git diff`` and ``git ls-files``.

    Logging is configured early so all subsequent output, including
    discovery messages, respects the ``--quiet`` / ``--verbose`` flags.

    Returns
    -------
    int
        ``0`` when everything passes, ``1`` on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(quiet=args.quiet, verbose=args.verbose)
    check_style = not args.syntax_only

    if args.paths:
        files = collect_py_files([Path(p) for p in args.paths])
        return _run_checks(files, check_style=check_style)

    if not _in_git_repo():
        log.error(
            "Not in a Git repository. "
            "Pass one or more files or directories to check."
        )
        return 1

    try:
        files = get_changed_py_files(include_untracked=args.untracked)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        log.error("Git invocation failed: %s", exc)
        return 1

    return _run_checks(files, check_style=check_style)


if __name__ == "__main__":
    sys.exit(main())
