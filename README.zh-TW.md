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

🚀 **TradingAgents** 是一個多 Agent LLM 金融交易框架，利用大型語言模型模擬分析師團隊、研究辯論和投資組合管理決策，以提供股票交易分析。

其他語言: [English](README.md) | [繁體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md)

## ✨ 重點特色

- 基於 **LangGraph** 建構，提供穩健的多 Agent 編排機制
- 多 Agent 架構：分析師團隊 → **Situation Summariser** → 研究團隊 → 交易員 → 風險管理 → 投資組合管理
- **結構化交易建議** — Risk Judge 輸出強型別 `TradeRecommendation`(signal、size、target、stop、horizon、confidence、rationale),由一段 JSON 區塊加上 canonical `FINAL TRANSACTION PROPOSAL` 行解析得到
- **Backtest 工具** — `tradingagents backtest` 在日期 grid 上驅動 `propagate()`,依 cache 過的 OHLCV 算實際 return,回報 Sharpe / hit-rate / drawdown,並支援 `--dry-run` stub-LLM 模式做 harness 驗證
- 透過 `langchain.chat_models.init_chat_model` 建構 LLM，使用獨立的 `llm_provider` 欄位加上 model name 指定模型,支援 OpenAI、Anthropic、Google Gemini、xAI (Grok)、OpenRouter、Ollama、HuggingFace、LiteLLM
- 統一的 `reasoning_effort` 旋鈕（`low / medium / high / xhigh / max`）會 map 到各 provider 的 native 參數（Anthropic `effort`、OpenAI `reasoning_effort`、Google `thinking_level`）
- 市場數據全由 `yfinance` 提供:OHLCV、基本面、技術指標、新聞、內部人交易、analyst ratings、earnings calendar、institutional holders、short interest、dividends / splits,以及區域 macro 上下文(local index、^TNX、^VIX)
- Google News 路由依地區自動選擇 — exchange suffix(`.TW`、`.HK`、`.T`、`.DE`、...)決定 `hl` / `gl` / `ceid`,非美股標的可以拿到當地語言的新聞覆蓋
- 所有歷史 tool 都做 point-in-time 過濾 — 帶 reporting-lag 調整後的 `as_of` 日期,back-test 不會洩漏未來財報
- 基於 Pydantic 的設定系統，提供嚴格型別檢查與驗證
- 分析結果自動儲存至 `results/` 目錄並依團隊分資料夾(state log schema 帶版本號,reflect CLI 內建 v1 → v2 migration)
- 現代 `src/` 佈局，完整型別註解
- 透過 `uv` 進行快速依賴管理
- Pre-commit 套件鏈：ruff、mdformat、codespell、mypy、uv hooks
- Pytest + coverage、MkDocs Material 文件系統

## 🚀 快速開始

```bash
git clone https://github.com/Mai0313/TradingAgents.git
cd TradingAgents
make uv-install               # 安裝 uv（僅需一次）
uv sync                       # 安裝依賴
cp .env.example .env          # 設定 API 金鑰
```

### 設定 API 金鑰

編輯 `.env` 並設定您的 LLM 供應商金鑰：

```bash
# LLM 供應商（設定您使用的那一個）
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
XAI_API_KEY=...
OPENROUTER_API_KEY=...
```

### 使用方式

#### Command line / 互動模式

套件提供 `tradingagents` console script,內含四個 subcommand:

```bash
uv run tradingagents tui                     # 互動式 questionary 流程
uv run tradingagents cli                     # 全部使用預設值執行
uv run tradingagents cli --ticker AAPL \
    --deep_think_llm gpt-5 \
    --quick_think_llm gpt-5-mini             # 透過 flag 覆寫
uv run tradingagents reflect --ticker AAPL --date 2024-05-10 --returns 0.032   # 交易後反思
uv run tradingagents backtest --tickers GOOG,2330.TW \
    --start 2024-01-01 --end 2024-06-30 \
    --frequency weekly --horizon-days 5 \
    --budget-cap-usd 25                      # 在 LLM 成本上限內跑 grid backtest
uv run tradingagents backtest --tickers GOOG \
    --start 2024-01-01 --end 2024-06-30 --dry-run   # 秒驗 harness、$0 成本
uv run tradingagents --help                  # rich 渲染的 top-level help
uv run tradingagents cli --help              # rich 渲染的 per-command flag 列表
```

`tradingagents tui` 會用一連串 questionary prompt 帶你走完所有參數(ticker、日期、provider、models、辯論輪數、analyst 選擇等);`tradingagents cli` 是同一條流程,但完全用 command-line flag 驅動,方便寫進 shell script 或 CI。`tradingagents reflect` 會把過去 run 的 state log 重新跑 post-trade reflector,把學到的教訓寫進 BM25 memory。`tradingagents backtest` 會在日期 grid 上反覆呼叫 `propagate()`,用下一個 bar 的 close 做 mark-to-market,回報 Sharpe / hit rate / expectancy / drawdown,並依 token-aware cost tracker 強制 `--budget-cap-usd`。加 `--dry-run` 會切到 in-memory stub LLM,直接回 canned 的 `TradeRecommendation` payload — 拿來在不燒 API 預算的情況下驗證 harness 對真實 cached OHLCV 的處理。兩條互動路徑跑 graph 時都會把 LangGraph 的 agent 訊息透過 Rich panel 串流出來(prose 用 Markdown 渲染、tool 輸出做 JSON pretty-print、payload 過長會自動截斷)。`python -m tradingagents <subcommand>` 也走同一條 dispatcher。

#### 程式呼叫

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

`propagate()` 回傳 `(AgentState, TradeRecommendation)`。`TradeRecommendation` 是一個 Pydantic model:

- `signal: Literal["BUY", "SELL", "HOLD"]` — 標準方向
- `size_fraction: float`(0.0 – 1.0)— 部位大小占可用資金的比例
- `target_price: float | None`、`stop_loss: float | None`、`time_horizon_days: int | None` — 交易計畫
- `confidence: float`(0.0 – 1.0)、`rationale: str`、`warning_message: str | None`(parser 走 fallback 路徑時會填)

結構化結果同時會寫進 `AgentState.final_trade_recommendation` 與 state log JSON,讓 `reflect` 與 `backtest` subcommand 之後能重新組回來。

`response_language` 是來自 `ResponseLanguage` `Literal` 的 BCP 47 tag(`zh-TW`、`zh-CN`、`en-US`、`ja-JP`、`ko-KR`、`de-DE`),挑最接近你希望 agent 用的語言即可。

`TradingAgentsGraph.propagate` 也接受一個可選的 `on_message` callback(`Callable[[AnyMessage], None]`),每收到一則 streamed LangGraph 訊息就會呼叫一次 — 想接自己的 renderer 時很好用,內建的 CLI / TUI 也是用這個 hook 來餵 Rich panel。

`llm_provider` 是 `langchain.chat_models.init_chat_model` 的 registry key(`openai`、`anthropic`、`google_genai`、`xai`、`openrouter`、`ollama`、`huggingface`、`litellm`);`deep_think_llm` / `quick_think_llm` 則填該 provider 接受的 model name(`gpt-5`、`claude-sonnet-4-6`、`gemini-3-pro-preview`、`grok-4` 等)。

`max_recur_limit` 下限是 **30** — P0 加入 Situation Summariser 節點後多了一個 superstep,原本 25 的下限已經不夠跑最小輪數的 topology。CLI / TUI 預設仍是 100。

`response_language` 可控制所有 agent prompt 要求的回覆語言。沒有 exchange suffix 的 ticker 會自動透過 Yahoo Finance Search 解析。台股請直接傳股票代號,例如 `2330`、`2408`、`8069`;也支援明確的 Yahoo Finance symbol,例如 `2330.TW`、`8069.TWO`、`AAPL`、`TSM`。

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

同一條 `propagate()` 流程也可以透過 `Backtester` Pydantic model 在日期 grid 上跑(或上面提到的 `tradingagents backtest` CLI):

```python
from tradingagents.backtest import BacktestConfig, Backtester

cfg = BacktestConfig(
    tickers=["GOOG", "2330.TW"],
    start_date="2024-01-01",
    end_date="2024-06-30",
    frequency="weekly",  # 或 "daily"
    horizon_days=5,  # 每個 decision 的 mark-to-market 視窗
    budget_cap_usd=25.0,  # 達上限會 raise CostBudgetExceeded 並停 loop
    reflect_after_each_trade=True,
    trading_config=config,
)
report = Backtester(config=cfg).run()
print(report.sharpe, report.hit_rate, report.estimated_cost_usd)
```

Harness 對每個 ticker 各建一個全新的 `TradingAgentsGraph`(per-run state 是 mutable),共用同一個 `CostTracker` callback 讓 budget 跨 ticker 累計,把每個 decision 對應到 15 年 OHLCV cache 的下一個 bar 算實際 return,並可選擇把 realised return 餵回 `reflect_and_remember`,讓 memory 像在 production 一樣在 backtest 期間長出來。傳 `dry_run=True` 會切到 in-memory `StubChatModel` 做 harness 驗證。

## 📁 專案結構

```
src/
└── tradingagents/
    ├── agents/           # Agent 實作
    │   ├── analysts/     # 市場、新聞、News Sentiment、基本面分析師
    │   ├── managers/     # 研究 & 投資組合管理者
    │   ├── preprocessors/# Situation Summariser 節點(analyst reports → BM25 query)
    │   ├── researchers/  # 多頭 & 空頭研究員
    │   ├── risk_mgmt/    # 風險管理 Agents
    │   ├── trader/       # 交易員 Agent
    │   ├── prompts/      # 所有 agent prompt(.md 模板)
    │   └── utils/        # 共用 Agent 工具(memory、tools、state)
    ├── dataflows/        # yfinance + Google News RSS 數據擷取
    ├── graph/            # LangGraph 交易圖設定
    │   ├── trading_graph.py    # 主要的 TradingAgentsGraph orchestrator
    │   ├── signal_processing.py# TradeRecommendation 解析(JSON / canonical-line 優先序)
    │   └── reflection.py       # 交易後 reflector
    ├── interface/        # CLI / TUI / backtest / reflect 實作
    │   ├── cli.py        # fire 驅動的 flag runner(run_cli)
    │   ├── tui/          # textual 版互動 app
    │   ├── backtest.py   # fire 驅動的 backtest runner(run_backtest)
    │   ├── reflect.py    # fire 驅動的 reflect runner(run_reflect)
    │   ├── display.py    # rich 版本的 LangChain message renderer + TradeRecommendation 面板
    │   └── help.py       # 取代 fire pager 的 rich help
    ├── backtest.py       # Backtester 引擎、CostTracker、StubChatModel、BacktestReport
    ├── llm.py            # Chat model 構造(init_chat_model wrapper + reasoning_effort mapping)
    ├── config.py         # TradingAgentsConfig schema 與全域 singleton
    ├── __init__.py       # Top-level public API(TradingAgentsConfig、TradingAgentsGraph)
    └── __main__.py       # Console script 入口(fire dispatcher 加 rich help)
```

## 🤖 Agent 工作流程

TradingAgents 透過 LangGraph `StateGraph` 編排 **12 個 LLM agent** 加上 **3 個支援元件**,每次執行會依序跑過 4 個 phase,中間用 Situation Summariser 串接,所有狀態(各類 report、debate transcript、trade decision)都透過一個共用的 Pydantic `AgentState` 在所有節點之間傳遞。

### Phase 1 — 分析師團隊(資料蒐集)

預設四位 analyst 依序執行；`selected_analysts` 可以只跑其中一部分。每位 analyst 的 LLM 都會依 central tool registry `bind_tools(...)` 到一組以 `yfinance` 為 backend 的 `@tool` 函式,並與其專屬的 `ToolNode` 配對,持續 loop 直到沒有新的 tool call 為止。每位 analyst 結束之後會經過一個 `Msg Clear` node,它會發出 `RemoveMessage` 並補上一個 `HumanMessage("Continue")` placeholder(這是為了維持 Anthropic 對最後一則訊息必須是 human 的要求)。

| Analyst                    | LLM 綁定的 tools                                                                                                                                                                  | 寫入 state            |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| **Market Analyst**         | `get_stock_data`, `get_indicators`, `get_dividends_splits`                                                                                                                        | `market_report`       |
| **News Sentiment Analyst** | `get_news`                                                                                                                                                                        | `sentiment_report`    |
| **News Analyst**           | `get_news`, `get_global_news`, `get_insider_transactions`, `get_market_context`, `get_earnings_calendar`                                                                          | `news_report`         |
| **Fundamentals Analyst**   | `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_analyst_ratings`, `get_institutional_holders`, `get_short_interest`, `get_dividends_splits` | `fundamentals_report` |

所有歷史 tool 都會依 reporting-lag 調整後的 `as_of` 日期做 point-in-time 過濾,確保 back-test 不會洩漏未來財報。yfinance 沒有歷史檔案的 tool(`get_institutional_holders`、`get_short_interest`)在 back-dated `curr_date` 會故意回 `[NO_DATA]` sentinel,而不是默默把當下 snapshot 漏出去。

Market Analyst 可挑選的 technical indicator(**一次選 6 – 8 個**):`close_50_sma`、`close_200_sma`、`close_10_ema`、`macd`、`macds`、`macdh`、`rsi`、`mfi`、`cci`、`wr`、`kdjk`、`kdjd`、`stochrsi`、`adx`、`pdi`、`boll`、`boll_ub`、`boll_lb`、`atr`、`supertrend`、`supertrend_ub`、`supertrend_lb`、`vwma`、`obv`。Market Analyst 被要求挑均衡的趨勢 / 動能 / 波動 / 成交量訊號;當底層 history 少於 50 bar 時,輸出會帶 `DATA WARNING` 前言(長週期指標不可靠的提醒)。

### Phase 1.5 — Situation Summariser

最後一個 selected analyst 的 Msg Clear 之後,單一的 **Situation Summariser** 節點(quick-thinking LLM)把 selected analyst reports 蒸餾成 ≤400-token 的結構化 snapshot。若某個 analyst 沒有被選取,缺少的 report 會被視為 unavailable,不能 invent。snapshot 寫進 `state.situation_summary`,並成為之後每一次 memory 查詢的 BM25 retrieval query — 取代原本 10-20 KB、太散漫無法 surface 出相關歷史 situation 的 `combined_reports` query。

### Phase 2 — 研究辯論

- **Bull Researcher** 與 **Bear Researcher** 會依照 `max_debate_rounds`(預設為 1,等於雙方各講一輪)互相辯論,依據「上一位發言者是誰」決定下一個輪到誰。每位 researcher 從自己的 `FinancialSituationMemory` 取出 top-k BM25 matches,同時看到過去 situation snapshot 與當時學到的 lesson(不只是 lesson 字串)。
- 終止條件:當 `count >= 2 * max_debate_rounds` 時,graph 會 route 到 **Research Manager**(deep-thinking LLM),由它彙整整場辯論、產出 `investment_plan`,並填入 `investment_debate_state.judge_decision`。

### Phase 3 — Trader

**Trader**(quick-thinking LLM)會讀取 `investment_plan` 以及來自 `trader_memory` 的 top-k 歷史經驗,輸出 `trader_investment_plan`。它的輸出必須以 `FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL**` 結尾。

### Phase 4 — 風險辯論

三位 risk debator 以固定順序輪流發言:**Aggressive → Conservative → Neutral → Aggressive → …**,循環 `max_risk_discuss_rounds` 輪(預設為 1,代表每種立場各發言一次)。終止條件:當 `count >= 3 * max_risk_discuss_rounds` 時,graph route 到 **Risk Judge**(由 `create_risk_manager` 建立的 deep-thinking LLM),由它寫入 `final_trade_decision`。Risk Judge 的 prompt 要求輸出一個 fenced ```` ```json ```` 區塊包含 `TradeRecommendation` schema(signal、size_fraction、target_price、stop_loss、time_horizon_days、confidence、rationale、warning_message),加上 canonical 的 `FINAL TRANSACTION PROPOSAL: **<signal>**` 行。決定性的 `SignalProcessor` 會解析這兩個輸出 — 當兩者不一致時 canonical line 優先,JSON 不完整或解析失敗時會優雅 fallback 並填上保守預設值(size 0.5、confidence 0.5)。

### 支援元件

- **Situation Summariser** — 把 analyst reports 蒸餾成 BM25 retrieval query,讓 memory lookup 在 lexical 上保持精準。
- **FinancialSituationMemory** — 採 BM25Okapi 做 retrieval,整個流程共有 5 個 instance(bull、bear、trader、invest_judge、risk_manager)。純 lexical 相似度,不需要任何 embedding API。每筆 match 同時 surface 過去 situation snapshot 與 lesson — agent 自己判斷類比是否成立再決定要不要套用 lesson。
- **Reflector** — 交易結果出爐之後,呼叫 `TradingAgentsGraph.reflect_and_remember(returns_losses)` 會針對 5 個 memory 各跑一輪 post-trade reflection。reflector 輸出結構化 rubric(每個 factor 1 – 5 分 + 整體 reasoning + outcome quality + lesson category enum),讓 backtest 工具可以聚合 reasoning 軌跡。

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

每次執行的 log 會寫入 `results/<股票代碼>/`:`full_states_log_<股票代碼>_<日期>.json`(v2 schema,外層為 `{"schema_version": 2, "runs": {...}}`)、`conversation_log_<股票代碼>_<日期>.txt`、`conversation_log_<股票代碼>_<日期>.json`(base path 由 `TradingAgentsConfig.results_dir` 決定,預設為 `./results`)。`reflect` CLI 讀檔時會自動把 v1 log 轉成 v2 shape,舊 run 仍可重新處理。

## 🤝 貢獻

有關開發說明（包含文件、測試和 Docker 服務等），請參閱 [CONTRIBUTING.md](CONTRIBUTING.md)。

- 歡迎 Issue/PR
- 請遵循程式風格（ruff、型別）
- PR 標題遵循 Conventional Commits

## 📄 授權

MIT — 詳見 `LICENSE`。
