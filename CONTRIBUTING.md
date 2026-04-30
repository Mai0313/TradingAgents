# Contributing to TradingAgents

Guidelines for working on this codebase. Use the actual source under `src/tradingagents/` as the canonical reference; this doc only covers operational commands and project-wide style invariants.

## 🧰 Commands

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

Optional tasks via `poe` (defined in `[tool.poe.tasks]`):

```bash
uv run poe docs         # generate + serve docs
uv run poe gen          # generate + deploy docs (gh-deploy)
```

## 📚 Docs

Built with MkDocs Material. Generate locally and serve at http://localhost:9987:

```bash
uv sync --group docs
make gen-docs
uv run mkdocs serve
```

## 📦 Packaging

```bash
uv build                # wheel + sdist into dist/
UV_PUBLISH_TOKEN=... uv publish
```

## 🔁 CI

All workflows under `.github/workflows/`:

- **`test.yml`** — pytest on Python 3.12 / 3.13 / 3.14
- **`code-quality-check.yml`** — ruff + pre-commit hooks
- **`deploy.yml`** — MkDocs → GitHub Pages
- **`build_release.yml`** — build wheels + multi-platform executables on tag push
- **`build_image.yml`** — build & push Docker image to GHCR (kept as backup artifact)
- **`release_drafter.yml`** — draft releases from Conventional Commits

## 📁 Project Layout

```
src/tradingagents/
├── agents/      # @tool definitions, agent node creators, prompts/*.md, state schemas
├── dataflows/   # yfinance-backed data fetchers (plain module-level functions)
├── graph/       # LangGraph wiring: setup, propagation, reflection, signal_processing, conditional_logic
├── llm.py       # build_chat_model wrapping init_chat_model + per-provider reasoning_effort mapping
├── config.py    # TradingAgentsConfig schema + global singleton (set_config / get_config)
└── cli.py       # Entry point
```

Canonical examples (read these before writing similar code):

| Pattern                  | File                                              | Symbol                |
| ------------------------ | ------------------------------------------------- | --------------------- |
| Pure config model        | `config.py`                                       | `TradingAgentsConfig` |
| Stateful service class   | `graph/trading_graph.py`                          | `TradingAgentsGraph`  |
| LangGraph state schema   | `agents/utils/agent_states.py`                    | `AgentState`          |
| Provider-agnostic LLM    | `llm.py`                                          | `build_chat_model`    |
| `@tool`-wrapped function | `agents/utils/core_stock_tools.py`                | `get_stock_data`      |
| Agent node creator       | `agents/researchers/bull_researcher.py`           | `create_bull_*`       |

## 🎨 Code Style

### Pydantic

- Every config / state / service class subclasses `pydantic.BaseModel`. No bare `__init__`-based classes for stateful objects.
- Every `Field()` has `default` (or `default_factory`), `title`, and `description`.
- Mutable defaults always use `default_factory=` (never `default={}` or `default=[]`).
- Nested models use `default_factory=NestedModel`, not `default=NestedModel()`.
- Add `model_config = ConfigDict(arbitrary_types_allowed=True)` only when a field holds a non-Pydantic type (LLM client, `ToolNode`, dataclass, etc.).
- Derived expensive objects: `@computed_field` stacked directly above `@cached_property`, with a one-line docstring.
- Side effects after construction go in `@model_validator(mode="after")` returning `"ClassName"` (string forward ref, not `typing.Self`).
- For fields holding a `ChatModel` Union value, annotate as `SkipValidation[ChatModel]` to bypass Pydantic's cross-model coercion (LangChain's per-class validators fight each other otherwise).

### Type Hints

- Use PEP 604 / lowercase generics: `X | None`, `list[X]`, `dict[str, X]`, `tuple[X, Y]`. Never `Optional[X]`, `List[X]`, `Dict[str, X]`.
- Avoid bare `Any` in `@computed_field` return types — prefer the concrete type, the `ChatModel` Union, or `object`.
- Type LLM values as `ChatModel` (the union exported from `tradingagents.llm`), not `BaseChatModel`.

### Paths

- `pathlib.Path` only. Never `os.path.*`, `os.getcwd()`, or `os.path.join(...)`.
- Anchor with `Path(__file__).resolve().parent`.
- Extract path defaults to module-level `_CONSTANT` names — never inline inside `Field(default=...)`.

### LangGraph

- State schemas are Pydantic `BaseModel`, not `TypedDict` or `dataclass`. All fields have defaults so the schema can be instantiated empty.
- Node function signatures: `(state: AgentState) -> dict[str, Any]`. Access fields via attribute (`state.market_report`), not `state["market_report"]` or `.get(...)`.
- The `messages` field on `AgentState` must use `Annotated[list[AnyMessage], add_messages]` so the LangGraph reducer fires.
- Construct nested state updates as typed instances (`InvestDebateState(...)`), not raw dicts.
- Initial state via `Propagator.create_initial_state()` returning `AgentState`. Use `HumanMessage(content=...)`, not `("human", ...)` tuples.

### Prompts

- All agent prompts live under `src/tradingagents/agents/prompts/<name>.md`.
- Load with `load_prompt(name)` and `.format(**kwargs)`. Never inline system / user prompts as Python string literals or module-level constants.
- File name uses snake_case matching the agent role (e.g. `bull_researcher.md`, `reflector.md`).

### Misc

- Commit messages follow Conventional Commits.
- Open issues / PRs welcome. CI must pass; hooks should not be skipped.
