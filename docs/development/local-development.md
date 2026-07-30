# Local development

## Recommended path: Dev Container

Prerequisites:

- Docker-compatible container runtime
- Visual Studio Code with Dev Containers, or another compatible client

Open the repository in the Dev Container. The container installs Node.js, Go, Python, Docker CLI support, PostgreSQL client tools, GitHub CLI, Make, ShellCheck, and Graphify.

After creation, verify the environment:

```bash
node --version
go version
python3 --version
docker version
psql --version
gh --version
graphify --version
make check
```

## Common commands

```bash
make setup   # Install or prepare repository dependencies
make dev     # Start implemented application processes
make test    # Run tests available at the current milestone
make lint    # Run static checks
make format  # Apply formatters when source projects exist
make check   # Run the CI-equivalent validation entry point
make graphify        # Rebuild the local, code-only knowledge graph
make graphify-update # Update code nodes in an existing graph
```

M0 intentionally has no application runtime. Commands are extended as M1 and later milestones add projects.

## Graphify

The Dev Container installs the `graphifyy` package at version `0.9.30`. Its `graphify` command is available on `PATH`, and the project-scoped Codex Skill is stored in `.codex/skills/graphify/`.

`make graphify` uses deterministic local AST extraction by default:

```bash
make graphify
```

This default passes `--code-only`, so source code stays local and no LLM credentials are required. To include Markdown and other semantic content from a Codex session, invoke the project Skill with `$graphify .`.

After source-code changes, update an existing graph with:

```bash
make graphify-update
```

Graphify writes generated files under `graphify-out/`. The directory is currently Git-ignored. Whether those files should be committed will be decided after the proof of concept; remove the ignore rule only after that decision.

No Graphify Git hooks, Neo4j integration, MCP server, watch mode, or CI graph generation are enabled.

## Troubleshooting

- Dev Container build fails: rebuild without cache and confirm access to container registries and language download hosts.
- `graphify` is unavailable or reports another version: rebuild the Dev Container.
- `make graphify-update` reports a missing graph: run `make graphify` first.
- Docker CLI cannot connect: confirm the host Docker daemon is running and Docker-outside-of-Docker is available.
- `make check` reports a missing file: restore the required M0 artifact or update the validation only when the repository convention changes intentionally.
- GitHub CLI is unauthenticated: run `gh auth login` before publishing branches or pull requests from the container.
