#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -x .venv/bin/python ]]; then
  studio_python=.venv/bin/python
elif command -v python3 >/dev/null 2>&1; then
  studio_python=python3
elif command -v python >/dev/null 2>&1; then
  studio_python=python
else
  echo 'Python 3.10 or newer is required: https://www.python.org/downloads/' >&2
  exit 1
fi
"$studio_python" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or newer is required"'
exec "$studio_python" app.py "$@"
