"""What a bank's narration says: who paid, how, and whether it is interest, a charge or a
payment coming back.

Narrations are short and packed: NEFT CR-SBIN0001234-PRIYA SHARMA-KAVERI HOMES-SBIN4251234567,
UPI-PRIYA SHARMA-priya@okhdfcbank-HDFC0001234-512345678901-PAYMENT, BY TRANSFER-NEFT*SBIN0001234*
N123456789*PRIYA SHARMA, MMT/IMPS/512312345678/PRIYA SHARMA/SBIN. The payer's name is the first
part that is not a channel word, a code, a number, an account or a bank.
"""

import re

_SPLIT = re.compile(r"\s*[-/*:|\\]+\s*|\s{2,}")
_IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$", re.IGNORECASE)
_UTR = re.compile(r"\b([A-Z]{4}[RHN0-9][0-9A-Z]{10,18}|[0-9]{12,22})\b")

NOISE = {
    "neft", "rtgs", "imps", "upi", "cr", "dr", "mmt", "p2a", "p2m", "p2p", "by", "to", "from",
    "transfer", "tfr", "trf", "ft", "dep", "deposit", "inb", "inbt", "mob", "mb", "ib", "clg",
    "chq", "cheque", "micr", "cts", "inw", "inward", "outward", "ow", "iw", "payment", "pay",
    "paymen", "fund", "funds", "credit", "debit", "ach", "nach", "ecs", "ref", "utr", "txn",
    "na", "sent", "received", "using", "via", "online", "net", "banking", "bil", "bill",
    "ybl", "paytm", "phonepe", "gpay", "the", "for", "of", "a", "c", "ac", "no", "and",
    "branch", "self", "cash", "rev", "towards", "flat", "unit", "inst", "installment",
}  # fmt: skip
BANK_WORDS = re.compile(
    r"\b(bank|hdfc|icici|sbi|sbin|axis|utib|kotak|kkbk|canara|cnrb|baroda|barb|union|ubin|"
    r"federal|indusind|yes|idfc|pnb|kvb)\b",
    re.IGNORECASE,
)
BANK_FILLER = {
    "of", "india", "ltd", "limited", "co", "op", "cooperative", "the", "first", "state",
    "national", "punjab", "indian", "overseas", "central", "mahindra", "small", "finance",
}  # fmt: skip
LENDERS = re.compile(
    r"\b(hdfc\s*ltd|lic\s*h(ousing)?\s*f|lichfl|pnb\s*housing|bajaj\s*housing|tata\s*capital|"
    r"home\s*loan|housing\s*finance|hfl|hfc|disb|disbursement|loan)\b",
    re.IGNORECASE,
)

INTEREST = re.compile(
    r"\b(int\.?\s*(pd|paid|cr|credit|coll|on)|interest|sb\s*int|fd\s*int|int\.?pd)\b", re.I
)
CHARGES = re.compile(
    r"\b(chgs?|charges?|commission|gst\s*@|cgst|sgst|igst|sms\s*(chg|alert)|annual\s*fee|amc|"
    r"service\s*(charge|chg)|min(imum)?\s*bal|stamp\s*duty|cheque\s*book|chq\s*book|"
    r"ledger\s*folio|folio\s*chg|maint(enance)?\s*chg)",
    re.IGNORECASE,
)
RETURNED = re.compile(
    r"\b(return(ed)?|rtn|reversal|reversed|rev\b|bounce[d]?|dishono[u]?r(ed)?|unpaid|"
    r"inward\s*ret|chq\s*ret|o/?w\s*rtn|i/?w\s*rtn|refund\s*of\s*failed)",
    re.IGNORECASE,
)
CHANNELS = (
    ("RTGS", re.compile(r"\brtgs\b", re.I)),
    ("NEFT", re.compile(r"\bneft\b", re.I)),
    ("IMPS", re.compile(r"\b(imps|mmt)\b", re.I)),
    ("UPI", re.compile(r"\bupi\b", re.I)),
    ("Cheque", re.compile(r"\b(chq|cheque|clg|clearing|micr|cts)\b", re.I)),
    ("Cash", re.compile(r"\bcash\b", re.I)),
    ("Transfer", re.compile(r"\b(transfer|tfr|trf|ft|inb|ib)\b", re.I)),
)


def channel(narration: str) -> str | None:
    for name, pattern in CHANNELS:
        if pattern.search(narration):
            return name
    return None


def is_interest(narration: str) -> bool:
    return bool(INTEREST.search(narration))


def is_charge(narration: str) -> bool:
    return bool(CHARGES.search(narration))


def is_returned(narration: str) -> bool:
    return bool(RETURNED.search(narration))


def is_loan(narration: str) -> bool:
    return bool(LENDERS.search(narration))


def _is_name(part: str, *, lenders: bool) -> bool:
    if "@" in part or _IFSC.match(part.replace(" ", "")):
        return False
    if len(re.findall(r"\d", part)) >= 3:
        return False
    words = re.findall(r"[a-z]+", part.casefold())
    meaningful = [w for w in words if w not in NOISE]
    if not meaningful or sum(len(w) for w in meaningful) < 3:
        return False
    if lenders and LENDERS.search(part):
        return True
    banks_only = all(BANK_WORDS.fullmatch(w) or w in BANK_FILLER for w in meaningful)
    return not banks_only


def payer(narration: str, own: tuple[str, ...] = ()) -> str | None:
    """The name of whoever paid (or was paid), as the bank wrote it. Parts that are the firm's
    own names (the beneficiary on a credit) are passed over; a lender counts as the payer of a
    home-loan disbursement."""
    lenders = is_loan(narration)
    own_keys = {k for k in (payer_key(o) for o in own) if k}
    for part in _SPLIT.split(narration):
        part = part.strip(" .,")
        if not part or not _is_name(part, lenders=lenders):
            continue
        words = [w for w in part.split() if w.casefold().strip(".") not in NOISE]
        name = " ".join(words).strip(" .,")
        key = payer_key(name)
        if key and any(key in k or k in key for k in own_keys):
            continue
        if len(re.sub(r"[^A-Za-z]", "", name)) >= 3:
            return name[:120]
    for part in _SPLIT.split(narration):
        if "@" in part:
            handle = re.sub(r"[^a-z]", " ", part.split("@")[0].casefold()).strip()
            if len(handle) >= 3:
                return handle
    return None


def payer_key(name: str | None) -> str | None:
    """A payer's name as Lekhara remembers it: lower case letters and single spaces."""
    if not name:
        return None
    key = " ".join(re.findall(r"[a-z]+", name.casefold()))
    return key[:200] or None


def utr(narration: str, reference: str) -> str | None:
    ref = (reference or "").strip()
    if ref and ref not in ("0", "-") and len(re.sub(r"\D", "", ref)) >= 5:
        return ref[:60]
    for part in _SPLIT.split(narration):
        m = _UTR.search(part.strip().upper())
        if m and not _IFSC.match(m.group(1)):
            return m.group(1)
    return ref[:60] or None
