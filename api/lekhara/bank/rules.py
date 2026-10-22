"""Bank rules a firm writes: words in a statement line's narration, and what such a line is.

Lekhara already remembers each payer once someone places them. Rules go further, for what
repeats every month in a builder's statements: "NEFT PRIYA SHARMA" is the buyer of A-101,
"SWEEP TO FD" is left out, "GST ON CHARGES" is bank charges in the RERA account. A rule looks
for its words the four ways filing rules do (`matching`), can be kept to money in or out and to
an amount range, and applies to every statement of its project, or of every project. Rules are
tried in their order and the first that fits a line decides it; a choice made for the line
itself still comes first.

The idea comes from Firefly III's rules.
"""

from decimal import Decimal, InvalidOperation

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from lekhara.bank.plan import RuleRef
from lekhara.bank.service import statement_of
from lekhara.matching import HOW
from lekhara.matching import normal as _normal
from lekhara.models import BankRule, BankStatement, Project, Unit
from lekhara.money import inr
from lekhara.services import ServiceError
from lekhara.storage import Storage

ACTIONS = {
    "unit": "A payment from the buyer of a unit",
    "not_buyer": "Not a buyer's payment",
    "leave_out": "Leave the line out",
    "deposit": "A deposit into the RERA account",
    "interest": "Interest from the bank",
    "withdrawal": "A withdrawal from the RERA account",
    "charges": "Bank charges",
}
DIRECTIONS = {"any": "Money in or out", "in": "Money in", "out": "Money out"}
FIXED_DIRECTION = {
    "unit": "in",
    "not_buyer": "in",
    "deposit": "in",
    "interest": "in",
    "withdrawal": "out",
    "charges": "out",
}
"""Most actions make sense one way only: a buyer pays in, a bank charges out."""
TRY_LIMIT = 10


def _amount(value, label: str) -> Decimal | None:
    text = str(value or "").replace(",", "").replace("₹", "").strip()
    if not text:
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ServiceError(f"{label} is not an amount.") from None
    if amount < 0:
        raise ServiceError(f"{label} cannot be below zero.")
    return amount.quantize(Decimal("0.01"))


def _check(session: Session, project: Project, fields: dict) -> dict:
    name = (fields.get("name") or "").strip()
    words = (fields.get("words") or "").strip()
    how = fields.get("how") or "all"
    action = fields.get("action") or ""
    if not name:
        raise ServiceError("Name the rule, so you know it again.")
    if not _normal(words):
        raise ServiceError("Give the words to look for in the narration.")
    if len(words) > 200:
        raise ServiceError("Keep the words to a few, under 200 characters.")
    if how not in HOW:
        raise ServiceError("Choose how to look for the words.")
    if action not in ACTIONS:
        raise ServiceError("Choose what a line with these words is.")
    direction = FIXED_DIRECTION.get(action) or fields.get("direction") or "any"
    if direction not in DIRECTIONS:
        raise ServiceError("Choose money in, money out, or either.")
    low = _amount(fields.get("min_amount"), "The smallest amount")
    high = _amount(fields.get("max_amount"), "The largest amount")
    if low is not None and high is not None and low > high:
        raise ServiceError("The smallest amount is more than the largest.")
    every = bool(fields.get("every_project"))
    unit_id = None
    if action == "unit":
        unit = session.get(Unit, fields.get("unit_id") or "")
        if unit is None or unit.project_id != project.id or not unit.booked:
            raise ServiceError("Choose a sold unit in this project.")
        if every:
            raise ServiceError("A rule that names a unit is for that unit's project only.")
        unit_id = unit.id
    return {
        "name": name[:100],
        "words": words,
        "how": how,
        "direction": direction,
        "min_amount": low,
        "max_amount": high,
        "action": action,
        "unit_id": unit_id,
        "project_id": None if every else project.id,
    }


def rules_for(session: Session, project: Project) -> list[BankRule]:
    """The rules a project's statements follow, in order: its own and the firm's for every
    project."""
    return list(
        session.scalars(
            select(BankRule)
            .where(
                BankRule.organization_id == project.organization_id,
                or_(BankRule.project_id == project.id, BankRule.project_id.is_(None)),
            )
            .order_by(BankRule.position, BankRule.created_at)
        )
    )


def ref(rule: BankRule) -> RuleRef:
    return RuleRef(
        name=rule.name,
        words=rule.words,
        how=rule.how,
        direction=rule.direction,
        action=rule.action,
        unit_id=rule.unit_id,
        min_amount=rule.min_amount,
        max_amount=rule.max_amount,
    )


def _rule(session: Session, project: Project, rule_id: str) -> BankRule:
    rule = session.get(BankRule, rule_id)
    if rule is None or rule not in rules_for(session, project):
        raise ServiceError("Rule not found.", 404)
    return rule


def create_rule(session: Session, project: Project, fields: dict, user_id: str) -> BankRule:
    values = _check(session, project, fields)
    last = session.scalar(
        select(func.coalesce(func.max(BankRule.position), 0)).where(
            BankRule.organization_id == project.organization_id
        )
    )
    rule = BankRule(
        organization_id=project.organization_id, position=last + 1, created_by=user_id, **values
    )
    session.add(rule)
    session.commit()
    return rule


def delete_rule(session: Session, project: Project, rule_id: str) -> None:
    session.delete(_rule(session, project, rule_id))
    session.commit()


def move_up(session: Session, project: Project, rule_id: str) -> None:
    """Moves a rule one place earlier, so it is tried before the one above it."""
    rule = _rule(session, project, rule_id)
    order = rules_for(session, project)
    at = order.index(rule)
    if at == 0:
        return
    above = order[at - 1]
    if above.position == rule.position:
        rule.position = above.position - 1
    else:
        above.position, rule.position = rule.position, above.position
    session.commit()


def lines_fitting(
    session: Session,
    storage: Storage,
    project: Project,
    fields: dict,
    passwords: tuple[str, ...] = (),
) -> tuple[int, list[dict]]:
    """How many lines in the project's statements a rule would fit, and the first few, to try
    it before saving. A line in two overlapping statements counts once."""
    values = _check(session, project, {**fields, "name": fields.get("name") or "Trying"})
    rule = RuleRef(**{k: values[k] for k in (
        "words", "how", "direction", "action", "unit_id", "min_amount", "max_amount"
    )}, name="Trying")  # fmt: skip
    seen: set[str] = set()
    found: list[dict] = []
    rows = session.scalars(
        select(BankStatement)
        .where(BankStatement.project_id == project.id, BankStatement.status != "undone")
        .order_by(BankStatement.created_at.desc())
        .limit(20)
    )
    count = 0
    for row in rows:
        try:
            statement = statement_of(storage, row, passwords)
        except ServiceError:
            continue  # one that can no longer be read (its password changed) is passed over
        for line in statement.lines:
            if line.key in seen or not rule.fits(line):
                continue
            seen.add(line.key)
            count += 1
            if len(found) < TRY_LIMIT:
                found.append({
                    "on": line.on.isoformat(),
                    "narration": line.narration,
                    "amount": inr(line.amount),
                    "direction": "in" if line.is_credit else "out",
                })  # fmt: skip
    return count, found


def view(session: Session, project: Project, *, can_edit: bool) -> dict:
    units = {
        u.id: u
        for u in session.scalars(
            select(Unit).where(Unit.project_id == project.id, Unit.booked).order_by(Unit.label)
        )
    }

    def then(rule: BankRule) -> str:
        if rule.action == "unit":
            unit = units.get(rule.unit_id)
            if unit is None:
                return "A payment from the buyer of a unit no longer sold"
            buyer = f", {unit.buyer_name}" if unit.buyer_name else ""
            return f"A payment from the buyer of {unit.label}{buyer}"
        return ACTIONS[rule.action]

    def which(rule: BankRule) -> str:
        parts = [DIRECTIONS[rule.direction]]
        if rule.min_amount is not None and rule.max_amount is not None:
            parts.append(f"from {inr(rule.min_amount)} to {inr(rule.max_amount)}")
        elif rule.min_amount is not None:
            parts.append(f"of {inr(rule.min_amount)} or more")
        elif rule.max_amount is not None:
            parts.append(f"up to {inr(rule.max_amount)}")
        return " ".join(parts)

    return {
        "can_edit": can_edit,
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "words": r.words,
                "how": r.how,
                "how_label": HOW[r.how],
                "lines": which(r),
                "then": then(r),
                "action": r.action,
                "every_project": r.project_id is None,
            }
            for r in rules_for(session, project)
        ],
        "hows": [{"value": k, "label": v} for k, v in HOW.items()],
        "actions": [{"value": k, "label": v} for k, v in ACTIONS.items()],
        "directions": [{"value": k, "label": v} for k, v in DIRECTIONS.items()],
        "units": [{"id": u.id, "label": u.label, "buyer": u.buyer_name} for u in units.values()],
    }
