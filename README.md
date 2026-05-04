# git-pychecker

Syntax-check Python files changed since the last Git commit — useful as a
quick pre-commit sanity gate.

Uses only `py_compile` from Python's standard library. Zero dependencies.

## Requirements

- Python 3.8+
- Git

## Usage

```sh
# Check all .py files changed since HEAD (modified + untracked)
./git-pycheck.py

# Explicit files or directories (recursive)
./git-pycheck.py foo.py bar/
./git-pycheck.py src/

# Style checks
./git-pycheck.py --syntax-only   # skip trailing whitespace / EOF newline checks
./git-pycheck.py -q              # errors only (suppress OK/WARN lines)
./git-pycheck.py --no-untracked  # skip new untracked files
./git-pycheck.py -v              # verbose (default, explicit)
```

Exit codes: `0` = all passed, `1` = at least one failure.
Style warnings never cause a non-zero exit.

## Checks performed

| Check | Type | What it catches |
|---|---|---|
| **Syntax** | error | `SyntaxError`, `IndentationError`, `TabError`, `from __future__` ordering |
| **Trailing whitespace** | warning | Lines ending with space or tab |
| **EOF newline** | warning | File missing final `\n` (POSIX convention) |

## How it works

When run inside a Git repo without arguments, it finds changed `.py` files via:

- `git diff HEAD --name-only` — modified tracked files
- `git ls-files --others --exclude-standard` — untracked files

Each file is compiled with `py_compile.compile(..., doraise=True)` to detect
syntax errors. No code is executed. Style checks read the file directly.

Outside a Git repo, explicit paths are required.
