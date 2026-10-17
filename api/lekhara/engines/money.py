"""Money truth engine: a project's real numbers from its append-only ledger.

Spend moves through stages. A commitment is a work order or purchase order
(variations and cancellations are further signed entries). Incurred is cost the
project has taken on: a certified RA bill, an accepted invoice, a land or fee
payment booked. Paid is cash out. Retention and mobilisation advances are
tracked separately because they are future cash.

Anticipated final cost (AFC) per line is the larger of the revised budget, what
is committed and what is incurred. Contingency absorbs overruns on other lines;
whatever contingency is left is assumed spent, which keeps the forecast prudent.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from lekhara.money import ZERO, percent
from lekhara.rules import RulesPack


class Category(StrEnum):
    LAND = "land"
    APPROVALS = "approvals"
    CONSTRUCTION = "construction"
    FINANCE = "finance"
    MARKETING = "marketing"
    OVERHEADS = "overheads"
    CONTINGENCY = "contingency"


class ReraHead(StrEnum):
    """The two parts of estimated project cost in RERA certificates."""

    LAND = "land"
    DEVELOPMENT = "development"


class EntryKind(StrEnum):
    COMMITMENT = "commitment"
    INCURRED = "incurred"
    PAID = "paid"
    RETENTION_HELD = "retention_held"
    RETENTION_RELEASED = "retention_released"
    ADVANCE_PAID = "advance_paid"
    ADVANCE_RECOVERED = "advance_recovered"


@dataclass(frozen=True)
class CostLine:
    id: str
    code: str
    name: str
    category: Category
    rera_head: ReraHead
    original_budget: Decimal
    revised_budget: Decimal

    @property
    def is_contingency(self) -> bool:
        return self.category == Category.CONTINGENCY


@dataclass(frozen=True)
class Entry:
    cost_line_id: str
    kind: EntryKind
    amount: Decimal
    on: date


@dataclass(frozen=True)
class LinePosition:
    line: CostLine
    committed: Decimal
    incurred: Decimal
    paid: Decimal
    retained: Decimal
    advance_outstanding: Decimal
    anticipated_final_cost: Decimal
    cost_to_complete: Decimal
    overrun: Decimal

    @property
    def over_committed_by(self) -> Decimal:
        return max(self.committed - self.line.revised_budget, ZERO)


@dataclass(frozen=True)
class HeadTotals:
    estimated_cost: Decimal
    incurred: Decimal
    paid: Decimal


@dataclass(frozen=True)
class Alert:
    code: str
    title: str
    detail: str
    amount: Decimal | None = None
    line_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectPosition:
    as_of: date
    lines: tuple[LinePosition, ...]
    budget: Decimal
    committed: Decimal
    incurred: Decimal
    paid: Decimal
    retained: Decimal
    advance_outstanding: Decimal
    contingency_budget: Decimal
    contingency_used: Decimal
    contingency_remaining: Decimal
    overrun_beyond_contingency: Decimal
    anticipated_final_cost: Decimal
    cost_to_complete: Decimal
    land: HeadTotals
    development: HeadTotals
    certified_progress_pct: Decimal | None
    development_incurred_pct: Decimal
    alerts: tuple[Alert, ...]


def _sums(entries: list[Entry]) -> dict[EntryKind, Decimal]:
    totals: dict[EntryKind, Decimal] = defaultdict(lambda: ZERO)
    for entry in entries:
        totals[entry.kind] += entry.amount
    return totals


def project_position(
    lines: list[CostLine],
    entries: list[Entry],
    *,
    as_of: date,
    certified_progress_pct: Decimal | None,
    rules: RulesPack,
) -> ProjectPosition:
    """The project's position on `as_of`, using only entries dated on or before it."""
    line_ids = {line.id for line in lines}
    by_line: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        if entry.cost_line_id not in line_ids:
            raise ValueError(f"Entry refers to unknown cost line {entry.cost_line_id!r}")
        if entry.on <= as_of:
            by_line[entry.cost_line_id].append(entry)

    regular: list[LinePosition] = []
    contingency_lines = [line for line in lines if line.is_contingency]
    for line in lines:
        if line.is_contingency:
            continue
        s = _sums(by_line[line.id])
        committed = s[EntryKind.COMMITMENT]
        incurred = s[EntryKind.INCURRED]
        afc = max(line.revised_budget, committed, incurred)
        regular.append(
            LinePosition(
                line=line,
                committed=committed,
                incurred=incurred,
                paid=s[EntryKind.PAID],
                retained=s[EntryKind.RETENTION_HELD] - s[EntryKind.RETENTION_RELEASED],
                advance_outstanding=s[EntryKind.ADVANCE_PAID] - s[EntryKind.ADVANCE_RECOVERED],
                anticipated_final_cost=afc,
                cost_to_complete=afc - incurred,
                overrun=afc - line.revised_budget,
            )
        )

    overruns = sum((p.overrun for p in regular), ZERO)
    contingency_budget = sum((line.revised_budget for line in contingency_lines), ZERO)
    contingency_used = min(overruns, contingency_budget)
    contingency_remaining = contingency_budget - contingency_used
    overrun_beyond = max(overruns - contingency_budget, ZERO)

    contingency_positions: list[LinePosition] = []
    for line in contingency_lines:
        share = line.revised_budget / contingency_budget if contingency_budget else ZERO
        remaining = (contingency_remaining * share).quantize(Decimal("0.01"))
        contingency_positions.append(
            LinePosition(
                line=line,
                committed=ZERO,
                incurred=ZERO,
                paid=ZERO,
                retained=ZERO,
                advance_outstanding=ZERO,
                anticipated_final_cost=remaining,
                cost_to_complete=remaining,
                overrun=ZERO,
            )
        )

    ordered = {p.line.id: p for p in [*regular, *contingency_positions]}
    positions = tuple(ordered[line.id] for line in lines)

    def head(h: ReraHead) -> HeadTotals:
        ps = [p for p in positions if p.line.rera_head == h]
        return HeadTotals(
            estimated_cost=sum((p.anticipated_final_cost for p in ps), ZERO),
            incurred=sum((p.incurred for p in ps), ZERO),
            paid=sum((p.paid for p in ps), ZERO),
        )

    land = head(ReraHead.LAND)
    development = head(ReraHead.DEVELOPMENT)
    afc_total = land.estimated_cost + development.estimated_cost
    incurred_total = sum((p.incurred for p in positions), ZERO)
    development_incurred_pct = percent(development.incurred, development.estimated_cost)

    alerts = _alerts(
        regular=regular,
        contingency_budget=contingency_budget,
        contingency_remaining=contingency_remaining,
        overrun_beyond=overrun_beyond,
        development_incurred_pct=development_incurred_pct,
        certified_progress_pct=certified_progress_pct,
        rules=rules,
        as_of=as_of,
    )

    return ProjectPosition(
        as_of=as_of,
        lines=positions,
        budget=sum((line.revised_budget for line in lines), ZERO),
        committed=sum((p.committed for p in positions), ZERO),
        incurred=incurred_total,
        paid=sum((p.paid for p in positions), ZERO),
        retained=sum((p.retained for p in positions), ZERO),
        advance_outstanding=sum((p.advance_outstanding for p in positions), ZERO),
        contingency_budget=contingency_budget,
        contingency_used=contingency_used,
        contingency_remaining=contingency_remaining,
        overrun_beyond_contingency=overrun_beyond,
        anticipated_final_cost=afc_total,
        cost_to_complete=afc_total - incurred_total,
        land=land,
        development=development,
        certified_progress_pct=certified_progress_pct,
        development_incurred_pct=development_incurred_pct,
        alerts=tuple(alerts),
    )


def _alerts(
    *,
    regular: list[LinePosition],
    contingency_budget: Decimal,
    contingency_remaining: Decimal,
    overrun_beyond: Decimal,
    development_incurred_pct: Decimal,
    certified_progress_pct: Decimal | None,
    rules: RulesPack,
    as_of: date,
) -> list[Alert]:
    alerts: list[Alert] = []

    if certified_progress_pct is not None:
        gap = development_incurred_pct - certified_progress_pct
        if gap >= rules.value("money.cost_ahead_points", as_of):
            alerts.append(
                Alert(
                    code="cost_ahead_of_progress",
                    title="Spending is running ahead of construction",
                    detail=(
                        f"{development_incurred_pct}% of development cost is incurred, but "
                        f"certified progress is {certified_progress_pct}%. The K-RERA auditor "
                        "and the escrow bank compare these two figures."
                    ),
                )
            )

    if overrun_beyond > 0:
        alerts.append(
            Alert(
                code="overrun_beyond_contingency",
                title="Overruns are larger than the contingency",
                detail="The anticipated final cost is now above the total budget.",
                amount=overrun_beyond,
            )
        )
    elif contingency_budget > 0:
        low_share = rules.value("money.contingency_low_share", as_of)
        if contingency_remaining < contingency_budget * low_share:
            alerts.append(
                Alert(
                    code="contingency_low",
                    title="Contingency is running low",
                    detail="Most of the contingency has been used by overruns on other lines.",
                    amount=contingency_remaining,
                )
            )

    for p in regular:
        if p.over_committed_by > 0:
            alerts.append(
                Alert(
                    code="over_committed",
                    title=f"{p.line.name}: committed above budget",
                    detail="Work orders and purchase orders on this line exceed its budget.",
                    amount=p.over_committed_by,
                    line_ids=(p.line.id,),
                )
            )

    return alerts
