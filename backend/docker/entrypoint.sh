#!/usr/bin/env bash
set -euo pipefail

# If the venv folder isn't present, install deps.
if [ ! -d "/project/.venv" ] || [ ! -x "/project/.venv/bin/python" ]; then
  echo ">> No venv detected; running 'pdm install --prod --no-editable'..."
  python -m venv /project/.venv
  export VIRTUAL_ENV=/project/.venv
  export PATH="/project/.venv/bin:$PATH"
  pdm use -f /project/.venv
  pdm install --prod --no-editable
fi

exec "$@"
