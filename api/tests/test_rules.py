from datetime import date
from decimal import Decimal

import pytest

from horus.rules import KARNATAKA, Rule, RuleNotFound, RulesPack, SourceQuality


def _rule(value: str, start: date, end: date | None = None) -> Rule:
    return Rule(
        key="x.rate",
        value=Decimal(value),
        title="A rate",
        basis="Test",
        source_quality=SourceQuality.OFFICIAL,
        confirm_against="Test",
        effective_from=start,
        effective_to=end,
    )


def test_rule_in_force_on_date_is_returned() -> None:
    pack = RulesPack(
        state="T",
        version="1",
        rules=(
            _rule("0.28", date(2019, 4, 1), date(2025, 9, 21)),
            _rule("0.18", date(2025, 9, 22)),
        ),
    )
    assert pack.value("x.rate", date(2024, 1, 1)) == Decimal("0.28")
    assert pack.value("x.rate", date(2025, 9, 22)) == Decimal("0.18")


def test_missing_rule_raises() -> None:
    pack = RulesPack(state="T", version="1", rules=(_rule("0.18", date(2025, 1, 1)),))
    with pytest.raises(RuleNotFound):
        pack.value("x.rate", date(2024, 1, 1))
    with pytest.raises(RuleNotFound):
        pack.value("y.rate", date(2025, 6, 1))


def test_overlapping_periods_are_rejected() -> None:
    with pytest.raises(ValueError, match="overlapping"):
        RulesPack(
            state="T",
            version="1",
            rules=(_rule("0.28", date(2019, 4, 1)), _rule("0.18", date(2025, 9, 22))),
        )


def test_every_karnataka_rule_explains_itself() -> None:
    for rule in KARNATAKA.rules:
        assert rule.title, rule.key
        assert rule.basis, rule.key
        assert rule.confirm_against, rule.key


def test_karnataka_core_values() -> None:
    today = date(2026, 10, 17)
    assert KARNATAKA.value("escrow.deposit_share", today) == Decimal("0.70")
    assert KARNATAKA.value("gst.procurement.min_registered_share", today) == Decimal("0.80")
    assert KARNATAKA.value("it.s43ca.tolerance", today) == Decimal("0.10")
    assert KARNATAKA.value("it.msme.days_with_agreement", today) == 45


def test_horus_settings_apply_on_any_date() -> None:
    old = date(2018, 1, 1)
    for rule in KARNATAKA.rules:
        if rule.source_quality == SourceQuality.HORUS_DEFAULT:
            assert rule.applies_on(old), rule.key
