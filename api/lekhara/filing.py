"""Filing documents by rules: a firm's own words for its documents, without waiting for AI.

A rule names some words and how to look for them, and what a document containing them is: its
kind (approvals, title, insurance and so on) and, if it is one, the checklist item it answers
(the occupancy certificate, the fire NOC). When someone uploads or emails in a document without
choosing its kind, Lekhara reads its text, file name and title and files it by the rule that
fits, saying which rule did; when several fit, the one whose words come earliest wins. The
person can always change it.

The idea comes from Paperless-ngx's matching. Of its ways to match, four are kept:

- any:    any one of the words appears;
- all:    every word appears, in any order;
- phrase: the words appear together, in that order;
- fuzzy:  every word appears, allowing a letter or two wrong (useful for scanned text).

Patterns (regular expressions) are left out on purpose: one written carelessly can take a
server minutes to run over a long document.
"""

import difflib
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lekhara.engines.documents import CATEGORY_LABEL, REQUIREMENTS
from lekhara.models import Document, DocumentPage, FilingRule, Organization
from lekhara.services import ServiceError

HOW = {
    "any": "Any of the words",
    "all": "All of the words",
    "phrase": "The exact phrase",
    "fuzzy": "All of the words, allowing small spelling differences",
}
TEXT_LIMIT = 40_000
"""Rules look at the first part of a document, where its title and number are."""

STANDARD = (
    ("K-RERA registration", "rera registration certificate", "all", "registration",
     "krera_registration"),
    ("Occupancy certificate", "occupancy certificate", "phrase", "approval", "oc"),
    ("Commencement certificate", "commencement certificate", "phrase", "approval", "commencement"),
    ("Fire NOC", "fire noc", "all", "approval", "fire_noc"),
    ("Fire no objection", "fire no objection", "phrase", "approval", "fire_noc"),
    ("Environmental clearance", "environmental clearance", "phrase", "approval", "environmental"),
    ("Sanctioned plan", "sanctioned plan", "phrase", "approval", "plan_sanction"),
    ("Plan sanction", "plan sanction", "phrase", "approval", "plan_sanction"),
    ("Encumbrance certificate", "encumbrance certificate", "phrase", "title", "encumbrance"),
    ("Mother deed", "mother deed", "phrase", "title", "title_deed"),
    ("Joint development agreement", "joint development agreement", "phrase", "agreement", "jda"),
    ("Designated account letter", "designated account", "phrase", "bank", "escrow_letter"),
    ("Contractor's all-risk insurance", "contractor all risk", "fuzzy", "insurance", "insurance"),
    ("Sale deed", "sale deed", "phrase", "sale_deed", None),
    ("Khata", "khata ekhata", "any", "ekhata", None),
    ("Tax invoice", "tax invoice", "phrase", "invoice", None),
    ("Bank guarantee", "bank guarantee", "phrase", "insurance", None),
)  # fmt: skip
"""Rules for the documents every Karnataka project has, added in one step."""


# Matching


def _normal(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text.casefold())).strip()


def position(how: str, words: str, text: str) -> int | None:
    """Where in the text (already normalised) the words are found the given way, or None."""
    wanted = _normal(words).split()
    if not wanted:
        return None
    padded = f" {text} "

    def at(word: str) -> int:
        return padded.find(f" {word} ")

    if how == "phrase":
        found = at(" ".join(wanted))
        return found if found >= 0 else None
    places = [at(w) for w in wanted]
    if how == "any":
        hits = [p for p in places if p >= 0]
        return min(hits) if hits else None
    if how == "all":
        return min(places) if all(p >= 0 for p in places) else None
    if how == "fuzzy":
        tokens = text.split()
        starts, found = [], []
        offset = 0
        for token in tokens:
            starts.append(offset)
            offset += len(token) + 1
        for w in wanted:
            close = difflib.get_close_matches(w, set(tokens), n=1, cutoff=0.8)
            if not close:
                return None
            found.append(starts[tokens.index(close[0])])
        return min(found)
    return None


def matches(how: str, words: str, text: str) -> bool:
    return position(how, words, text) is not None


def document_text(session: Session, doc: Document) -> str:
    pages = session.scalars(
        select(DocumentPage.text)
        .where(DocumentPage.document_id == doc.id)
        .order_by(DocumentPage.page_no)
    )
    body = " ".join(t or "" for t in pages)[:TEXT_LIMIT]
    return _normal(f"{doc.title} {doc.filename} {body}")


def rules_of(session: Session, organization_id: str) -> list[FilingRule]:
    return list(
        session.scalars(
            select(FilingRule)
            .where(FilingRule.organization_id == organization_id)
            .order_by(FilingRule.position, FilingRule.created_at)
        )
    )


def first_rule(session: Session, organization_id: str, text: str) -> FilingRule | None:
    """The rule whose words come earliest in the document: a document says what it is near
    the top (its title), and may mention other kinds of document further down. Rules found at
    the same place are taken in their order."""
    best, best_at = None, None
    for rule in rules_of(session, organization_id):
        found = position(rule.how, rule.words, text)
        if found is not None and (best_at is None or found < best_at):
            best, best_at = rule, found
    return best


def file_by_rules(session: Session, doc: Document, *, fallback: str | None = None) -> None:
    """Gives a document with no kind chosen the kind (and checklist item) of the first rule
    that fits, or the fallback guess, or Other."""
    rule = first_rule(session, doc.organization_id, document_text(session, doc))
    if rule is not None:
        doc.category = rule.category
        if rule.requirement and doc.requirement is None:
            doc.requirement = rule.requirement
        doc.filed_by = rule.name
    else:
        doc.category = fallback or "other"


# Keeping the rules


def _check(fields: dict) -> dict:
    name = (fields.get("name") or "").strip()
    words = (fields.get("words") or "").strip()
    how = fields.get("how") or "all"
    category = fields.get("category") or ""
    requirement = fields.get("requirement") or None
    if not name:
        raise ServiceError("Name the rule, so you know it again.")
    if not _normal(words):
        raise ServiceError("Give the words to look for.")
    if len(words) > 200:
        raise ServiceError("Keep the words to a few, under 200 characters.")
    if how not in HOW:
        raise ServiceError("Choose how to look for the words.")
    if category not in CATEGORY_LABEL:
        raise ServiceError("Choose what kind of document it files them as.")
    if requirement is not None and requirement not in REQUIREMENTS:
        raise ServiceError("That checklist item is not known.")
    return {"name": name[:100], "words": words, "how": how, "category": category,
            "requirement": requirement}  # fmt: skip


def create_rule(session: Session, org: Organization, fields: dict, user_id: str) -> FilingRule:
    values = _check(fields)
    position = session.scalar(
        select(func.coalesce(func.max(FilingRule.position), 0)).where(
            FilingRule.organization_id == org.id
        )
    )
    rule = FilingRule(organization_id=org.id, position=position + 1, created_by=user_id, **values)
    session.add(rule)
    session.commit()
    return rule


def delete_rule(session: Session, org: Organization, rule_id: str) -> None:
    rule = session.get(FilingRule, rule_id)
    if rule is None or rule.organization_id != org.id:
        raise ServiceError("Rule not found.", 404)
    session.delete(rule)
    session.commit()


def add_standard(session: Session, org: Organization, user_id: str) -> int:
    have = {r.name for r in rules_of(session, org.id)}
    added = 0
    for name, words, how, category, requirement in STANDARD:
        if name in have:
            continue
        fields = {"name": name, "words": words, "how": how, "category": category,
                  "requirement": requirement}  # fmt: skip
        create_rule(session, org, fields, user_id)
        added += 1
    return added


def would_file(
    session: Session, org: Organization, fields: dict, limit: int = 20
) -> list[Document]:
    """The documents already in the vault a rule would fit, to try it before saving."""
    values = _check({**fields, "name": fields.get("name") or "Trying"})
    found = []
    for doc in session.scalars(
        select(Document).where(Document.organization_id == org.id, Document.archived_on.is_(None))
    ):
        if matches(values["how"], values["words"], document_text(session, doc)):
            found.append(doc)
            if len(found) >= limit:
                break
    return found


def refile(session: Session, org: Organization) -> int:
    """Files by the rules every document still under Other that no person has filed."""
    filed = 0
    for doc in session.scalars(
        select(Document).where(
            Document.organization_id == org.id,
            Document.category == "other",
            Document.requirement.is_(None),
            Document.archived_on.is_(None),
        )
    ):
        file_by_rules(session, doc)
        if doc.category != "other":
            filed += 1
    session.commit()
    return filed


def view(session: Session, org: Organization) -> dict:
    return {
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "words": r.words,
                "how": r.how,
                "how_label": HOW[r.how],
                "category": r.category,
                "category_label": CATEGORY_LABEL[r.category],
                "requirement": r.requirement,
                "requirement_label": REQUIREMENTS[r.requirement].title if r.requirement else None,
            }
            for r in rules_of(session, org.id)
        ],
        "hows": [{"value": k, "label": v} for k, v in HOW.items()],
        "categories": [{"value": k, "label": v} for k, v in CATEGORY_LABEL.items()],
        "requirements": [{"value": k, "label": r.title} for k, r in REQUIREMENTS.items()],
        "standard_missing": len(
            {n for n, *_ in STANDARD} - {r.name for r in rules_of(session, org.id)}
        ),
    }
