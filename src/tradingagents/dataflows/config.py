from tradingagents import default_config

# Use default config but allow it to be overridden
# Using a mutable list as a container to avoid global statement warnings
_config_container: list[dict[str, object] | None] = [None]


def _get_config_ref() -> dict[str, object] | None:
    return _config_container[0]


def _set_config_ref(value: dict[str, object] | None) -> None:
    _config_container[0] = value


def initialize_config() -> None:
    """Initialize the configuration with default values."""
    if _config_container[0] is None:
        _config_container[0] = default_config.DEFAULT_CONFIG.copy()


def set_config(config: dict[str, object]) -> None:
    """Update the configuration with custom values."""
    if _config_container[0] is None:
        _config_container[0] = default_config.DEFAULT_CONFIG.copy()
    cfg = _config_container[0]
    if cfg is None:
        raise RuntimeError("Configuration not initialized")
    cfg.update(config)


def get_config() -> dict[str, object]:
    """Get the current configuration."""
    if _config_container[0] is None:
        initialize_config()
    cfg = _config_container[0]
    if cfg is None:
        raise RuntimeError("Configuration not initialized")
    return cfg.copy()


# Initialize with default config
initialize_config()
