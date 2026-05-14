# TradingAgents/graph/signal_processing.py

import re
import json
from typing import Any, Literal, cast
import logging

from pydantic import Field, BaseModel, ConfigDict, field_validator

logger = logging.getLogger(__name__)

TradeSignal = Literal["BUY", "SELL", "HOLD"]
_DECISION_PATTERN = re.compile(r"\b(BUY|SELL|HOLD)\b", re.IGNORECASE)
_FINAL_PATTERN = re.compile(
    r"FINAL\s+TRANSACTION\s+PROPOSAL\s*:\s*(?:\*\*)?\s*(BUY|SELL|HOLD)\s*(?:\*\*)?", re.IGNORECASE
)
# Capture the LAST fenced ``` json ... ``` block in the response. Risk Judges
# often quote example payloads earlier in their prose; the canonical answer is
# the final block, mirroring how `_FINAL_PATTERN` already prefers the last
# `FINAL TRANSACTION PROPOSAL` line.
_JSON_BLOCK_PATTERN = re.compile(r"```\s*json\s*\n(.*?)\n\s*```", re.IGNORECASE | re.DOTALL)


class TradeRecommendation(BaseModel):
    """Structured Risk-Judge recommendation, persisted on AgentState.

    Replaces the bare ``Literal["BUY","SELL","HOLD"]`` returned by the old
    ``process_signal`` so downstream consumers (backtester, CLI, TUI) can
    reason about size, target, horizon, and confidence — not just the
    direction.
    """

    model_config = ConfigDict(extra="ignore")

    signal: TradeSignal = Field(
        ..., title="Signal", description="Canonical direction: BUY, SELL, or HOLD."
    )
    size_fraction: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Size Fraction",
        description="Position size as a fraction of the available capital (0.0-1.0).",
    )
    target_price: float | None = Field(
        default=None,
        title="Target Price",
        description="Price target for the trade in the issuer's reporting currency, or None.",
    )
    stop_loss: float | None = Field(
        default=None,
        title="Stop Loss",
        description="Stop-loss price in the issuer's reporting currency, or None.",
    )
    time_horizon_days: int | None = Field(
        default=None,
        ge=1,
        title="Time Horizon (days)",
        description="Expected holding period in calendar days, or None.",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        title="Confidence",
        description="Subjective confidence in this recommendation (0.0-1.0).",
    )
    rationale: str = Field(
        default="",
        title="Rationale",
        description="One-paragraph rationale, anchored in analyst reports + debate.",
    )
    warning_message: str | None = Field(
        default=None,
        title="Warning Message",
        description=(
            "Set by the parser when fallback paths fire (missing JSON, "
            "conflicting signal vs canonical line, etc.). The CLI / TUI surfaces this."
        ),
    )

    @field_validator("signal", mode="before")
    @classmethod
    def _normalise_signal(cls, value: object) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return cast("str", value)


def _flatten_text(payload: str | list[str | dict[str, Any]] | None) -> str:
    """Flatten multi-modal LangChain content into a plain string for regex matching."""
    if isinstance(payload, list):
        return "\n".join(
            item.get("text", "") if isinstance(item, dict) else str(item) for item in payload
        )
    return str(payload or "")


def extract_trade_signal(full_signal: str | list[str | dict[str, Any]] | None) -> TradeSignal:
    """Extract a canonical BUY/SELL/HOLD decision without another LLM call.

    Always returns one of BUY/SELL/HOLD; logs a warning and defaults to
    HOLD when the input is empty, missing the canonical
    ``FINAL TRANSACTION PROPOSAL`` line, or contains conflicting signals.
    Never raises — a malformed risk-judge response must not abort a paid
    LangGraph run after every other agent has already produced output.
    """
    text = _flatten_text(full_signal)

    final_matches = [match.upper() for match in _FINAL_PATTERN.findall(text)]
    if final_matches:
        # The last FINAL marker wins because risk judges often quote the
        # trader's earlier proposal ("the trader proposed BUY but I
        # recommend SELL") before stating their own conclusion.
        return cast("TradeSignal", final_matches[-1])

    decisions = [match.upper() for match in _DECISION_PATTERN.findall(text)]
    if not decisions:
        logger.warning("Risk judge output contained no BUY/SELL/HOLD token; defaulting to HOLD.")
        return "HOLD"

    distinct = set(decisions)
    if len(distinct) == 1:
        return cast("TradeSignal", decisions[-1])

    logger.warning(
        "Risk judge output is ambiguous (signals: %s); defaulting to HOLD.", sorted(distinct)
    )
    return "HOLD"


def _parse_json_block(text: str) -> dict[str, Any] | None:
    """Extract and parse the LAST ```json``` fenced block from ``text``."""
    matches = _JSON_BLOCK_PATTERN.findall(text)
    if not matches:
        return None
    raw = matches[-1].strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Risk judge JSON block failed to parse (%s); falling back to text-only signal.", exc
        )
        return None
    if not isinstance(parsed, dict):
        logger.warning("Risk judge JSON block was not an object; ignoring.")
        return None
    return parsed


def extract_trade_recommendation(
    full_signal: str | list[str | dict[str, Any]] | None,
) -> TradeRecommendation:
    """Parse the risk-judge output into a structured :class:`TradeRecommendation`.

    Resolution order:

    1. The canonical ``FINAL TRANSACTION PROPOSAL`` line — its direction
       always wins, since that's what the regex contract has trained the
       LLM on and what every test in the suite pins.
    2. The last fenced ``` ```json``` block in the response — fills in
       size, target, stop, horizon, confidence, rationale.
    3. When the JSON block is missing or malformed, default everything to
       conservative midpoints (size 0.5, confidence 0.5) and surface a
       ``warning_message`` so the CLI / backtester can flag the run.

    Never raises. The function is on the hot path of every paid LangGraph
    run; a malformed risk-judge response must degrade gracefully rather
    than abort.
    """
    text = _flatten_text(full_signal)
    canonical_signal = extract_trade_signal(text)
    json_payload = _parse_json_block(text)

    if json_payload is None:
        return TradeRecommendation(
            signal=canonical_signal,
            warning_message=(
                "No parseable JSON block found in risk-judge output; "
                "using defaults (size_fraction=0.5, confidence=0.5)."
            ),
        )

    # Filter out unknown / non-schema keys before validating so a verbose
    # LLM that adds extra fields does not break this path.
    allowed_keys = set(TradeRecommendation.model_fields)
    cleaned = {k: v for k, v in json_payload.items() if k in allowed_keys}
    cleaned["signal"] = canonical_signal  # canonical line is authoritative
    try:
        recommendation = TradeRecommendation(**cleaned)
    except Exception as exc:
        logger.warning(
            "Risk judge JSON block validated to invalid TradeRecommendation (%s); "
            "falling back to defaults.",
            exc,
        )
        return TradeRecommendation(
            signal=canonical_signal,
            warning_message=(
                f"JSON block parsed but failed schema validation ({exc!s}); "
                "using defaults (size_fraction=0.5, confidence=0.5)."
            ),
        )

    json_signal_raw = json_payload.get("signal")
    if isinstance(json_signal_raw, str):
        json_signal = json_signal_raw.strip().upper()
        if json_signal in {"BUY", "SELL", "HOLD"} and json_signal != canonical_signal:
            recommendation = recommendation.model_copy(
                update={
                    "warning_message": (
                        f"JSON block signal ({json_signal}) disagreed with canonical "
                        f"FINAL TRANSACTION PROPOSAL ({canonical_signal}); canonical wins."
                    )
                }
            )

    return recommendation


class SignalProcessor(BaseModel):
    """Processes trading signals deterministically to extract actionable decisions."""

    def process_signal(self, full_signal: str) -> TradeRecommendation:
        """Process a full trading signal into a structured recommendation.

        Args:
            full_signal (str): The full signal text generated by the Risk Judge.

        Returns:
            TradeRecommendation: Structured decision (BUY/SELL/HOLD plus
            size, target, stop, horizon, confidence, rationale). Defaults
            to HOLD with conservative sizing when the input is empty or
            ambiguous; ``warning_message`` is populated on any fallback.
        """
        return extract_trade_recommendation(full_signal)
