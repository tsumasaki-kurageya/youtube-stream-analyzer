#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
env_file="${YSA_ENV_FILE:-$repo_root/.env}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file. Run 'cp .env.example .env' first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$env_file"
set +a

exec "$@"
