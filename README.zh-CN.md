<div align="center" markdown="1">

# TradingAgents

[![PyPI version](https://img.shields.io/pypi/v/tradingagents.svg)](https://pypi.org/project/tradingagents/)
[![python](https://img.shields.io/badge/-Python_%7C_3.12%7C_3.13%7C_3.14-blue?logo=python&logoColor=white)](https://www.python.org/downloads/source/)
[![uv](https://img.shields.io/badge/-uv_dependency_management-2C5F2D?logo=python&logoColor=white)](https://docs.astral.sh/uv/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://docs.pydantic.dev/latest/contributing/#badges)
[![tests](https://github.com/Mai0313/TradingAgents/actions/workflows/test.yml/badge.svg)](https://github.com/Mai0313/TradingAgents/actions/workflows/test.yml)
[![code-quality](https://github.com/Mai0313/TradingAgents/actions/workflows/code-quality-check.yml/badge.svg)](https://github.com/Mai0313/TradingAgents/actions/workflows/code-quality-check.yml)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Mai0313/TradingAgents)
[![license](https://img.shields.io/badge/License-MIT-green.svg?labelColor=gray)](https://github.com/Mai0313/TradingAgents/tree/main?tab=License-1-ov-file)
[![PRs](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Mai0313/TradingAgents/pulls)
[![contributors](https://img.shields.io/github/contributors/Mai0313/TradingAgents.svg)](https://github.com/Mai0313/TradingAgents/graphs/contributors)

</div>

🚀 **TradingAgents** 是一个多 Agent LLM 金融交易框架，利用大型语言模型模拟分析师团队、研究辩论和投资组合管理决策，以提供股票交易分析。

其他语言: [English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

## ✨ 重点特色

- 基于 **LangGraph** 构建，提供稳健的多 Agent 编排机制
- 多 Agent 架构：分析师团队 → 研究团队 → 交易员 → 风险管理 → 投资组合管理
- 通过 `langchain.chat_models.init_chat_model` 构造 LLM，使用独立的 `llm_provider` 字段加上 model name 指定模型,支持 OpenAI、Anthropic、Google Gemini、xAI (Grok)、OpenRouter、Ollama、HuggingFace、LiteLLM
- 统一的 `reasoning_effort` 旋钮（`low / medium / high / xhigh / max`）会 map 到各 provider 的 native 参数（Anthropic `effort`、OpenAI `reasoning_effort`、Google `thinking_level`）
- 市场数据全由 `yfinance` 提供：OHLCV、基本面、技术指标、新闻与内部人交易
- 基于 Pydantic 的配置系统，提供严格类型检查与验证
- 分析结果自动保存至 `results/` 目录并按团队分组
- 现代 `src/` 布局，完整类型注解
- 通过 `uv` 进行快速依赖管理
- Pre-commit 包链：ruff、mdformat、codespell、mypy、uv hooks
- Pytest + coverage、MkDocs Material 文档系统

## 🚀 快速开始

```bash
git clone https://github.com/Mai0313/TradingAgents.git
cd TradingAgents
make uv-install               # 安装 uv（仅需一次）
uv sync                       # 安装依赖
cp .env.example .env          # 配置 API 密钥
```

### 配置 API 密钥

编辑 `.env` 并设置您的 LLM 供应商密钥：

```bash
# LLM 供应商（设置您使用的那一个）
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
XAI_API_KEY=...
OPENROUTER_API_KEY=...
```

### 使用方式

```python
from tradingagents.config import TradingAgentsConfig
from tradingagents.graph.trading_graph import TradingAgentsGraph

config = TradingAgentsConfig(
    llm_provider="openai",
    deep_think_llm="gpt-5",
    quick_think_llm="gpt-5-mini",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    max_recur_limit=100,
    reasoning_effort="medium",
)

ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

`llm_provider` 是 `langchain.chat_models.init_chat_model` 的 registry key（`openai`、`anthropic`、`google_genai`、`xai`、`openrouter`、`ollama`、`huggingface`、`litellm`)；`deep_think_llm` / `quick_think_llm` 则填该 provider 接受的 model name(`gpt-5`、`claude-sonnet-4-6`、`gemini-3-pro-preview`、`grok-4` 等）。

## 📁 项目结构

```
src/
└── tradingagents/
    ├── agents/           # Agent 实现
    │   ├── analysts/     # 市场、新闻、社交、基本面分析师
    │   ├── managers/     # 研究 & 投资组合管理者
    │   ├── researchers/  # 多头 & 空头研究员
    │   ├── risk_mgmt/    # 风险管理 Agents
    │   ├── trader/       # 交易员 Agent
    │   └── utils/        # 共用 Agent 工具
    ├── dataflows/        # yfinance 数据采集
    ├── graph/            # LangGraph 交易图配置
    ├── llm.py            # Chat model 构造（init_chat_model wrapper + reasoning_effort mapping）
    ├── config.py         # TradingAgentsConfig schema 与全局 singleton
    └── cli.py            # 入口
```

## 🤖 Agent 工作流程

TradingAgents 通过 LangGraph `StateGraph` 编排 **12 个 LLM agent** 加上 **2 个支持组件**，每次执行会依序跑过 4 个 phase，所有状态（各类 report、debate transcript、trade decision）都通过一个共用的 Pydantic `AgentState` 在所有节点之间传递。

### Phase 1 — 分析师团队（数据采集）

四位 analyst 依序执行。每位 analyst 的 LLM 都会 `bind_tools(...)` 到一组以 `yfinance` 为 backend 的 `@tool` 函数，并与其专属的 `ToolNode` 配对，持续 loop 直到没有新的 tool call 为止。每位 analyst 结束之后会经过一个 `Msg Clear` node，它会发出 `RemoveMessage` 并补上一个 `HumanMessage("Continue")` placeholder（这是为了维持 Anthropic 对最后一则消息必须是 human 的要求）。

| Analyst                  | LLM 绑定的 tools                                                                | 写入 state            |
| ------------------------ | ------------------------------------------------------------------------------- | --------------------- |
| **Market Analyst**       | `get_stock_data`, `get_indicators`                                              | `market_report`       |
| **Social Media Analyst** | `get_news`                                                                      | `sentiment_report`    |
| **News Analyst**         | `get_news`, `get_global_news`                                                   | `news_report`         |
| **Fundamentals Analyst** | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement` | `fundamentals_report` |

Market Analyst 可挑选的 technical indicator（一次最多 8 个）：`close_50_sma`、`close_200_sma`、`close_10_ema`、`macd`、`macds`、`macdh`、`rsi`、`boll`、`boll_ub`、`boll_lb`、`atr`、`vwma`。

### Phase 2 — 研究辩论

- **Bull Researcher** 与 **Bear Researcher** 会按照 `max_debate_rounds`（默认为 1，等于双方各讲一轮）互相辩论，依据 "上一位发言者是谁" 决定下一个轮到谁。每位 researcher 会先用自己的 `FinancialSituationMemory` 做 BM25 retrieval，把 top-k 的过往经验灌进 prompt 再开讲。
- 终止条件：当 `count >= 2 * max_debate_rounds` 时，graph 会 route 到 **Research Manager**（deep-thinking LLM），由它汇整整场辩论、产出 `investment_plan`，并填入 `investment_debate_state.judge_decision`。

### Phase 3 — Trader

**Trader**（quick-thinking LLM）会读取 `investment_plan` 以及来自 `trader_memory` 的 top-k 历史经验，输出 `trader_investment_plan`。它的输出必须以 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` 结尾。

### Phase 4 — 风险辩论

三位 risk debator 以固定顺序轮流发言：**Aggressive → Conservative → Neutral → Aggressive → …**，循环 `max_risk_discuss_rounds` 轮（默认为 1，代表每种立场各发言一次）。终止条件：当 `count >= 3 * max_risk_discuss_rounds` 时，graph route 到 **Risk Judge**（由 `create_risk_manager` 建立的 deep-thinking LLM），由它修正 trader 的计划并写入 `final_trade_decision`。最后再由一个轻量的 `SignalProcessor` LLM 把这段自然语言决策抽成单一 token — `BUY` / `SELL` / `HOLD`。

### 支持组件

- **FinancialSituationMemory** — 采 BM25Okapi 做 retrieval，整个流程共有 5 个 instance（bull、bear、trader、invest_judge、risk_manager）。纯 lexical 相似度，不需要任何 embedding API。
- **Reflector** — 交易结果出炉之后，调用 `TradingAgentsGraph.reflect_and_remember(returns_losses)` 会针对 5 个 memory 各跑一轮 post-trade reflection，把这次的成败写回对应的 memory 供之后 retrieval 使用。

### 流程示意

```
START
  │
  ▼
[Market Analyst ⇄ tools_market] → Msg Clear
  │
  ▼
[Social Analyst ⇄ tools_social] → Msg Clear
  │
  ▼
[News Analyst ⇄ tools_news] → Msg Clear
  │
  ▼
[Fundamentals Analyst ⇄ tools_fundamentals] → Msg Clear
  │
  ▼
[Bull Researcher ⇄ Bear Researcher] × max_debate_rounds
  │
  ▼
Research Manager  →  Trader
                        │
                        ▼
[Aggressive → Conservative → Neutral] × max_risk_discuss_rounds
  │
  ▼
Risk Judge  →  SignalProcessor  →  END
```

每次执行的完整 state 会写入 `results/<股票代码>/TradingAgentsStrategy_logs/full_states_log_<日期>.json`（路径由 `TradingAgentsConfig.results_dir` 决定，默认为 `./results`）。

## 🤝 贡献

有关开发说明（包含文档、测试和 Docker 服务等），请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 欢迎 Issue/PR
- 请遵循代码风格（ruff、类型）
- PR 标题遵循 Conventional Commits

## 📄 授权

MIT — 详见 `LICENSE`。
