from tradingagents.default_config import TradingAgentsConfig

_config_container: list[TradingAgentsConfig | None] = [None]


def initialize_config() -> None:
    """Initialize the configuration with default values."""
    if _config_container[0] is None:
        _config_container[0] = TradingAgentsConfig()


def set_config(config: TradingAgentsConfig) -> None:
    """Set the configuration."""
    _config_container[0] = config


def get_config() -> TradingAgentsConfig:
    """Get the current configuration."""
    if _config_container[0] is None:
        initialize_config()
    cfg = _config_container[0]
    if cfg is None:
        raise RuntimeError("Configuration not initialized")
    return cfg


initialize_config()
