#!/usr/bin/env bash
set -euo pipefail

required_files=(
  "AGENTS.md"
  ".agents/skills/.gitkeep"
  ".devcontainer/devcontainer.json"
  ".devcontainer/Dockerfile"
  ".env.example"
  ".graphifyignore"
  ".codex/skills/graphify/.graphify_version"
  ".codex/skills/graphify/SKILL.md"
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

expected_graphify_version="0.9.30"
actual_graphify_version="$(tr -d '\r\n' < .codex/skills/graphify/.graphify_version)"

if [[ "$actual_graphify_version" != "$expected_graphify_version" ]]; then
  echo "Unexpected Graphify skill version: $actual_graphify_version (expected $expected_graphify_version)" >&2
  exit 1
fi

if find . -type f \( -name '*.md' -o -name '*.yml' -o -name '*.yaml' -o -name '*.json' \) -print0 \
  | xargs -0 grep -n $'\r' >/tmp/youtube-stream-analyzer-crlf.txt 2>/dev/null; then
  echo "CRLF characters detected:" >&2
  cat /tmp/youtube-stream-analyzer-crlf.txt >&2
  exit 1
fi

echo "Repository structure checks passed"
