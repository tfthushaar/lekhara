"""The rules pack: every statutory rate, threshold and deadline, stored as dated data.

Engines never hold a legal number as a literal. They ask the pack for the rule in
force on a date, and every rule carries its legal basis and how reliable its
source is, so the product can show both next to any figure it produces.
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any


class SourceQuality(StrEnum):
    OFFICIAL = "official"
    """Statute, notification or an official government reply."""

    SECONDARY = "secondary"
    """Consistent secondary commentary; confirm against the official text."""

    UNSETTLED = "unsettled"
    """Sources conflict or the law is unclear; a professional must confirm."""

    UNVERIFIED = "unverified"
    """A single secondary source or a reported figure; must be confirmed before use."""

    LEKHARA_DEFAULT = "lekhara_default"
    """A Lekhara setting, not a legal rule. Customers can change it."""


@dataclass(frozen=True)
class Rule:
    key: str
    value: Any
    title: str
    basis: str
    source_quality: SourceQuality
    confirm_against: str
    effective_from: date
    effective_to: date | None = None
    note: str = ""

    def applies_on(self, on: date) -> bool:
        if on < self.effective_from:
            return False
        return self.effective_to is None or on <= self.effective_to


class RuleNotFound(KeyError):
    pass


@dataclass(frozen=True)
class RulesPack:
    state: str
    version: str
    rules: tuple[Rule, ...]

    def __post_init__(self) -> None:
        by_key: dict[str, list[Rule]] = {}
        for rule in self.rules:
            by_key.setdefault(rule.key, []).append(rule)
        for key, versions in by_key.items():
            versions.sort(key=lambda r: r.effective_from)
            for earlier, later in zip(versions, versions[1:], strict=False):
                if earlier.effective_to is None or earlier.effective_to >= later.effective_from:
                    raise ValueError(f"Rule {key!r} has overlapping periods")

    def get(self, key: str, on: date) -> Rule:
        for rule in self.rules:
            if rule.key == key and rule.applies_on(on):
                return rule
        raise RuleNotFound(f"No rule {key!r} in force on {on.isoformat()} in pack {self.state}")

    def value(self, key: str, on: date) -> Any:
        return self.get(key, on).value

    def rule_keys(self) -> list[str]:
        return sorted({rule.key for rule in self.rules})
