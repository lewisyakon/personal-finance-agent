"""Deterministic checks that monetary claims originate from Tool evidence."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from app.agent.contracts import GroundingResult

_CLAIM = re.compile(r"(?<![\d.])-?\d+(?:\.\d+)?\s*(?:元|分|%|％|笔)")
_VALUE_AND_UNIT = re.compile(r"(-?\d+(?:\.\d+)?)\s*(元|分|%|％|笔)")


def _collect_numbers(
    value: Any,
    path: tuple[str, ...],
    minor: set[int],
    percentages: set[Decimal],
    counts: set[int],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _collect_numbers(item, (*path, str(key)), minor, percentages, counts)
        return
    if isinstance(value, list):
        for item in value:
            _collect_numbers(item, path, minor, percentages, counts)
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return

    joined = ".".join(path)
    if "_minor" in joined and isinstance(value, int):
        minor.add(value)
    if "percent" in joined:
        percentages.add(Decimal(str(value)).quantize(Decimal("0.01")))
    if "count" in joined or path[-1:] == ("total",):
        if isinstance(value, int):
            counts.add(value)


def validate_numeric_grounding(answer: str, tool_results: list[dict[str, Any]]) -> GroundingResult:
    minor: set[int] = set()
    percentages: set[Decimal] = set()
    counts: set[int] = set()
    for result in tool_results:
        _collect_numbers(result.get("data"), (), minor, percentages, counts)

    unsupported: list[str] = []
    for claim in _CLAIM.findall(answer):
        match = _VALUE_AND_UNIT.fullmatch(claim.strip())
        if not match:
            continue
        raw, unit = match.groups()
        try:
            number = Decimal(raw)
        except InvalidOperation:
            unsupported.append(claim)
            continue
        valid = False
        if unit == "元":
            converted = number * 100
            valid = converted == converted.to_integral_value() and int(converted) in minor
        elif unit == "分":
            valid = number == number.to_integral_value() and int(number) in minor
        elif unit in {"%", "％"}:
            valid = number.quantize(Decimal("0.01")) in percentages
        elif unit == "笔":
            valid = number == number.to_integral_value() and int(number) in counts
        if not valid:
            unsupported.append(claim)
    return GroundingResult(valid=not unsupported, unsupported_claims=unsupported)
