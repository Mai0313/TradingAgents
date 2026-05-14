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
- 多 Agent 架构：分析师团队 → **Situation Summariser** → 研究团队 → 交易员 → 风险管理 → 投资组合管理
- **结构化交易建议** — Risk Judge 输出强类型 `TradeRecommendation`(signal、size、target、stop、horizon、confidence、rationale),由一段 JSON 块加上 canonical `FINAL TRANSACTION PROPOSAL` 行解析得到
- **Backtest 工具** — `tradingagents backtest` 在日期 grid 上驱动 `propagate()`,依 cache 过的 OHLCV 算实际 return,报告 Sharpe / hit-rate / drawdown,并支持 `--dry-run` stub-LLM 模式做 harness 验证
- 通过 `langchain.chat_models.init_chat_model` 构造 LLM，使用独立的 `llm_provider` 字段加上 model name 指定模型,支持 OpenAI、Anthropic、Google Gemini、xAI (Grok)、OpenRouter、Ollama、HuggingFace、LiteLLM
- 统一的 `reasoning_effort` 旋钮（`low / medium / high / xhigh / max`）会 map 到各 provider 的 native 参数（Anthropic `effort`、OpenAI `reasoning_effort`、Google `thinking_level`）
- 市场数据全由 `yfinance` 提供:OHLCV、基本面、技术指标、新闻、内部人交易、analyst ratings、earnings calendar、institutional holders、short interest、dividends / splits,以及区域 macro 上下文(local index、^TNX、^VIX)
- Google News 路由按地区自动选择 — exchange suffix(`.TW`、`.HK`、`.T`、`.DE`、...)决定 `hl` / `gl` / `ceid`,非美股标的可以拿到当地语言的新闻覆盖
- 所有历史 tool 都做 point-in-time 过滤 — 带 reporting-lag 调整后的 `as_of` 日期,back-test 不会泄漏未来财报
- 基于 Pydantic 的配置系统，提供严格类型检查与验证
- 分析结果自动保存至 `results/` 目录并按团队分组(state log schema 带版本号,reflect CLI 内置 v1 → v2 migration)
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

#### Command line / 交互模式

包提供 `tradingagents` console script,含四个 subcommand:

```bash
uv run tradingagents tui                     # 交互式 questionary 流程
uv run tradingagents cli                     # 全部使用默认值执行
uv run tradingagents cli --ticker AAPL \
    --deep_think_llm gpt-5 \
    --quick_think_llm gpt-5-mini             # 通过 flag 覆盖
uv run tradingagents reflect --ticker AAPL --date 2024-05-10 --returns 0.032   # 交易后反思
uv run tradingagents backtest --tickers GOOG,2330.TW \
    --start 2024-01-01 --end 2024-06-30 \
    --frequency weekly --horizon-days 5 \
    --budget-cap-usd 25                      # 在 LLM 成本上限内跑 grid backtest
uv run tradingagents backtest --tickers GOOG \
    --start 2024-01-01 --end 2024-06-30 --dry-run   # 秒验 harness、$0 成本
uv run tradingagents --help                  # rich 渲染的 top-level help
uv run tradingagents cli --help              # rich 渲染的 per-command flag 列表
```

`tradingagents tui` 会用一连串 questionary prompt 带你走完所有参数(ticker、日期、provider、models、辩论轮数、analyst 选择等);`tradingagents cli` 是同一条流程,但完全用 command-line flag 驱动,方便写进 shell script 或 CI。`tradingagents reflect` 会把过去 run 的 state log 重新跑 post-trade reflector,把学到的教训写进 BM25 memory。`tradingagents backtest` 会在日期 grid 上反复调用 `propagate()`,用下一个 bar 的 close 做 mark-to-market,报告 Sharpe / hit rate / expectancy / drawdown,并依 token-aware cost tracker 强制 `--budget-cap-usd`。加 `--dry-run` 会切到 in-memory stub LLM,直接回 canned 的 `TradeRecommendation` payload — 拿来在不烧 API 预算的情况下验证 harness 对真实 cached OHLCV 的处理。两条交互路径跑 graph 时都会把 LangGraph 的 agent 消息通过 Rich panel 流式输出(prose 用 Markdown 渲染、tool 输出做 JSON pretty-print、payload 过长会自动截断)。`python -m tradingagents <subcommand>` 也走同一条 dispatcher。

#### 程序调用

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
    response_language="en-US",
)

ta = TradingAgentsGraph(debug=True, config=config)
state, recommendation = ta.propagate("NVDA", "2024-05-10")
print(recommendation.signal, recommendation.size_fraction, recommendation.confidence)
print(recommendation.rationale)
```

`propagate()` 返回 `(AgentState, TradeRecommendation)`。`TradeRecommendation` 是一个 Pydantic model:

- `signal: Literal["BUY", "SELL", "HOLD"]` — 标准方向
- `size_fraction: float`(0.0 – 1.0)— 仓位大小占可用资金的比例
- `target_price: float | None`、`stop_loss: float | None`、`time_horizon_days: int | None` — 交易计划
- `confidence: float`(0.0 – 1.0)、`rationale: str`、`warning_message: str | None`(parser 走 fallback 路径时会填)

结构化结果同时会写进 `AgentState.final_trade_recommendation` 与 state log JSON,让 `reflect` 与 `backtest` subcommand 之后能重新组回来。

`response_language` 是来自 `ResponseLanguage` `Literal` 的 BCP 47 tag(`zh-TW`、`zh-CN`、`en-US`、`ja-JP`、`ko-KR`、`de-DE`),挑最接近你希望 agent 用的语言即可。

`TradingAgentsGraph.propagate` 也接受一个可选的 `on_message` callback(`Callable[[AnyMessage], None]`),每收到一则 streamed LangGraph 消息就会调用一次 — 想接自己的 renderer 时很好用,内置的 CLI / TUI 也是用这个 hook 来喂 Rich panel。

`llm_provider` 是 `langchain.chat_models.init_chat_model` 的 registry key(`openai`、`anthropic`、`google_genai`、`xai`、`openrouter`、`ollama`、`huggingface`、`litellm`);`deep_think_llm` / `quick_think_llm` 则填该 provider 接受的 model name(`gpt-5`、`claude-sonnet-4-6`、`gemini-3-pro-preview`、`grok-4` 等)。

`max_recur_limit` 下限是 **30** — P0 加入 Situation Summariser 节点后多了一个 superstep,原本 25 的下限已经不够跑最小轮数的 topology。CLI / TUI 默认仍是 100。

`response_language` 可控制所有 agent prompt 要求的回复语言。没有 exchange suffix 的 ticker 会自动通过 Yahoo Finance Search 解析。台股请直接传股票代码,例如 `2330`、`2408`、`8069`;也支持明确的 Yahoo Finance symbol,例如 `2330.TW`、`8069.TWO`、`AAPL`、`TSM`。

```python
config = TradingAgentsConfig(
    llm_provider="openai",
    deep_think_llm="gpt-5",
    quick_think_llm="gpt-5-mini",
    max_debate_rounds=1,
    max_risk_discuss_rounds=1,
    max_recur_limit=100,
    response_language="zh-TW",
)

ta = TradingAgentsGraph(config=config)
state, recommendation = ta.propagate("2330", "2024-05-10")
```

#### Backtest

同一条 `propagate()` 流程也可以通过 `Backtester` Pydantic model 在日期 grid 上跑(或上面提到的 `tradingagents backtest` CLI):

```python
from tradingagents.backtest import BacktestConfig, Backtester

cfg = BacktestConfig(
    tickers=["GOOG", "2330.TW"],
    start_date="2024-01-01",
    end_date="2024-06-30",
    frequency="weekly",  # 或 "daily"
    horizon_days=5,  # 每个 decision 的 mark-to-market 窗口
    budget_cap_usd=25.0,  # 达上限会 raise CostBudgetExceeded 并停 loop
    reflect_after_each_trade=True,
    trading_config=config,
)
report = Backtester(config=cfg).run()
print(report.sharpe, report.hit_rate, report.estimated_cost_usd)
```

Harness 对每个 ticker 各建一个全新的 `TradingAgentsGraph`(per-run state 是 mutable),共用同一个 `CostTracker` callback 让 budget 跨 ticker 累计,把每个 decision 对应到 15 年 OHLCV cache 的下一个 bar 算实际 return,并可选择把 realised return 喂回 `reflect_and_remember`,让 memory 像在 production 一样在 backtest 期间长出来。传 `dry_run=True` 会切到 in-memory `StubChatModel` 做 harness 验证。

## 📁 项目结构

```
src/
└── tradingagents/
    ├── agents/           # Agent 实现
    │   ├── analysts/     # 市场、新闻、News Sentiment、基本面分析师
    │   ├── managers/     # 研究 & 投资组合管理者
    │   ├── preprocessors/# Situation Summariser 节点(analyst reports → BM25 query)
    │   ├── researchers/  # 多头 & 空头研究员
    │   ├── risk_mgmt/    # 风险管理 Agents
    │   ├── trader/       # 交易员 Agent
    │   ├── prompts/      # 所有 agent prompt(.md 模板)
    │   └── utils/        # 共用 Agent 工具(memory、tools、state)
    ├── dataflows/        # yfinance + Google News RSS 数据采集
    ├── graph/            # LangGraph 交易图配置
    │   ├── trading_graph.py    # 主要的 TradingAgentsGraph orchestrator
    │   ├── signal_processing.py# TradeRecommendation 解析(JSON / canonical-line 优先级)
    │   └── reflection.py       # 交易后 reflector
    ├── interface/        # CLI / TUI / backtest / reflect 实现
    │   ├── cli.py        # fire 驱动的 flag runner(run_cli)
    │   ├── tui/          # textual 版交互 app
    │   ├── backtest.py   # fire 驱动的 backtest runner(run_backtest)
    │   ├── reflect.py    # fire 驱动的 reflect runner(run_reflect)
    │   ├── display.py    # rich 版的 LangChain message renderer + TradeRecommendation 面板
    │   └── help.py       # 取代 fire pager 的 rich help
    ├── backtest.py       # Backtester 引擎、CostTracker、StubChatModel、BacktestReport
    ├── llm.py            # Chat model 构造(init_chat_model wrapper + reasoning_effort mapping)
    ├── config.py         # TradingAgentsConfig schema 与全局 singleton
    ├── __init__.py       # Top-level public API(TradingAgentsConfig、TradingAgentsGraph)
    └── __main__.py       # Console script 入口(fire dispatcher 加 rich help)
```

## 🤖 Agent 工作流程

TradingAgents 通过 LangGraph `StateGraph` 编排 **12 个 LLM agent** 加上 **3 个支持组件**,每次执行会依序跑过 4 个 phase,中间用 Situation Summariser 串接,所有状态(各类 report、debate transcript、trade decision)都通过一个共用的 Pydantic `AgentState` 在所有节点之间传递。

### Phase 1 — 分析师团队(数据采集)

四位 analyst 依序执行。每位 analyst 的 LLM 都会 `bind_tools(...)` 到一组以 `yfinance` 为 backend 的 `@tool` 函数,并与其专属的 `ToolNode` 配对,持续 loop 直到没有新的 tool call 为止。每位 analyst 结束之后会经过一个 `Msg Clear` node,它会发出 `RemoveMessage` 并补上一个 `HumanMessage("Continue")` placeholder(这是为了维持 Anthropic 对最后一则消息必须是 human 的要求)。

| Analyst                    | LLM 绑定的 tools                                                                                                                                                                  | 写入 state            |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| **Market Analyst**         | `get_stock_data`, `get_indicators`, `get_dividends_splits`                                                                                                                        | `market_report`       |
| **News Sentiment Analyst** | `get_news`                                                                                                                                                                        | `sentiment_report`    |
| **News Analyst**           | `get_news`, `get_global_news`, `get_insider_transactions`, `get_market_context`, `get_earnings_calendar`                                                                          | `news_report`         |
| **Fundamentals Analyst**   | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_analyst_ratings`, `get_institutional_holders`, `get_short_interest`, `get_dividends_splits` | `fundamentals_report` |

所有历史 tool 都会按 reporting-lag 调整后的 `as_of` 日期做 point-in-time 过滤,确保 back-test 不会泄漏未来财报。yfinance 没有历史档案的 tool(`get_institutional_holders`、`get_short_interest`)在 back-dated `curr_date` 会故意回 `[NO_DATA]` sentinel,而不是默默把当下 snapshot 漏出去。

Market Analyst 可挑选的 technical indicator(**一次选 6 – 8 个**):`close_50_sma`、`close_200_sma`、`close_10_ema`、`macd`、`macds`、`macdh`、`rsi`、`mfi`、`cci`、`wr`、`kdjk`、`kdjd`、`stochrsi`、`adx`、`pdi`、`boll`、`boll_ub`、`boll_lb`、`atr`、`supertrend`、`supertrend_ub`、`supertrend_lb`、`vwma`、`obv`。Market Analyst 被要求挑均衡的趋势 / 动能 / 波动 / 成交量信号;当底层 history 少于 50 bar 时,输出会带 `DATA WARNING` 前言(长周期指标不可靠的提醒)。

### Phase 1.5 — Situation Summariser

最后一个 analyst 的 Msg Clear 之后,单一的 **Situation Summariser** 节点(quick-thinking LLM)把 4 份 analyst report 蒸馏成 ≤400-token 的结构化 snapshot。snapshot 写进 `state.situation_summary`,并成为之后每一次 memory 查询的 BM25 retrieval query — 取代原本 10-20 KB、太散漫无法 surface 出相关历史 situation 的 `combined_reports` query。

### Phase 2 — 研究辩论

- **Bull Researcher** 与 **Bear Researcher** 会按照 `max_debate_rounds`(默认为 1,等于双方各讲一轮)互相辩论,依据 "上一位发言者是谁" 决定下一个轮到谁。每位 researcher 从自己的 `FinancialSituationMemory` 取出 top-k BM25 matches,同时看到过去 situation snapshot 与当时学到的 lesson(不只是 lesson 字符串)。
- 终止条件:当 `count >= 2 * max_debate_rounds` 时,graph 会 route 到 **Research Manager**(deep-thinking LLM),由它汇整整场辩论、产出 `investment_plan`,并填入 `investment_debate_state.judge_decision`。

### Phase 3 — Trader

**Trader**(quick-thinking LLM)会读取 `investment_plan` 以及来自 `trader_memory` 的 top-k 历史经验,输出 `trader_investment_plan`。它的输出必须以 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` 结尾。

### Phase 4 — 风险辩论

三位 risk debator 以固定顺序轮流发言:**Aggressive → Conservative → Neutral → Aggressive → …**,循环 `max_risk_discuss_rounds` 轮(默认为 1,代表每种立场各发言一次)。终止条件:当 `count >= 3 * max_risk_discuss_rounds` 时,graph route 到 **Risk Judge**(由 `create_risk_manager` 建立的 deep-thinking LLM),由它写入 `final_trade_decision`。Risk Judge 的 prompt 要求输出一个 fenced ```` ```json ```` 块包含 `TradeRecommendation` schema(signal、size_fraction、target_price、stop_loss、time_horizon_days、confidence、rationale、warning_message),加上 canonical 的 `FINAL TRANSACTION PROPOSAL: **<signal>**` 行。确定性的 `SignalProcessor` 会解析这两个输出 — 当两者不一致时 canonical line 优先,JSON 不完整或解析失败时会优雅 fallback 并填上保守预设值(size 0.5、confidence 0.5)。

### 支持组件

- **Situation Summariser** — 把 analyst reports 蒸馏成 BM25 retrieval query,让 memory lookup 在 lexical 上保持精准。
- **FinancialSituationMemory** — 采 BM25Okapi 做 retrieval,整个流程共有 5 个 instance(bull、bear、trader、invest_judge、risk_manager)。纯 lexical 相似度,不需要任何 embedding API。每笔 match 同时 surface 过去 situation snapshot 与 lesson — agent 自己判断类比是否成立再决定要不要套用 lesson。
- **Reflector** — 交易结果出炉之后,调用 `TradingAgentsGraph.reflect_and_remember(returns_losses)` 会针对 5 个 memory 各跑一轮 post-trade reflection。reflector 输出结构化 rubric(每个 factor 1 – 5 分 + 整体 reasoning + outcome quality + lesson category enum),让 backtest 工具可以聚合 reasoning 轨迹。

### 流程示意

```
START
  │
  ▼
[Market Analyst ⇄ tools_market] → Msg Clear
  │
  ▼
[News Sentiment Analyst ⇄ tools_social] → Msg Clear
  │
  ▼
[News Analyst ⇄ tools_news] → Msg Clear
  │
  ▼
[Fundamentals Analyst ⇄ tools_fundamentals] → Msg Clear
  │
  ▼
Situation Summariser  →  state.situation_summary
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
Risk Judge  →  SignalProcessor (TradeRecommendation)  →  END
```

每次执行的 log 会写入 `results/<股票代码>/`:`full_states_log_<股票代码>_<日期>.json`(v2 schema,外层为 `{"schema_version": 2, "runs": {...}}`)、`conversation_log_<股票代码>_<日期>.txt`、`conversation_log_<股票代码>_<日期>.json`(base path 由 `TradingAgentsConfig.results_dir` 决定,默认为 `./results`)。`reflect` CLI 读档时会自动把 v1 log 转成 v2 shape,旧 run 仍可重新处理。

## 🤝 贡献

有关开发说明（包含文档、测试和 Docker 服务等），请参阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 欢迎 Issue/PR
- 请遵循代码风格（ruff、类型）
- PR 标题遵循 Conventional Commits

## 📄 授权

MIT — 详见 `LICENSE`。
