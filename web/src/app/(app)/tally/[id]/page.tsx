import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { applyTally, tallyChoices, undoTally } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type TallyAlert, type TallyReview, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export const metadata: Metadata = { title: "Tally import" };

export default function TallyPage({ params }: PageProps<"/tally/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Reading the Tally file</p>}>
      <TallyView params={params} />
    </Suspense>
  );
}

const LEVEL: Record<TallyAlert["level"], { label: string; className: string }> = {
  blocking: { label: "Waiting for you", className: "tag tag-fail" },
  missing: { label: "Missing", className: "tag tag-soon" },
  info: { label: "Note", className: "tag tag-upcoming" },
};

const VOUCHER_KINDS: Record<string, string> = {
  purchase: "Purchases",
  payment: "Payments",
  receipt: "Receipts",
  journal: "Journals",
  contra: "Contras",
  sales: "Sales",
  "debit note": "Debit notes",
  "credit note": "Credit notes",
  other: "Other",
};

async function TallyView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const t = await api.tally(id);
  const base = `/projects/${t.project_id}`;
  const c = t.counts;
  const waiting = t.buyers.filter((b) => !b.ignored);

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{t.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/import`}>Import</Link>
          </p>
          <h1>{t.filename}</h1>
          <p>
            {`${t.source_label}${t.company ? ` from ${t.company}` : ""}`}
            {t.period.from ? `, ${day(t.period.from)} to ${day(t.period.to)}` : ""}.
          </p>
        </div>
      </div>

      <p className="status-line">
        {t.status === "applied"
          ? `Brought in: ${plural(t.result?.bills_added.length ?? 0, "bill")}, ${plural(t.result?.receipts_added.length ?? 0, "buyer payment")} and ${plural(t.result?.vendors_added.length ?? 0, "new supplier")}.`
          : t.status === "undone"
            ? "This import was undone; what it brought in has been removed."
            : "Nothing is saved yet. Check what Lekhara found and what is missing, then bring it in."}
      </p>

      <div className="stats">
        <div className="stat">
          <p className="stat-label">Suppliers</p>
          <p className="stat-value">{c.vendors_new + c.vendors_updated}</p>
          <p className="stat-note">{`${c.vendors_new} new, ${c.vendors_updated} with details filled in`}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Suppliers&apos; bills</p>
          <p className="stat-value">{c.bills_new}</p>
          <p className="stat-note">{`${c.bills_paid} already paid; ${c.bills_known} brought in before`}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Buyer payments</p>
          <p className="stat-value">{c.receipts_new}</p>
          <p className="stat-note">
            {c.receipts_waiting ? `${c.receipts_waiting} waiting for their unit` : `${c.receipts_known} brought in before`}
          </p>
        </div>
      </div>

      <div className="stats" style={{ marginTop: 24 }}>
        <div className="stat">
          <p className="stat-label">Cost incurred</p>
          <p className="stat-value">{inr(t.money.counts.incurred)}</p>
          <p className="stat-note">
            {Number(t.money.counts.unmapped_spend) > 0
              ? `${inr(t.money.counts.unmapped_spend)} more once every expense ledger has a cost line`
              : "Against the project's cost lines"}
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Cost paid</p>
          <p className="stat-value">{inr(t.money.counts.paid)}</p>
          <p className="stat-note">Paid directly, or to suppliers against their bills</p>
        </div>
        <div className="stat">
          <p className="stat-label">Into the RERA account</p>
          <p className="stat-value">{inr(t.money.counts.deposits)}</p>
          <p className="stat-note">{`${inr(t.money.counts.withdrawals)} taken out`}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Landowner payments</p>
          <p className="stat-value">{t.money.counts.landowner_payments}</p>
          <p className="stat-note">With the TDS cut on each</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>What needs attention</h2>
          <p>Anything the file is missing for Lekhara&apos;s checks, and how to fix it</p>
        </div>
        {t.alerts.length === 0 ? (
          <p className="empty">The file has everything Lekhara needs.</p>
        ) : (
          <ul className="rows">
            {t.alerts.map((a) => (
              <li key={a.code} className="row">
                <div>
                  <span className={LEVEL[a.level].className}>{LEVEL[a.level].label}</span>
                </div>
                <div>
                  <p className="row-title">{a.title}</p>
                  <p className="row-detail">{a.detail}</p>
                  {a.fix ? <p className="row-meta">{`How to fix it: ${a.fix}`}</p> : null}
                  {a.items.length > 0 ? (
                    <details className="disclosure" style={{ marginTop: 6 }}>
                      <summary>{`Which (${a.items.length}${a.items.length >= 20 ? " or more" : ""})`}</summary>
                      <p className="small">{a.items.join("; ")}</p>
                    </details>
                  ) : null}
                </div>
                <div />
              </li>
            ))}
          </ul>
        )}
      </section>

      {t.can_edit ? (
        <section className="section">
          <div className="section-head">
            <h2>Your choices</h2>
            <p>Lekhara remembers them for this project&apos;s next Tally import</p>
          </div>
          <ActionForm action={tallyChoices.bind(null, t.id)} label="Save the choices" pendingLabel="Checking again" secondary>
            {t.cost_centres.length > 0 ? (
              <div className="field" style={{ maxWidth: 420, marginTop: 12 }}>
                <label htmlFor="cost_centre">Which vouchers belong to this project</label>
                <select id="cost_centre" name="cost_centre" defaultValue={t.cost_centre ?? ""}>
                  <option value="">All vouchers in the file</option>
                  {t.cost_centres.map((cc) => (
                    <option key={cc} value={cc}>{`Only cost centre ${cc}`}</option>
                  ))}
                </select>
              </div>
            ) : null}
            {t.buyers.length > 0 ? (
              <table className="table" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Buyer&apos;s ledger in Tally</th>
                    <th className="right">Received</th>
                    <th>Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {t.buyers.map((b, i) => (
                    <tr key={b.ledger}>
                      <td>
                        {b.ledger}
                        <input type="hidden" name={`ledger_${i}`} value={b.ledger} />
                        <br />
                        <span className="small muted">{plural(b.count, "payment")}</span>
                      </td>
                      <td className="right num">{inr(b.total)}</td>
                      <td>
                        <select name={`unit_${i}`} defaultValue={b.ignored ? "ignore" : ""} aria-label={`Unit for ${b.ledger}`}>
                          <option value="">Choose the unit</option>
                          {t.units.map((u) => (
                            <option key={u.id} value={u.id}>
                              {`${u.label}${u.buyer ? `, ${u.buyer}` : ""}${b.suggestions.includes(u.label) ? " (likely)" : ""}`}
                            </option>
                          ))}
                          <option value="ignore">Not a buyer: leave these out</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            <MoneyChoices t={t} />
          </ActionForm>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>What the file holds</h2>
        </div>
        <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
          <li>
            <span className="muted">Ledger masters</span>
            <span>{t.found.masters ? `${t.found.ledgers} ledgers in ${t.found.groups} groups` : "Not in this file"}</span>
          </li>
          <li>
            <span className="muted">Vouchers</span>
            <span>
              {t.found.vouchers
                ? Object.entries(t.found.voucher_kinds)
                    .map(([k, n]) => `${n} ${(VOUCHER_KINDS[k] ?? k).toLowerCase()}`)
                    .join(", ")
                : "Not in this file"}
            </span>
          </li>
          <li>
            <span className="muted">Detail</span>
            <span>{t.found.totals_only ? "Totals only" : "Every ledger line"}</span>
          </li>
          {t.found.cost_centres ? (
            <li>
              <span className="muted">Cost centres</span>
              <span>{t.found.cost_centres}</span>
            </li>
          ) : null}
        </ul>
      </section>

      <Preview t={t} />

      {t.status === "review" && t.can_edit ? (
        <section className="section">
          <ActionForm action={applyTally.bind(null, t.id)} label="Bring it in" pendingLabel="Bringing it in">
            <p style={{ marginBottom: 12, maxWidth: 720 }}>
              {waiting.length > 0
                ? `Payments from ${plural(waiting.length, "buyer")} without a unit wait; everything else comes in now. You can import the same file again later for them.`
                : "Everything above comes in now. Importing the same file again later adds nothing twice."}
            </p>
          </ActionForm>
        </section>
      ) : null}

      {t.can_undo ? (
        <section className="section">
          <details className="disclosure">
            <summary>Undo this import</summary>
            <p className="small muted" style={{ margin: "8px 0 12px", maxWidth: 640 }}>
              Removes the bills and payments it brought in, and the suppliers it added that have no
              other bills, and puts back supplier details it filled in.
            </p>
            <ActionForm action={undoTally.bind(null, t.id)} label="Undo the import" pendingLabel="Undoing" secondary />
          </details>
        </section>
      ) : null}
    </>
  );
}

function Preview({ t }: { t: TallyReview }) {
  if (t.status !== "review") return null;
  return (
    <section className="section">
      <div className="section-head">
        <h2>A look at what comes in</h2>
      </div>
      {t.vendors.length > 0 ? (
        <details className="disclosure">
          <summary>{`Suppliers (${t.vendors.length})`}</summary>
          <table className="table">
            <thead>
              <tr>
                <th>Supplier</th>
                <th>GSTIN</th>
                <th>MSME</th>
                <th className="right">Bills</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {t.vendors.map((v) => (
                <tr key={v.name}>
                  <td>{v.name}</td>
                  <td>{v.gstin ?? (v.registered ? "Registered, no GSTIN" : "None")}</td>
                  <td>{v.msme === null ? "Not recorded" : v.msme === "none" ? "Not MSME" : v.msme}</td>
                  <td className="right num">{v.bills}</td>
                  <td className="small muted">{v.existing ? (v.changes.length ? "Details filled in" : "Already in Lekhara") : "New"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
      {t.bills.length > 0 ? (
        <details className="disclosure">
          <summary>{`Suppliers' bills (${t.counts.bills_new})`}</summary>
          <table className="table">
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Invoice</th>
                <th>Dated</th>
                <th className="right">Taxable value</th>
                <th className="right">GST</th>
                <th>Paid</th>
              </tr>
            </thead>
            <tbody>
              {t.bills.map((b) => (
                <tr key={`${b.vendor}-${b.bill_no}`}>
                  <td>{b.vendor}</td>
                  <td>
                    {b.bill_no}
                    {b.is_cement ? <span className="small muted"> cement</span> : null}
                  </td>
                  <td className="nowrap">{day(b.bill_date)}</td>
                  <td className="right num">{inr(b.taxable_value)}</td>
                  <td className="right num">{inr(b.gst)}</td>
                  <td className="nowrap">{b.paid_on ? day(b.paid_on) : "Not yet"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
      {t.receipts.length > 0 ? (
        <details className="disclosure">
          <summary>{`Buyer payments (${t.counts.receipts_new})`}</summary>
          <table className="table">
            <thead>
              <tr>
                <th>Buyer in Tally</th>
                <th>Unit</th>
                <th>Received</th>
                <th className="right">Amount</th>
                <th className="right">TDS</th>
              </tr>
            </thead>
            <tbody>
              {t.receipts.map((r, i) => (
                <tr key={`${r.ledger}-${i}`}>
                  <td>{r.ledger}</td>
                  <td>{r.unit}</td>
                  <td className="nowrap">{day(r.received_on)}</td>
                  <td className="right num">{inr(r.amount)}</td>
                  <td className="right num">{Number(r.tds) ? inr(r.tds) : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
    </section>
  );
}

function MoneyChoices({ t }: { t: TallyReview }) {
  const m = t.money;
  const rera = m.bank_ledgers.find((b) => b.rera)?.ledger ?? "";
  return (
    <>
      {m.cost_ledgers.length > 0 ? (
        <>
          <h3 style={{ marginTop: 24 }}>Expense ledgers and their cost lines</h3>
          {m.cost_lines.length === 0 ? (
            <p className="empty">
              Set up the project&apos;s cost lines first (Overview, Cost lines and budget).
            </p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Ledger in Tally</th>
                  <th className="right">Spent</th>
                  <th>Cost line</th>
                </tr>
              </thead>
              <tbody>
                {m.cost_ledgers.map((c, i) => (
                  <tr key={c.ledger}>
                    <td>
                      {c.ledger}
                      <input type="hidden" name={`costledger_${i}`} value={c.ledger} />
                      {c.source === "suggested" ? <span className="small muted"> (matched by name)</span> : null}
                    </td>
                    <td className="right num">{inr(c.total)}</td>
                    <td>
                      <select
                        name={`cost_${i}`}
                        defaultValue={c.source === "ignored" ? "ignore" : (c.target ?? "")}
                        aria-label={`Cost line for ${c.ledger}`}
                      >
                        <option value="">Choose a cost line</option>
                        {m.cost_lines.map((line) => (
                          <option key={line.id} value={line.id}>{`${line.code}, ${line.name}`}</option>
                        ))}
                        <option value="ignore">Not project cost</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : null}
      {m.bank_ledgers.length > 0 ? (
        <div className="field" style={{ maxWidth: 480, marginTop: 24 }}>
          <label htmlFor="rera_account">The RERA designated account (where 70% of buyer money goes)</label>
          <select id="rera_account" name="rera_account" defaultValue={rera}>
            <option value="">None of these</option>
            {m.bank_ledgers.map((b) => (
              <option key={b.ledger} value={b.ledger}>
                {b.ledger}
              </option>
            ))}
          </select>
          {m.bank_ledgers.map((b, i) => (
            <input key={b.ledger} type="hidden" name={`bankledger_${i}`} value={b.ledger} />
          ))}
        </div>
      ) : null}
      {m.landowners.length > 0 ? (
        <>
          <h3 style={{ marginTop: 24 }}>Landowners&apos; ledgers</h3>
          {m.landowner_ledgers.map((o, i) => (
            <input key={o.ledger} type="hidden" name={`ownerwas_${i}`} value={o.ledger} />
          ))}
          <div className="field-grid">
            {m.landowners.map((owner, i) => (
              <div key={owner.id} className="field">
                <label htmlFor={`owner_${i}`}>{`${owner.name}'s ledger in Tally`}</label>
                <input type="hidden" name={`ownerid_${i}`} value={owner.id} />
                <select
                  id={`owner_${i}`}
                  name={`owner_${i}`}
                  defaultValue={m.landowner_ledgers.find((l) => l.target === owner.id)?.ledger ?? ""}
                >
                  <option value="">Not in this file</option>
                  {m.party_ledgers.map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}
