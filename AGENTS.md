# git-pychecker

Single-file Python CLI that syntax-checks `.py` files changed since HEAD
(via `py_compile` from stdlib — zero third-party dependencies).

## Commands

```sh
# Check files changed since HEAD (git diff HEAD + untracked)
./git-pycheck.py

# Explicit files or directories (recursive)
./git-pycheck.py foo.py bar/
./git-pycheck.py src/

# Flags
./git-pycheck.py -q              # errors only
./git-pycheck.py --no-untracked  # skip new untracked files
```

Exit: `0` all passed, `1` at least one failure.

## Repo structure

```
git-pycheck.py   — entry point (also the only source file)
```

## State

- **No commits exist yet** — first `git add` + `git commit` needed.
- **No tests, no CI, no linter/formatter config**.
- Remote: `git@github.com:Lmex89vexi/python-compyle-checker.git` (differs from local dir name).
