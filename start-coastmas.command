#!/bin/bash
# Double-click on macOS, or execute this file from any working directory.
set -eu
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.docker/bin:$PATH"
COASTMAS_ROOT="$(cd -- "$(dirname -- "$0")" && pwd -P)"
cd "$COASTMAS_ROOT"
if [ ! -x "$COASTMAS_ROOT/.venv/bin/python" ]; then
  echo "缺少 CoastMAS Python 环境，请先按 docs/web-runtime.md 配置。" >&2
  exit 1
fi
exec "$COASTMAS_ROOT/.venv/bin/python" "$COASTMAS_ROOT/scripts/start_local.py"
