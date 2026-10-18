"""Bank statements in the database: the uploaded file, the review, the builder's choices,
apply and undo.

The file is kept in storage and read again for each review, so a builder can upload a
statement, say which account it is, match the payments Lekhara could not, and apply it later.
The account and each payer are remembered for the next statement. The RERA account's
movements are append-only, so undoing adds reversing entries; buyer payments are removed.
"""

import json
from collections import OrderedDict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lekhara.bank.narration import payer_key
from lekhara.bank.plan import Context, KnownReceipt, KnownTxn, Plan, make_plan
from lekhara.bank.reader import Statement, read_statement
from lekhara.models import (
    BankAccount,
    BankPayer,
    BankStatement,
    EscrowTxn,
    Organization,
    Project,
    Receipt,
    TallyLink,
    Unit,
    utcnow,
)
from lekhara.services import ServiceError
from lekhara.storage import Storage
from lekhara.tally.plan import UnitRef

UNDO_DAYS = 30
ROLES = ("rera", "collections")
_cache: "OrderedDict[str, Statement]" = OrderedDict()


def _read(filename: str, data: bytes, passwords: tuple[str, ...] = ()) -> Statement:
    return read_statement(filename, data, passwords)


def statement_passwords(session: Session, settings, organization_id: str) -> tuple[str, ...]:
    """The passwords the firm has given for its banks' emailed statements."""
    from lekhara.models import StatementPassword
    from lekhara.secretbox import unseal

    rows = session.scalars(
        select(StatementPassword).where(StatementPassword.organization_id == organization_id)
    )
    return tuple(p for p in (unseal(settings, r.sealed) for r in rows) if p)


def statement_of(
    storage: Storage, row: BankStatement, passwords: tuple[str, ...] = ()
) -> Statement:
    cached = _cache.get(row.storage_key)
    if cached is None:
        cached = _read(row.filename, storage.get(row.storage_key), passwords)
        _cache[row.storage_key] = cached
        while len(_cache) > 8:
            _cache.popitem(last=False)
    return cached


def _account(session: Session, project_id: str, number: str | None) -> BankAccount | None:
    if not number:
        return None
    return session.scalars(
        select(BankAccount).where(
            BankAccount.project_id == project_id, BankAccount.number == number
        )
    ).first()


def upload(
    session: Session,
    storage: Storage,
    project: Project,
    *,
    filename: str,
    data: bytes,
    user_id: str | None,
    passwords: tuple[str, ...] = (),
) -> BankStatement:
    statement = _read(filename, data, passwords)
    key = storage.put(data)
    _cache[key] = statement
    known = _account(session, project.id, statement.account)
    opts = {"role": known.role, "buyers_pay_here": known.buyers_pay_here} if known else {}
    row = BankStatement(
        organization_id=project.organization_id,
        project_id=project.id,
        filename=filename[:300],
        storage_key=key,
        bank=statement.bank,
        account_number=statement.account,
        period_from=statement.period_from,
        period_to=statement.period_to,
        lines=len(statement.lines),
        options=json.dumps(opts),
        created_by_user_id=user_id,
    )
    session.add(row)
    session.commit()
    return row


def get_statement(session: Session, statement_id: str) -> BankStatement:
    row = session.get(BankStatement, statement_id)
    if row is None:
        raise ServiceError("Statement not found.", 404)
    return row


def project_statements(session: Session, project: Project) -> list[BankStatement]:
    return list(
        session.scalars(
            select(BankStatement)
            .where(BankStatement.project_id == project.id)
            .order_by(BankStatement.created_at.desc())
            .limit(20)
        )
    )


def options(row: BankStatement) -> dict:
    return json.loads(row.options or "{}")


def context(session: Session, project: Project, row: BankStatement, as_of: date) -> Context:
    opts = options(row)
    org = session.get(Organization, project.organization_id)
    units = tuple(
        UnitRef(u.id, u.label, u.buyer_name)
        for u in session.scalars(
            select(Unit).where(Unit.project_id == project.id, Unit.booked).order_by(Unit.label)
        )
    )
    payers = {
        p.payer: p.unit_id
        for p in session.scalars(select(BankPayer).where(BankPayer.project_id == project.id))
    }
    tally_units = {
        link.ledger: link.target_id
        for link in session.scalars(
            select(TallyLink).where(TallyLink.project_id == project.id, TallyLink.role == "unit")
        )
        if link.target_id
    }
    receipts = tuple(
        KnownReceipt(r.id, r.unit_id, r.received_on, r.amount, r.source_ref)
        for r in session.scalars(select(Receipt).where(Receipt.project_id == project.id))
    )
    escrow = tuple(
        KnownTxn(t.id, t.kind, t.txn_date, t.amount, t.reference)
        for t in session.scalars(select(EscrowTxn).where(EscrowTxn.project_id == project.id))
    )
    own = tuple(
        n
        for n in (org.name if org else None, org.legal_name if org else None, project.spv_name)
        if n
    )
    return Context(
        as_of=as_of,
        role=opts.get("role"),
        buyers_pay_here=bool(opts.get("buyers_pay_here")),
        units=units,
        payers=payers,
        tally_units=tally_units,
        choices=opts.get("lines", {}),
        own_names=own,
        receipts=receipts,
        escrow=escrow,
    )


def review(
    session: Session,
    storage: Storage,
    row: BankStatement,
    as_of: date,
    passwords: tuple[str, ...] = (),
) -> tuple[Statement, Plan]:
    project = session.get(Project, row.project_id)
    statement = statement_of(storage, row, passwords)
    return statement, make_plan(statement, context(session, project, row, as_of))


def set_options(
    session: Session,
    storage: Storage,
    row: BankStatement,
    body: dict,
    *,
    as_of: date,
    passwords: tuple[str, ...] = (),
) -> None:
    if row.status == "undone" or (row.status == "applied" and body.get("role") is not None):
        raise ServiceError("This statement has already been applied.")
    opts = options(row)
    if body.get("role") is not None:
        if body["role"] not in ROLES:
            raise ServiceError("Choose the RERA designated account or the collection account.")
        opts["role"] = body["role"]
    if body.get("buyers_pay_here") is not None:
        opts["buyers_pay_here"] = bool(body["buyers_pay_here"])

    statement = statement_of(storage, row, passwords)
    lines = {line.key: line for line in statement.lines}
    units = {
        u.id
        for u in session.scalars(select(Unit).where(Unit.project_id == row.project_id, Unit.booked))
    }
    chosen = dict(opts.get("lines", {}))
    for key, value in (body.get("lines") or {}).items():
        if key not in lines:
            raise ServiceError("That line is not in this statement.")
        if value in (None, ""):
            chosen.pop(key, None)
        elif value in ("not_buyer", "skip") or value in units:
            chosen[key] = value
        else:
            raise ServiceError("Choose a sold unit in this project.")
    opts["lines"] = chosen
    row.options = json.dumps(opts)

    # Remember the account, and each payer the builder placed, for the next statement.
    if opts.get("role") and row.account_number:
        account = _account(session, row.project_id, row.account_number)
        if account is None:
            account = BankAccount(project_id=row.project_id, number=row.account_number)
            session.add(account)
        account.bank = row.bank
        account.role = opts["role"]
        account.buyers_pay_here = bool(opts.get("buyers_pay_here"))
        account.updated_at = utcnow()
    _, plan = review(session, storage, row, as_of, passwords)
    by_key = {p.key: p for p in plan.lines}
    for key, value in (body.get("lines") or {}).items():
        p = by_key.get(key)
        name = payer_key(p.payer) if p else None
        if not name or p.loan or value in (None, "", "skip"):
            continue
        remembered = session.scalars(
            select(BankPayer).where(BankPayer.project_id == row.project_id, BankPayer.payer == name)
        ).first()
        if remembered is None:
            remembered = BankPayer(project_id=row.project_id, payer=name)
            session.add(remembered)
        remembered.payer_name = (p.payer or "")[:200]
        remembered.unit_id = None if value == "not_buyer" else value
        remembered.updated_at = utcnow()
    session.commit()


def apply(
    session: Session,
    storage: Storage,
    row: BankStatement,
    *,
    as_of: date,
    user_id: str | None,
    passwords: tuple[str, ...] = (),
) -> dict:
    if row.status not in ("review", "applied"):
        raise ServiceError("This statement was undone.")
    if not options(row).get("role"):
        raise ServiceError("Say which account this statement is for first.")
    _, plan = review(session, storage, row, as_of, passwords)
    # Applying again brings in what has been placed since: the rest is already in.
    result: dict[str, list[str]] = {"receipts": [], "escrow": []}
    if row.status == "applied":
        result = json.loads(row.result or "{}")
        if not plan.to_add:
            raise ServiceError("Everything in this statement is already in.")
    for p in plan.lines:
        if p.receipt and not p.receipt_exists:
            receipt = Receipt(
                project_id=row.project_id,
                unit_id=p.unit_id,
                amount=p.credit,
                received_on=p.on,
                reference=(p.reference or "")[:200] or None,
                source_ref=p.key,
            )
            session.add(receipt)
            session.flush()
            result["receipts"].append(receipt.id)
        if p.escrow_kind and not p.escrow_exists:
            txn = EscrowTxn(
                project_id=row.project_id,
                kind=p.escrow_kind,
                amount=p.amount,
                txn_date=p.on,
                reference=p.key,
            )
            session.add(txn)
            session.flush()
            result["escrow"].append(txn.id)
    if row.status != "applied":
        row.applied_at = utcnow()
    row.status = "applied"
    row.result = json.dumps(result)
    session.commit()
    return result


def can_undo(row: BankStatement) -> bool:
    return (
        row.status == "applied"
        and row.applied_at is not None
        and utcnow() - row.applied_at <= timedelta(days=UNDO_DAYS)
    )


def undo(session: Session, row: BankStatement) -> None:
    if not can_undo(row):
        raise ServiceError(f"A statement can be undone for {UNDO_DAYS} days after it is applied.")
    result = json.loads(row.result or "{}")
    for receipt_id in result.get("receipts", []):
        receipt = session.get(Receipt, receipt_id)
        if receipt is not None:
            session.delete(receipt)
    for txn_id in result.get("escrow", []):
        txn = session.get(EscrowTxn, txn_id)
        if txn is not None:
            session.add(
                EscrowTxn(
                    project_id=txn.project_id,
                    kind=txn.kind,
                    amount=-txn.amount,
                    txn_date=txn.txn_date,
                    reference=f"undo:{txn.reference}",
                )
            )
    row.status = "undone"
    row.undone_at = utcnow()
    session.commit()
