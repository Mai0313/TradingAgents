from tradingagents.default_config import TradingAgentsConfig

_config_container: list[TradingAgentsConfig | None] = [None]


def set_config(config: TradingAgentsConfig) -> None:
    """Set the configuration."""
    _config_container[0] = config


def get_config() -> TradingAgentsConfig:
    """Get the current configuration."""
    cfg = _config_container[0]
    if cfg is None:
        raise RuntimeError(
            "TradingAgentsConfig has not been initialized. "
            "Construct a TradingAgentsConfig and pass it to TradingAgentsGraph "
            "(or call set_config) before accessing the global config."
        )
    return cfg
