# Contributing to TradingAgents

Thank you for your interest in contributing to TradingAgents! This document provides guidelines and information for developers.

## 🧰 Commands Reference

```bash
# Development
make help               # List available make targets
make clean              # Clean caches, artifacts and generated docs
make format             # Run all pre-commit hooks
make test               # Run pytest across the repository
make gen-docs           # Generate docs from src/ and scripts/

# Dependencies (via uv)
make uv-install         # Install uv on your system
uv add <pkg>            # Add production dependency
uv add <pkg> --dev      # Add development dependency
uv sync --group dev     # Install dev-only deps (pre-commit, poe, notebook)
uv sync --group test    # Install test-only deps
uv sync --group docs    # Install docs-only deps
```

## 📚 Documentation

- Live docs are built with MkDocs Material.
- Generate API docs locally and serve:

```bash
uv sync --group docs
make gen-docs
uv run mkdocs serve    # http://localhost:9987
```

## 🐳 Docker Environment

A `Dockerfile` is provided in the `docker/` directory for building a containerized version of the application.

Build the Docker image:

```bash
docker build -t tradingagents -f docker/Dockerfile .
```

Run the container:

```bash
docker run -it --env-file .env tradingagents
```

## 📦 Packaging and Distribution

Build artifacts with uv (wheel and sdist go to `dist/`):

```bash
uv build
```

Publish to PyPI (requires `UV_PUBLISH_TOKEN`):

```bash
UV_PUBLISH_TOKEN=... uv publish
```

## 🧭 Optional Task Runner (Poe the Poet)

Convenience tasks are defined under `[tool.poe.tasks]` in `pyproject.toml`:

```bash
uv run poe docs        # generate + serve docs
uv run poe gen         # generate + deploy docs (gh-deploy)
```

## 🔁 CI/CD Actions Overview

All workflows live in `.github/workflows/`.

- **Tests** (`test.yml`) — Runs pytest on Python 3.12/3.13/3.14
- **Code Quality** (`code-quality-check.yml`) — Runs ruff and pre-commit hooks
- **Docs Deploy** (`deploy.yml`) — Builds and publishes MkDocs to GitHub Pages
- **Build and Release** (`build_release.yml`) — Builds multi-platform executables and Python packages on tag push
- **Publish Docker Image** (`build_image.yml`) — Builds and pushes Docker image to GHCR
- **Release Drafter** (`release_drafter.yml`) — Maintains draft releases based on Conventional Commits
