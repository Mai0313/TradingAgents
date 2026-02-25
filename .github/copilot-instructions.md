# Copilot Instructions for tradingagents

## IMPORTANT: This is a Template Project

**DO NOT develop directly on this repository.** This is a project template designed to be forked/cloned and renamed for creating new Python projects.

When working with this codebase, the correct workflow is:

1. Fork or clone this repository to create a new project
2. Rename `tradingagents` to your actual project name throughout the codebase
3. Rename `RepoTemplate` to your actual project display name
4. Then begin development on the renamed project

If a user asks to add features or modify code, first confirm whether they want to:

- A) Update the template itself (rare, only for template maintenance)
- B) Create a new project from this template (most common use case)

## Project Overview

This is a **production-ready Python project template** using modern tooling with `uv` for dependency management, comprehensive CI/CD, Docker support, and MkDocs Material documentation. The template provides a complete scaffold that can be quickly adapted for new Python projects.

## Critical Architecture Decisions

### src/ Layout with Strict Packaging

- Source code lives in `src/tradingagents/` (not root-level package)
- This prevents accidental imports of local code during tests
- When forking: rename both the `src/tradingagents/` directory AND all references in `pyproject.toml`, scripts, and workflows

### uv-First Dependency Management

- **Never** use `pip install` or `poetry` - this project uses `uv` exclusively
- Install dependencies: `uv sync` (not `pip install -r requirements.txt`)
- Add dependencies: Edit `pyproject.toml` dependencies list, then run `uv sync`
- Run commands: `uv run <command>` to ensure correct environment
- The project is configured as `managed = true` and `package = true` in `[tool.uv]`

### Dual CLI Entry Points

- Main CLI: `uv run tradingagents` or `uv run cli` (via `project.scripts` in pyproject.toml)
- Both `cli` and `tradingagents` commands point to `tradingagents.cli:main`

## Developer Workflows

### First-Time Setup

```bash
make uv-install               # Install uv (only needed once)
uv sync                       # Install all dependencies
uv tool install pre-commit    # Or: uv sync --group dev
make format                   # Run pre-commit hooks
```

### Common Commands

- `make format` or `uv run pre-commit run -a` - Run ALL pre-commit hooks (ruff, mypy, mdformat, codespell, nbstripout, gitleaks)
- `make test` - Run pytest with coverage (80% minimum, fails below threshold)
- `make clean` - Remove all build artifacts, caches, and generated docs
- `make gen-docs` - Generate API docs from `src/` and `scripts/` into `docs/Reference/` and `docs/Scripts/`
- `uv run mkdocs serve` - Start docs server at `http://0.0.0.0:9987`

### Testing Philosophy

- Tests in `tests/` directory, mirroring `src/` structure
- Coverage reports to `.github/reports/` (committed to repo for PR comments)
- **80% coverage minimum** enforced via `--cov-fail-under=80` in pyproject.toml
- Use `pytest -n=auto` for parallel execution via xdist
- Mark slow tests with `@pytest.mark.slow` and skip in CI with `@pytest.mark.skip_when_ci`

### Pre-commit Hooks Run on Multiple Git Events

- Hooks run on: pre-commit, post-checkout, post-merge, post-rewrite
- This ensures consistency across branch switches and merges
- Use `make format` to manually trigger all hooks

## Code Conventions

### Type Hints & Pydantic Models

- **All functions must have type hints** including return types
- Use Pydantic models for structured data (see `cli.py` `Response` class example)
- Enable `use_attribute_docstrings=True` in `ConfigDict` for field docstrings
- Prefer `AliasChoices` for flexible field names: `validation_alias=AliasChoices("name", "Name")`

### Docstring Style: Google

- Use Google-style docstrings (enforced by ruff pydocstyle)
- Example from `cli.py`:
    ```python
    def main() -> Response:
        """Generates a greeting response.

        This function creates a Response object with a predefined name and content.

        Returns:
            Response: An object containing the name and content.
        """
    ```

### Ruff Configuration Specifics

- Line length: **99 characters** (matching Google Style Guide)
- Chinese punctuation allowed in `allowed-confusables`: `。，；：` etc.
- Print statements (`T201`) and unused vars (`F841`) NOT auto-fixed
- isort: `length-sort = true` and `length-sort-straight = true` - imports sorted by length then alpha
- Format code snippets in docstrings with `docstring-code-format = true`

### File Naming & Imports

- Test files: `test_*.py` in `tests/` directory
- Import local packages: Use `from tradingagents.module import ...` (never relative)
- Scripts with dependencies: Use PEP 723 inline metadata (see `scripts/gen_docs.py` header)

## Documentation Generation

### Auto-Docs with gen_docs.py

- Script: `scripts/gen_docs.py` generates markdown docs from Python files/classes
- Two modes: `--mode class` (default, one page per class) or `--mode file` (one page per file)
- Preserves folder structure in output: `src/tradingagents/cli.py` → `docs/Reference/cli.md`
- Async file processing with `anyio` and rich progress bars
- Optional notebook execution via `--execute` flag
- Concurrency controlled via `--concurrency` (default: 10)
- Excludes: `.venv` by default, customize with `--exclude`

### MkDocs Material Configuration

- Docs server: `http://0.0.0.0:9987` (not localhost)
- Uses mkdocstrings with inheritance diagrams via `show_inheritance_diagram: true`
- Supports markdown-exec for executable code blocks
- Type hints rendered by griffe-typingdoc extension

## Docker & Services

### Multi-Stage Dockerfile

- Base: `nikolaik/python-nodejs:python3.11-nodejs22` (Python + Node.js)
- Uses official `ghcr.io/astral-sh/uv:latest` for uv/uvx binaries
- Production stage: `uv sync --no-dev` for minimal image
- Workdir: `/app`

### docker-compose.yaml Services

- **Redis** on `127.0.0.1:6379` with health checks
- **PostgreSQL** on `127.0.0.1:5432` (creds: postgres/postgres)
- **MongoDB** on `127.0.0.1:27017`
- **MySQL** on `127.0.0.1:3306` (creds: root/root, user: mysql/mysql)
- All services have health checks, named volumes, and `restart: always`
- Main app service commented out by default

## CI/CD Workflows

### Test Workflow (.github/workflows/test.yml)

- Runs pytest with coverage reports
- Matrix: Python 3.11, 3.12, 3.13, 3.14
- Generates coverage badge and commits HTML report to `.github/coverage_html_report/`
- PR comments with coverage summary

### Code Quality (.github/workflows/code-quality-check.yml)

- Runs all pre-commit hooks via `uv run pre-commit run -a`
- Includes ruff check, ruff format, mypy, and other linters
- Enforces pre-commit hook standards

### Documentation Deploy (.github/workflows/deploy.yml)

- Auto-generates docs with `make gen-docs`
- Deploys to GitHub Pages via `mkdocs gh-deploy`

### Docker Image Build (.github/workflows/build_image.yml)

- Builds and pushes to GHCR (ghcr.io)
- Uses buildx for caching

### Release Management

- **release_drafter.yml**: Auto-generates release notes from PRs
- **build_release.yml**: Uses `dunamai` for PEP 440 versioning from git tags
- **semantic-pull-request.yml**: Enforces conventional commit PR titles

### Security & Automation

- **code_scan.yml**: Gitleaks secret scanning
- **dependency-review.yml**: Reviews dependency changes
- **pre-commit-updater.yml**: Auto-updates pre-commit hook versions
- **auto_labeler.yml**: Auto-labels PRs based on changed files

## Project-Specific Patterns

### Version Management in CI

- Version extracted from git via `dunamai from git --bump --no-metadata --style pep440`
- Applied during package build, NOT in pyproject.toml (which stays at `0.1.0`)
- Use `git-cliff` for changelog generation from conventional commits

### Coverage Reports Committed to Repo

- Unlike typical projects, coverage reports ARE committed to `.github/reports/`
- This enables PR comment bots to show coverage changes
- HTML reports in `.github/coverage_html_report/`

### poethepoet Task Runner (Optional)

- Alternative to Makefile: `uv run poe <task>`
- Tasks defined in `[tool.poe.tasks]` section of pyproject.toml
- Example: `uv run poe docs` runs `make gen-docs` then `mkdocs serve`

### i18n Documentation

- README files: `README.md` (English), `README.zh-TW.md` (Traditional Chinese), `README.zh-CN.md` (Simplified Chinese)
- All three should be kept in sync when updating project descriptions

## Creating a New Project from This Template

This section describes the essential steps to transform this template into your new project.

### Step 1: Create Repository from Template

Use GitHub's "Use this template" button or clone directly:

```bash
git clone https://github.com/Mai0313/tradingagents.git my_new_project
cd my_new_project
```

### Step 2: Rename Package and Module

Replace `tradingagents` with your new package name everywhere:

- Rename the `src/tradingagents/` directory to `src/your_new_project/`
- Update all imports in Python files from `tradingagents` to `your_new_project`
- Update `pyproject.toml` references to the package name
- Update workflow files in `.github/workflows/`
- Update Docker labels in `docker/Dockerfile` and `.devcontainer/Dockerfile`

### Step 3: Rename Display Titles

Replace `RepoTemplate` with your project's display name:

- Update `mkdocs.yml` site_name
- Update README files titles and badges
- Update documentation references

### Step 4: Update Project Metadata

Edit `pyproject.toml` to update:

- `[project]` section: name, version, description, authors
- `[project.urls]` section: Homepage, Repository URLs
- `[project.scripts]` section: CLI command names if needed

### Step 5: Update Repository URLs

Replace `Mai0313/tradingagents` with your repository path:

- Update `mkdocs.yml`: repo_name, repo_url, site_url
- Update all three README files: badges, links, and "Use this template" URL
- Update `.github/CODEOWNERS` with your GitHub username

### Step 6: Update Author Information

Replace author details with your own:

- `pyproject.toml`: authors name and email
- `mkdocs.yml`: site_author
- `docker/Dockerfile`: LABEL maintainer and vendor
- `.devcontainer/Dockerfile`: LABEL maintainer and vendor

### Step 7: Customize Optional Components

- **CI secrets**: Add PyPI tokens to GitHub secrets if publishing packages
- **Pre-commit hooks**: Adjust `.pre-commit-config.yaml` for your needs
- **Coverage threshold**: Modify `--cov-fail-under` in `[tool.pytest.ini_options]` if 80% is too strict/lenient
- **Docker services**: Enable/disable services in `docker-compose.yaml` based on project requirements

### Step 8: Initialize Your Project

```bash
uv sync                       # Install dependencies
uv tool install pre-commit    # Setup pre-commit
make format                   # Run pre-commit hooks
make test                     # Verify tests pass
```

### Step 9: Update Documentation Content

- Update all three README files: `README.md`, `README.zh-TW.md`, `README.zh-CN.md`
- **Preserve all badges** in README files, only update the repository URLs within them
- Remove or update template-specific content and examples
- Update `docs/` content to describe your project instead of the template

## External Dependencies & Integration

- **PyPI Publishing**: Configured via `tool.uv.publish-url` (requires PyPI token in CI)
- **GitHub Pages**: Docs deploy requires `contents: write` and `pages: write` permissions
- **GHCR Docker Registry**: Uses `ghcr.io/<owner>/<repo>` - requires packages: write permission
- **Pre-commit.ci**: Optional service for running pre-commit hooks on PRs (not enabled by default)

## Critical Usage Guidelines

- Always use `uv sync` for installing dependencies, never use `pip install`
- Always prefix script execution with `uv run <command>` to ensure correct environment
- Coverage threshold is set in `[tool.pytest.ini_options]` at `--cov-fail-under=80`
- Large files require explicit bypass of `check-added-large-files` pre-commit hook if needed
- Always use absolute imports: `from tradingagents.module import ...`, never relative imports
- Always run `make clean` before regenerating docs to avoid stale references
