#!/usr/bin/env python3
"""Syntax-check Python files changed since the last Git commit.

When run inside a Git repository, scans *all* changed Python files:
  - modified tracked files  (``git diff HEAD --name-only``)
  - new untracked files     (``git ls-files --others --exclude-standard``)

Works from any subdirectory inside the repository.

When no Git repository is found, or when one or more *paths* are given on
the command line, checks the specified files instead (directories are
scanned recursively for ``.py`` files).

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
    """Return ``True`` if CWD is inside a Git repository."""
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

    Files that no longer exist (e.g. deletions) are silently skipped.

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
    end with ``.py``.  Every returned path is a real, existing file.
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
# Core logic
# ---------------------------------------------------------------------------


def check_file(filepath: Path) -> bool:
    """Run ``py_compile`` on *filepath* and return ``True`` on success."""
    try:
        py_compile.compile(str(filepath), doraise=True)
        log.info("OK     %s", filepath)
        return True
    except py_compile.PyCompileError as exc:
        log.error("FAIL   %s — %s", filepath, exc)
        return False


def _run_checks(files: list[Path]) -> int:
    """Check all *files*, log summary, return exit code."""
    if not files:
        log.info("No .py files to check.")
        return 0

    log.info("Checking %d file(s) …", len(files))
    results = [check_file(f) for f in files]
    passed = sum(results)
    failed = len(results) - passed

    if failed:
        log.warning("DONE — %d passed, %d FAILED", passed, failed)
    else:
        log.info("DONE — %d passed, 0 failed", passed)

    return 1 if failed else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser."""
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
        "--no-untracked",
        action="store_false",
        dest="untracked",
        help="Exclude untracked .py files (included by default)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress all output except errors",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show every checked file (default behaviour)",
    )
    parser.set_defaults(verbose=True)
    return parser


def setup_logging(*, quiet: bool, verbose: bool) -> None:
    """Configure root logger for the script.

    Parameters
    ----------
    quiet
        Only warnings and above are emitted.
    verbose
        Info-level messages are shown (this is the default).
    """
    level = logging.WARNING if quiet else (logging.INFO if verbose else logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point: discover changed files, compile each, report result.

    Returns
    -------
    int
        ``0`` when everything passes, ``1`` on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(quiet=args.quiet, verbose=args.verbose)

    # -- explicit paths ---------------------------------------------------
    if args.paths:
        files = collect_py_files([Path(p) for p in args.paths])
        return _run_checks(files)

    # -- git mode ----------------------------------------------------------
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

    return _run_checks(files)


if __name__ == "__main__":
    sys.exit(main())
