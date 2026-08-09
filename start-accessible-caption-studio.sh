#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

if command -v python3 >/dev/null 2>&1; then
  BOOTSTRAP_PYTHON=$(command -v python3)
elif command -v python >/dev/null 2>&1; then
  BOOTSTRAP_PYTHON=$(command -v python)
else
  echo "Python 3 is required to prepare Accessible Caption Studio."
  exit 1
fi

if [ ! -x .bootstrap/bin/uv ]; then
  echo "Preparing the private local installer..."
  "$BOOTSTRAP_PYTHON" -m venv .bootstrap
  .bootstrap/bin/python -m pip install --upgrade pip uv
fi

export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
export UV_CACHE_DIR="$PWD/.runtime/cache"
export MPLCONFIGDIR="$PWD/storage/temporary/matplotlib"

if [ ! -f .setup-complete-v5 ] || [ ! -x .studio-venv/bin/python ]; then
  echo "Preparing Accessible Caption Studio. The first setup can take several minutes."
  .bootstrap/bin/uv python install 3.11 --install-dir "$UV_PYTHON_INSTALL_DIR" --no-bin
  .bootstrap/bin/uv venv --python 3.11 --clear .studio-venv
  .bootstrap/bin/uv pip install --python .studio-venv/bin/python -e ".[ml]"
  touch .setup-complete-v5
fi

exec .studio-venv/bin/accessible-caption-studio start
