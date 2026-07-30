#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "AGENTS.md"
  ".agents/skills/.gitkeep"
  ".devcontainer/devcontainer.json"
  ".devcontainer/Dockerfile"
  ".env.example"
  "docs/repository-structure.md"
  "docs/development/configuration.md"
  "docs/development/local-development.md"
  "docs/decisions/README.md"
  "docs/decisions/template.md"
  "docs/implementation-plans/README.md"
  "docs/implementation-plans/template.md"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required file: $file" >&2
    exit 1
  fi
done

if find . -type f \( -name '*.md' -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' \) -print0 \
  | xargs -0 grep -n $'\r' >/tmp/youtube-stream-analyzer-crlf.txt 2>/dev/null; then
  echo "CRLF characters detected:" >&2
  cat /tmp/youtube-stream-analyzer-crlf.txt >&2
  exit 1
fi

echo "Repository structure checks passed"
