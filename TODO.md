此專案是克隆自 `TradingAgents`
我目前已經將這個代碼庫透過我的另外一個 [template](https://github.com/Mai0313/repo_template) 進行了重構


- [ ] `./tradingagents` 要移動到 `./src` 目錄下, `./cli` 則要移動到 `./src/tradingagents` 目錄底下
- [ ] `./pyproject.toml` 中的一些項目可能需要修改
    - `project.scripts`
    - `tool.hatch.build`
    - `tool.hatch.build.targets.wheel`
    - `tool.poe.tasks`
- [ ] `README.md`, `README.zh-CN.md`, and `README.zh-TW.md` 需要對應更新
