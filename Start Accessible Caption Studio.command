#!/bin/zsh
set -e

cd "${0:A:h}"

if [[ -x /opt/local/bin/python3 ]]; then
  BOOTSTRAP_PYTHON=/opt/local/bin/python3
else
  BOOTSTRAP_PYTHON=$(command -v python3)
fi

if [[ ! -x .bootstrap/bin/uv ]]; then
  echo "Preparing the private local installer…"
  "$BOOTSTRAP_PYTHON" -m venv .bootstrap
  .bootstrap/bin/python -m pip install --upgrade pip uv
fi

export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
export UV_CACHE_DIR="$PWD/.runtime/cache"
export MPLCONFIGDIR="$PWD/storage/temporary/matplotlib"

if [[ ! -f .setup-complete-v6 || ! -x .studio-venv/bin/python ]]; then
  echo "Preparing Accessible Caption Studio. The first setup can take several minutes."
  .bootstrap/bin/uv python install 3.11 --install-dir "$UV_PYTHON_INSTALL_DIR" --no-bin
  .bootstrap/bin/uv venv --python 3.11 --clear .studio-venv
  .bootstrap/bin/uv pip install --python .studio-venv/bin/python -e ".[ml]"
  touch .setup-complete-v6
elif ! .studio-venv/bin/python -c "import yt_dlp_ejs" >/dev/null 2>&1; then
  echo "Updating YouTube download support. This should take only a moment."
  .bootstrap/bin/uv pip install --python .studio-venv/bin/python -e ".[ml]"
fi

exec .studio-venv/bin/accessible-caption-studio start
