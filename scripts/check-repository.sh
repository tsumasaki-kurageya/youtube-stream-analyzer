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
  "compose.yaml"
  "apps/api/go.mod"
  "apps/api/cmd/api/main.go"
  "apps/web/package.json"
  "apps/web/tsconfig.json"
  "apps/web/vite.config.ts"
  "apps/web/index.html"
  "apps/web/src/main.tsx"
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

# Do not fail a focused change because of pre-existing line endings elsewhere in
# the repository. Validate text files changed by the current commit/PR only.
if git rev-parse --verify HEAD^ >/dev/null 2>&1; then
  mapfile -d '' changed_text_files < <(
    git diff --name-only -z --diff-filter=ACM HEAD^ HEAD -- \
      '*.md' '*.yml' '*.yaml' '*.json' '*.ts' '*.tsx' '*.go'
  )
else
  changed_text_files=()
fi

crlf_files=()
for file in "${changed_text_files[@]}"; do
  [[ -f "$file" ]] || continue
  if LC_ALL=C grep -q $'\r' "$file"; then
    crlf_files+=("$file")
  fi
done

if ((${#crlf_files[@]} > 0)); then
  echo "CRLF characters detected in changed files:" >&2
  printf '  %s\n' "${crlf_files[@]}" >&2
  exit 1
fi

echo "Repository structure checks passed"
