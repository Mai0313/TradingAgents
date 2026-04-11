# Pydantic Refactoring Guide

This document defines the Pydantic patterns used in this project. All classes under
`src/tradingagents/` should follow these conventions consistently.

---

## Table of Contents

1. [Core Philosophy](#1-core-philosophy)
2. [Module-Level Path Constants](#2-module-level-path-constants)
3. [Pure Config Models](#3-pure-config-models)
4. [Stateful Service Classes](#4-stateful-service-classes)
5. [Field Rules](#5-field-rules)
6. [Side Effects After Init](#6-side-effects-after-init)
7. [Return Type for model_validator](#7-return-type-for-model_validator)
8. [ConfigDict](#8-configdict)
9. [LangGraph State Models](#9-langgraph-state-models)
10. [Agent Prompt Files](#10-agent-prompt-files)
11. [What NOT to Do](#11-what-not-to-do)
12. [Checklist Before Submitting](#12-checklist-before-submitting)

---

## 1. Core Philosophy

Every class that holds configuration or state **must** inherit from `pydantic.BaseModel`.

Regular Python classes (`__init__`-based) are only acceptable for lightweight stateless
helpers that hold no fields of their own and are never instantiated directly by users.

Attribute categories and how to define them:

| Category                 | Description                                    | How to define                                    |
| ------------------------ | ---------------------------------------------- | ------------------------------------------------ |
| User-configurable input  | Parameters the caller passes at construction   | `Field(default=..., title=..., description=...)` |
| Mutable runtime state    | Values that change over time via method calls  | `Field(default=..., title=..., description=...)` |
| Derived / computed state | Expensive objects built from other fields      | `@computed_field` + `@cached_property`           |
| Side effects after init  | Global state updates, directory creation, etc. | `@model_validator(mode="after")`                 |

---

## 2. Module-Level Path Constants

Path defaults must never be inlined inside `Field(default=...)`. Extract them as
module-level constants so the intent is readable and the constant is reusable.

```python
# Good
from pathlib import Path

_PROJECT_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = Path("./results")
_DATA_CACHE_DIR = _PROJECT_DIR / "dataflows" / "data_cache"


class MyConfig(BaseModel):
    data_cache_dir: Path = Field(
        default=_DATA_CACHE_DIR,
        title="Data Cache Directory",
        description="Directory for caching downloaded data",
    )
```

```python
# Bad — inline path construction is hard to read and cannot be reused
class MyConfig(BaseModel):
    data_cache_dir: Path = Field(
        default=Path(__file__).resolve().parent / "dataflows" / "data_cache",
        ...
    )
```

Rules:

- Name constants with a leading underscore (`_PROJECT_DIR`, `_RESULTS_DIR`, `_DATA_CACHE_DIR`).
- Always use `Path(__file__).resolve().parent` (not `os.path`) to anchor paths relative to the source file.
- Never use `os.path`, `os.getcwd()`, or `os.getenv()` anywhere. Use `pathlib.Path` and
    `os.environ` / `python-dotenv` where environment variables are required.

---

## 3. Pure Config Models

A pure config model holds only data — no methods that produce side effects.

```python
from pathlib import Path
from pydantic import BaseModel, Field

_PROJECT_DIR = Path(__file__).resolve().parent
_RESULTS_DIR = Path("./results")
_DATA_CACHE_DIR = _PROJECT_DIR / "dataflows" / "data_cache"


class RetryConfig(BaseModel):
    """Example nested config block (used below to demonstrate nesting)."""

    max_retries: int = Field(
        default=3,
        title="Max Retries",
        description="Maximum number of retry attempts for transient failures",
    )
    backoff_seconds: float = Field(
        default=1.0,
        title="Backoff Seconds",
        description="Initial backoff delay between retries in seconds",
    )


class TradingAgentsConfig(BaseModel):
    """Top-level configuration for the TradingAgents framework."""

    project_dir: Path = Field(
        default=_PROJECT_DIR,
        title="Project Directory",
        description="Root directory of the tradingagents package",
    )
    results_dir: Path = Field(
        default=_RESULTS_DIR,
        title="Results Directory",
        description="Directory for saving analysis results",
    )
    data_cache_dir: Path = Field(
        default=_DATA_CACHE_DIR,
        title="Data Cache Directory",
        description="Directory for caching downloaded data",
    )
    llm_provider: str = Field(
        default="openai", title="LLM Provider", description="LLM provider to use"
    )
    retry: RetryConfig = Field(
        default_factory=RetryConfig,
        title="Retry Policy",
        description="Retry behaviour for transient failures",
    )
    extra_headers: dict[str, str] = Field(
        default_factory=dict,
        title="Extra Headers",
        description="Additional HTTP headers to attach to outbound requests",
    )
```

Key points:

- Nested models use `default_factory=NestedModel` (not `default=NestedModel()`).
- Mutable defaults (`list`, `dict`) always use `default_factory=list` / `default_factory=dict`.
- Immutable scalar defaults use `default=value` directly.

---

## 4. Stateful Service Classes

A stateful service class holds both user-facing fields and derived objects (LLMs,
compiled graphs, memory instances, etc.).

Divide attributes into three sections in this exact order:

```python
from functools import cached_property
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class MyService(BaseModel):
    """One-line summary."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # --- Section 1: User-configurable fields ---
    # All values the caller may pass at construction.

    config: MyConfig = Field(
        default_factory=MyConfig, title="Configuration", description="Service configuration"
    )
    debug: bool = Field(
        default=False, title="Debug Mode", description="Enable verbose debug output"
    )

    # --- Section 2: Mutable runtime state ---
    # Values that start with a sensible default and are updated by methods.

    current_result: dict[str, Any] = Field(
        default_factory=dict,
        title="Current Result",
        description="Most recent result, populated after run()",
    )
    last_ticker: str = Field(
        default="", title="Last Ticker", description="Ticker symbol used in the most recent run"
    )

    # --- Section 3: Side effects after init ---

    @model_validator(mode="after")
    def _setup(self) -> "MyService":
        """Run one-time side effects after all fields are validated."""
        # e.g. push config to a global singleton, create directories
        return self

    # --- Section 4: Derived / computed state ---
    # Expensive objects built lazily from the fields above.

    @computed_field
    @cached_property
    def llm(self) -> object:
        """LLM instance derived from config."""
        return create_llm_client(
            provider=self.config.llm_provider, model=self.config.quick_think_llm
        ).get_llm()

    @computed_field
    @cached_property
    def compiled_graph(self) -> object:
        """Compiled workflow graph derived from config."""
        ...

    # --- Public methods ---

    def run(self, ticker: str) -> str:
        """Run the service for a given ticker."""
        self.last_ticker = ticker
        result = self.compiled_graph.invoke(...)
        self.current_result = result
        return result
```

Key points:

- `model_config = ConfigDict(arbitrary_types_allowed=True)` is **required** whenever a
    `@computed_field` returns a non-Pydantic type (LLM client, LangGraph graph, dataclass, etc.).
- `@computed_field` must be stacked directly above `@cached_property` with no blank line between them.
- Each `@computed_field` / `@cached_property` must have a one-line docstring.
- Mutable runtime state (section 2) uses plain `Field()` — the same as user-configurable
    fields. The distinction is conceptual only; methods update these values with direct
    assignment (`self.last_ticker = ticker`).

---

## 5. Field Rules

Every field declaration must include all three of: `default` (or `default_factory`),
`title`, and `description`.

```python
# Good
name: str = Field(
    default="", title="Company Name", description="Full legal name of the company being analyzed"
)

# Good — mutable default uses default_factory
results: dict[str, Any] = Field(
    default_factory=dict, title="Results", description="Accumulated analysis results keyed by date"
)

# Good — required field with no default
ticker: str = Field(..., title="Ticker Symbol", description="Stock ticker symbol, e.g. NVDA")

# Bad — missing title and description
name: str = Field(default="")

# Bad — mutable default inside default= (will be shared across instances)
results: dict = Field(default={})
```

Type annotation rules:

- Use `str | None` not `Optional[str]`.
- Use `list[str]` not `List[str]`.
- Use `dict[str, Any]` not `Dict[str, Any]`.
- Use `tuple[X, Y]` not `Tuple[X, Y]`.
- Avoid bare `Any` in `@computed_field` return types; use `object` when the exact type
    is a third-party type that cannot be imported without a heavy dependency.

---

## 6. Side Effects After Init

Use `@model_validator(mode="after")` for any work that must happen after all fields are
validated but is not itself a validation (e.g. pushing config to a global singleton,
creating directories).

```python
from pydantic import model_validator


class MyService(BaseModel):
    @model_validator(mode="after")
    def _setup(self) -> "MyService":
        """Brief description of what side effect this performs."""
        some_global_singleton.set(self.config)
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        return self
```

Rules:

- The method must return `self` — annotated as the class name in double quotes
    (`-> "MyService"`), not as `Self` from `typing`.
- The method name should be `_setup` (or another descriptive private name with a single
    leading underscore).
- Never use `model_post_init` — `@model_validator(mode="after")` is preferred because
    it has a cleaner signature (no `__context` parameter).

---

## 7. Return Type for model_validator

Always use the class name as a string literal for the return type.

```python
# Good
@model_validator(mode="after")
def _setup(self) -> "TradingAgentsGraph":
    ...
    return self


# Bad — requires importing Self and is less explicit
@model_validator(mode="after")
def _setup(self) -> Self:
    ...
    return self
```

---

## 8. ConfigDict

Add `model_config = ConfigDict(arbitrary_types_allowed=True)` to any `BaseModel`
subclass that stores non-Pydantic objects as `@computed_field` results (LLM clients,
LangGraph graphs, dataclasses, etc.).

```python
from pydantic import BaseModel, ConfigDict


class MyService(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    ...
```

Pure config models that hold only scalars, `Path`, and nested `BaseModel` subclasses do
**not** need `ConfigDict`.

---

## 9. LangGraph State Models

LangGraph state schemas (`AgentState` and nested sub-states such as `InvestDebateState`,
`RiskDebateState`) **must** be Pydantic `BaseModel` subclasses — never `TypedDict` or
plain `dataclass`. This enables attribute access inside every node function and full
linter / IDE assistance.

### 9.1 State class definition

```python
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class InvestDebateState(BaseModel):
    """Pure data model — no ConfigDict needed (only scalars)."""

    history: str = Field(default="", title="History", description="...")
    count: int = Field(default=0, title="Count", description="...")
    # ... all fields must have sensible defaults so the model can be
    # instantiated with no arguments by Propagator.create_initial_state()


class AgentState(BaseModel):
    """Top-level graph state. Needs arbitrary_types_allowed for AnyMessage."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    messages: Annotated[list[AnyMessage], add_messages] = Field(
        default_factory=list,
        title="Messages",
        description="Conversation history; merged by the add_messages reducer",
    )
    investment_debate_state: InvestDebateState = Field(
        default_factory=InvestDebateState, title="Investment Debate State", description="..."
    )
```

Key points:

- The `Annotated[list[AnyMessage], add_messages]` annotation is required on `messages`
    so LangGraph applies its reducer when merging state updates.
- Nested sub-states (`InvestDebateState`, `RiskDebateState`) are plain `BaseModel`
    with all fields defaulting to empty strings / zero — they do **not** need
    `ConfigDict` unless they hold non-Pydantic types.
- `AgentState` needs `ConfigDict(arbitrary_types_allowed=True)` because `AnyMessage`
    is a third-party type.

### 9.2 Node function signatures

Every LangGraph node function must type its input as `AgentState` (not `dict[str, Any]`)
and access state fields with attribute syntax. The return value is still a partial
`dict[str, Any]` because nodes return only the fields they are updating.

```python
# Good
def market_analyst_node(state: AgentState) -> dict[str, Any]:
    current_date = state.trade_date  # attribute access
    messages = state.messages  # attribute access
    debate = state.investment_debate_state  # nested attribute access
    count = debate.count  # nested attribute access
    return {"market_report": "..."}  # partial update dict


# Bad — dict subscript on AgentState
def market_analyst_node(state: dict[str, Any]) -> dict[str, Any]:
    current_date = state["trade_date"]
    count = state["investment_debate_state"]["count"]
```

Additional rules:

- Never use `.get("field", default)` on a `BaseModel` instance. All fields already
    have defaults; just read the attribute directly (`state.field`).
- When building an updated nested state, construct a new `InvestDebateState(...)` or
    `RiskDebateState(...)` instance explicitly instead of returning a raw dict for that
    field. LangGraph will validate/coerce either way, but a typed instance is clearer.
- `Propagator.create_initial_state()` must return `AgentState` — not a plain dict.
    Use `HumanMessage(content=...)` for the initial message; tuple-style tuples
    `("human", ...)` are not valid `AnyMessage` values.

---

## 10. Agent Prompt Files

All system and user prompts for agent nodes **must** live under
`src/tradingagents/agents/prompts/` as Markdown (`.md`) files. Load them at
call-time using the `load_prompt(name)` helper — never inline them as string
literals or module-level constants in Python source files.

```python
# Good — prompt in agents/prompts/my_agent.md
from tradingagents.agents.prompts import load_prompt


def my_agent_node(state: AgentState) -> dict[str, Any]:
    prompt = load_prompt("my_agent").format(field=state.some_field)
    ...


# Bad — inline string literal
SYSTEM_PROMPT = """You are an expert..."""  # never do this

# Bad — module-level constant in .py file
_MY_PROMPT = "You are an expert..."  # move to a .md file instead
```

Naming convention: the `.md` file name should match the snake_case name of the
agent role (e.g. `market_analyst.md`, `bull_researcher.md`, `reflector.md`).

---

## 11. What NOT to Do

| Anti-pattern                                    | Correct alternative                                           |
| ----------------------------------------------- | ------------------------------------------------------------- |
| `class Foo: def __init__(self, x): self.x = x`  | `class Foo(BaseModel): x: int = Field(...)`                   |
| `Field(default={})` or `Field(default=[])`      | `Field(default_factory=dict)` / `Field(default_factory=list)` |
| `os.path.join(...)`, `os.path.abspath(...)`     | `pathlib.Path(...)`                                           |
| `os.path.dirname(__file__)`                     | `Path(__file__).resolve().parent`                             |
| `Field(default=SomeModel())` for nested model   | `Field(default_factory=SomeModel)`                            |
| `from typing import Optional; x: Optional[str]` | `x: str \| None`                                              |
| `model_post_init(self, __context: object, /)`   | `@model_validator(mode="after")`                              |
| `-> Self` on model_validator                    | `-> "ClassName"`                                              |
| `PrivateAttr()` for runtime state               | `Field(default=..., title=..., description=...)`              |
| `PrivateAttr()` for derived objects             | `@computed_field` + `@cached_property`                        |
| Bare `Any` in `@computed_field` return type     | Use concrete type or `object`                                 |

---

## 12. Checklist Before Submitting

- [ ] Class inherits from `BaseModel`
- [ ] `model_config = ConfigDict(arbitrary_types_allowed=True)` present if needed
- [ ] All fields have `title=` and `description=`
- [ ] Mutable defaults use `default_factory=`, not `default=`
- [ ] Path defaults extracted to module-level `_CONSTANT` names
- [ ] No `os.path` anywhere — only `pathlib.Path`
- [ ] No `Optional[X]` — use `X | None`
- [ ] No `PrivateAttr` — use `Field()` or `@computed_field`
- [ ] `@computed_field` stacked directly above `@cached_property`
- [ ] Each `@computed_field` has a one-line docstring
- [ ] Side effects in `@model_validator(mode="after")` returning `"ClassName"`
- [ ] No `model_post_init`
- [ ] LangGraph state classes are `BaseModel`, not `TypedDict` or `dataclass`
- [ ] Node functions typed as `(state: AgentState) -> dict[str, Any]`
- [ ] State accessed with `state.field` — no `state["field"]` or `.get()`
- [ ] Nested state updates return typed instances (`InvestDebateState(...)`) not raw dicts
- [ ] `Propagator.create_initial_state()` returns `AgentState`, uses `HumanMessage`
- [ ] Agent prompts stored in `agents/prompts/<name>.md`, loaded via `load_prompt()`
- [ ] No inline prompt strings or module-level prompt constants in `.py` files
