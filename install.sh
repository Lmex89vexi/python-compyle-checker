#!/usr/bin/env bash
# git-pychecker install/uninstall script
# Symlinks git-pycheck.py into a PATH directory as `git-pycheck`.

set -euo pipefail

# Resolve the script's own directory so the symlink target is correct
# regardless of where the user invokes this script from.
name="git-pycheck"
src="$(dirname "$(readlink -f "$0")")/$name.py"

echo "[git-pycheck] Source: $src"

usage() {
    echo "Usage: $0 {install|uninstall} [--user]"
    echo ""
    echo "  install      Symlink $name.py into PATH"
    echo "  uninstall    Remove the symlink"
    echo "  --user       Target ~/.local/bin (default: /usr/local/bin)"
    exit 1
}

# Require at least the action argument
[[ $# -ge 1 ]] || usage
action="$1"; shift
echo "[git-pycheck] Action: $action"

# --user installs to ~/.local/bin instead of /usr/local/bin
if [[ "${1:-}" == "--user" ]]; then
    target_dir="$HOME/.local/bin"
    echo "[git-pycheck] Mode: user-local install"
    shift
else
    target_dir="/usr/local/bin"
    echo "[git-pycheck] Mode: system-wide install"
fi

echo "[git-pycheck] Target directory: $target_dir"

target="$target_dir/$name"

case "$action" in
    install)
        echo "[git-pycheck] Ensuring target directory exists ..."
        mkdir -p "$target_dir"
        echo "[git-pycheck] Creating symlink ..."
        ln -sfv "$src" "$target"
        echo "[git-pycheck] Done — installed $target -> $src"
        ;;
    uninstall)
        if [[ -L "$target" ]]; then
            echo "[git-pycheck] Removing symlink $target ..."
            rm -v "$target"
            echo "[git-pycheck] Done — uninstalled $target"
        else
            echo "[git-pycheck] Nothing to uninstall — no symlink at $target"
        fi
        ;;
    *)
        usage
        ;;
esac
