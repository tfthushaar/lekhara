"""What to do with each supplier's invoice in the GST portal's Invoice Management System (IMS).

Since October 2024 a buyer can accept, reject or keep pending each invoice and note its
suppliers report. GSTR-2B is drawn up on the 14th of the next month from what was accepted and
what was left untouched (taken as accepted); actions can be changed, and GSTR-2B computed again,
until GSTR-3B is filed. From Lekhara's check of a GSTR-2A or GSTR-2B against the firm's bills,
each invoice gets a suggestion and the reason for it:

- accept:  the bill is in Lekhara with the same amounts (in this project or another);
- pending: the amounts differ, or there is no bill yet (the goods or service may not have
           arrived, and credit needs them received); decide once it is clear;
- reject:  the same invoice was in an earlier month's return, so taking it again would count
           the credit twice;
- check:   a credit or debit note, which only the person who agreed to it can judge.

The idea comes from the purchase reconciliation in india-compliance for ERPNext. Which records
may be kept pending has changed since IMS began (some credit notes, for one period, from
October 2025), so the portal's own choices for each record are the final word.
"""

from dataclasses import dataclass

from lekhara.gst.plan import Line

ACTIONS = {
    "accept": "Accept",
    "pending": "Keep pending",
    "reject": "Reject",
    "check": "Check it",
}


@dataclass(frozen=True)
class Elsewhere:
    """The invoice's bill, found in another of the firm's projects."""

    project: str
    same_amounts: bool


@dataclass(frozen=True)
class Advice:
    action: str
    reason: str

    @property
    def label(self) -> str:
        return ACTIONS[self.action]


def advise(line: Line, *, elsewhere: Elsewhere | None = None, counted: str | None = None) -> Advice:
    """The suggestion for one invoice or note. `counted` names the earlier month whose return
    already had the same invoice."""
    inv = line.invoice
    no_credit = (
        " The GST system gives no credit on it either way." if inv.itc_available is False else ""
    )
    if counted:
        return Advice(
            "reject",
            f"It was already in the return for {counted}. If it is the same invoice, rejecting "
            "this copy keeps the credit from being taken twice.",
        )
    if inv.kind == "credit_note":
        return Advice(
            "check",
            "A credit note lowers your credit. Accept it if you agreed it with the supplier, and "
            "reject it if you did not.",
        )
    if inv.kind == "debit_note":
        return Advice(
            "check",
            "A debit note adds to what you pay. Accept it if you agreed to the extra charge, and "
            "reject it if you did not.",
        )
    if line.outcome == "matched":
        return Advice("accept", "The bill is in Lekhara with the same amounts." + no_credit)
    if line.outcome == "differs":
        return Advice(
            "pending",
            f"The amounts differ: {line.note}. Check the supplier's invoice. If the bill in "
            "Lekhara is wrong, correct it and accept; if the supplier reported it wrongly, reject "
            "it so they correct it.",
        )
    if elsewhere is not None:
        if elsewhere.same_amounts:
            return Advice(
                "accept",
                f"The bill is in Lekhara under {elsewhere.project}, with the same amounts."
                + no_credit,
            )
        return Advice(
            "pending",
            f"The bill is in Lekhara under {elsewhere.project}, but the amounts differ. Check "
            "the supplier's invoice before accepting.",
        )
    return Advice(
        "pending",
        "There is no bill for it in Lekhara yet. Credit needs the goods or service received: "
        "keep it pending until the bill is booked, and reject it if it is not your purchase.",
    )
