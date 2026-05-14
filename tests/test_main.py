import sys
from typing import Any

import pytest

from tradingagents import __main__ as main_module


def test_main_without_args_prints_app_help(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any]] = []
    monkeypatch.setattr(sys, "argv", ["tradingagents"])
    monkeypatch.setattr(main_module, "Console", lambda: "console")
    monkeypatch.setattr(
        main_module, "print_app_help", lambda console, commands: calls.append(("app", console))
    )

    main_module.main()

    assert calls == [("app", "console")]


def test_main_help_command_prints_command_help(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any, str]] = []
    monkeypatch.setattr(sys, "argv", ["tradingagents", "help", "cli"])
    monkeypatch.setattr(main_module, "Console", lambda: "console")
    monkeypatch.setattr(
        main_module,
        "print_command_help",
        lambda console, name, fn: calls.append(("command", console, name)),
    )

    main_module.main()

    assert calls == [("command", "console", "cli")]


def test_main_subcommand_help_prints_command_help(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Any, str]] = []
    monkeypatch.setattr(sys, "argv", ["tradingagents", "backtest", "--help"])
    monkeypatch.setattr(main_module, "Console", lambda: "console")
    monkeypatch.setattr(
        main_module,
        "print_command_help",
        lambda console, name, fn: calls.append(("command", console, name)),
    )

    main_module.main()

    assert calls == [("command", "console", "backtest")]


def test_main_dispatches_to_fire_for_non_help_invocations(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[dict[str, Any], str]] = []
    monkeypatch.setattr(sys, "argv", ["tradingagents", "cli", "--ticker", "AAPL"])
    monkeypatch.setattr(main_module, "Console", lambda: "console")
    monkeypatch.setattr(
        main_module.fire, "Fire", lambda commands, name: calls.append((commands, name))
    )

    main_module.main()

    assert calls == [(main_module.COMMANDS, "tradingagents")]
