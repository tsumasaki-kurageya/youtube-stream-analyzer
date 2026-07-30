# Local development

## Recommended path: Dev Container

Prerequisites:

- Docker-compatible container runtime
- Visual Studio Code with Dev Containers, or another compatible client

Open the repository in the Dev Container. The container installs Node.js, Go, Python, Docker CLI support, PostgreSQL client tools, GitHub CLI, Make, and ShellCheck.

After creation, verify the environment:

```bash
node --version
go version
python3 --version
docker version
psql --version
gh --version
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
```

M0 intentionally has no application runtime. Commands are extended as M1 and later milestones add projects.

## Troubleshooting

- Dev Container build fails: rebuild without cache and confirm access to container registries and language download hosts.
- Docker CLI cannot connect: confirm the host Docker daemon is running and Docker-outside-of-Docker is available.
- `make check` reports a missing file: restore the required M0 artifact or update the validation only when the repository convention changes intentionally.
- GitHub CLI is unauthenticated: run `gh auth login` before publishing branches or pull requests from the container.
