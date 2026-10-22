"""Filing documents by the firm's own rules, when no one chooses the kind."""

from conftest import signed_in
from fastapi.testclient import TestClient

from lekhara import filing
from lekhara.pdf import write_pdf

SG = "sarjapur-greens"


def text(words: str) -> str:
    return filing._normal(words)


def test_the_four_ways_of_matching() -> None:
    noc = text("Fire NOC issued by the Karnataka State Fire and Emergency Services")
    assert filing.matches("phrase", "fire and emergency", noc)
    assert not filing.matches("phrase", "emergency fire", noc)
    assert filing.matches("all", "NOC fire", noc)
    assert not filing.matches("all", "fire occupancy", noc)
    assert filing.matches("any", "khata occupancy fire", noc)
    assert not filing.matches("any", "khata occupancy", noc)
    scanned = text("OCCUPANCV CERTIFlCATE issued under section 310")  # read from a scan
    assert filing.matches("fuzzy", "occupancy certificate", scanned)
    assert not filing.matches("phrase", "occupancy certificate", scanned)
    assert not filing.matches("all", "", noc)


def upload(client: TestClient, words: str, filename: str, **fields):
    data = write_pdf([[words]], title=words[:40])
    return client.post(
        f"/projects/{SG}/documents",
        data=fields,
        files={"file": (filename, data, "application/pdf")},
    )


def test_an_upload_with_no_kind_chosen_is_filed_by_the_rules(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    added = owner.post("/organization/filing-rules/standard").json()["added"]
    assert added == len(filing.STANDARD)
    assert owner.post("/organization/filing-rules/standard").json()["added"] == 0  # once only

    r = upload(owner, "Fire NOC issued by Karnataka State Fire and Emergency Services, tower B",
               "scan-0042.pdf")  # fmt: skip
    assert r.status_code == 201, r.text
    doc = owner.get(f"/documents/{r.json()['id']}").json()
    assert doc["category"] == "approval" and doc["requirement"] == "fire_noc"
    assert doc["filed_by"] == "Fire NOC"

    # Someone chose the kind: the rules leave it alone.
    chosen = upload(owner, "Fire NOC, a copy for the bank", "copy.pdf", category="bank").json()
    doc = owner.get(f"/documents/{chosen['id']}").json()
    assert doc["category"] == "bank" and doc["filed_by"] is None

    # Nothing fits: Other.
    plain = upload(owner, "Minutes of the site meeting", "minutes.pdf").json()
    assert owner.get(f"/documents/{plain['id']}").json()["category"] == "other"


def test_a_rule_can_be_tried_then_used_on_documents_already_in(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    first = upload(owner, "Lift licence from the Electrical Inspectorate", "lift.pdf").json()
    assert owner.get(f"/documents/{first['id']}").json()["category"] == "other"

    rule = {"name": "Lift licence", "words": "lift licence", "how": "phrase",
            "category": "approval"}  # fmt: skip
    tried = owner.post("/organization/filing-rules/try", json=rule).json()["documents"]
    assert [d["id"] for d in tried] == [first["id"]]
    made = owner.post("/organization/filing-rules", json=rule)
    assert made.status_code == 201 and made.json()["would_file"] == 1
    assert owner.post("/organization/filing-rules/refile").json()["filed"] >= 1
    doc = owner.get(f"/documents/{first['id']}").json()
    assert doc["category"] == "approval" and doc["filed_by"] == "Lift licence"

    listed = owner.get("/organization/filing-rules").json()
    assert [r["name"] for r in listed["rules"]] == ["Lift licence"]
    bad = owner.post("/organization/filing-rules", json={**rule, "how": "regex"})
    assert bad.status_code == 400


def test_only_the_team_that_files_documents_changes_the_rules(app) -> None:
    # A certifier on the firm's projects is not in its team.
    architect = signed_in(app, "architect@demo.lekhara")
    assert architect.post("/organization/filing-rules/standard").status_code in (403, 404)
    assert architect.get("/organization/filing-rules").status_code in (403, 404)


def test_the_rule_found_nearest_the_top_wins(app) -> None:
    owner = signed_in(app, "promoter@demo.lekhara")
    owner.post("/organization/filing-rules/standard")
    # An occupancy certificate that mentions the project's RERA registration certificate.
    r = upload(owner, "OCCUPANCY CERTIFICATE for the building registered under RERA, "
                      "see the RERA registration certificate", "scan-0050.pdf")  # fmt: skip
    doc = owner.get(f"/documents/{r.json()['id']}").json()
    assert doc["requirement"] == "oc" and doc["filed_by"] == "Occupancy certificate"
