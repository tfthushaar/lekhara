import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { applyStatement, statementAccount, statementChoices, undoStatement } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type BankLine, type BankReview, type TallyAlert, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export const metadata: Metadata = { title: "Bank statement" };

export default function BankStatementPage({ params }: PageProps<"/bank/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Reading the statement</p>}>
      <StatementView params={params} />
    </Suspense>
  );
}

const LEVEL: Record<TallyAlert["level"], { label: string; className: string }> = {
  blocking: { label: "Waiting for you", className: "tag tag-fail" },
  missing: { label: "Check", className: "tag tag-soon" },
  info: { label: "Note", className: "tag tag-upcoming" },
};

const OUTCOME_CLASS: Record<string, string> = {
  buyer_payment: "tag tag-done",
  deposit: "tag tag-done",
  interest: "tag tag-done",
  withdrawal: "tag tag-soon",
  charges: "tag tag-soon",
  needs_unit: "tag tag-fail",
  exists: "tag tag-upcoming",
};

async function StatementView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = await api.bankStatement(id);
  const base = `/projects/${s.project_id}`;
  const buyerLines = s.lines.filter((l) => l.buyer_line);
  const waiting = s.counts.needs_unit ?? 0;
  const added = s.counts.to_add ?? 0;

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{s.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/import`}>Import</Link>
          </p>
          <h1>{s.filename}</h1>
          <p>
            {[s.bank, s.account ? `account ${s.account}` : null].filter(Boolean).join(", ") || "Bank statement"}
            {s.period_from ? `, ${day(s.period_from)} to ${day(s.period_to ?? s.period_from)}` : ""}
            {`. ${plural(s.lines.length, "transaction")}.`}
          </p>
        </div>
      </div>

      <p className="status-line">
        {s.status === "applied"
          ? "Brought in. Bringing in the same statement again, or one that overlaps it, adds nothing twice."
          : s.status === "undone"
            ? "This statement was undone; what it brought in has been removed or reversed."
            : s.role === null
              ? "Nothing is saved yet. Say which account this is, then check the payments and bring them in."
              : `Nothing is saved yet. ${plural(added, "transaction")} will come in${waiting ? `; ${plural(waiting, "payment")} wait for their unit` : ""}.`}
      </p>

      <Stats s={s} />

      {s.can_edit ? (
        <section className="section">
          <div className="section-head">
            <h2>Which account is this?</h2>
            <p>Lekhara remembers it for this account&apos;s next statements</p>
          </div>
          <div style={{ maxWidth: 720, marginTop: 12 }}>
            <ActionForm action={statementAccount.bind(null, s.id)} label="Save" pendingLabel="Checking again" secondary>
              <div className="checks">
                <label>
                  <input type="radio" name="role" value="collections" defaultChecked={s.role === "collections"} />
                  <span>
                    <strong>The account buyers pay into</strong>
                    <br />
                    <span className="small muted">Each credit is matched to the buyer&apos;s unit; money going out is left out.</span>
                  </span>
                </label>
                <label>
                  <input type="radio" name="role" value="rera" defaultChecked={s.role === "rera"} />
                  <span>
                    <strong>The RERA designated account</strong>
                    <br />
                    <span className="small muted">Deposits, withdrawals, interest and bank charges, for the 70% check and escrow.</span>
                  </span>
                </label>
                <label style={{ marginLeft: 28 }}>
                  <input type="checkbox" name="buyers_pay_here" value="yes" defaultChecked={s.buyers_pay_here} />
                  <span className="small">Buyers pay straight into the RERA account, so its credits are their payments too</span>
                </label>
              </div>
            </ActionForm>
          </div>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>What needs attention</h2>
          <p>Anything Lekhara could not settle by itself, and what to do</p>
        </div>
        {s.alerts.length === 0 ? (
          <p className="empty">Nothing: the statement reads cleanly.</p>
        ) : (
          <ul className="rows">
            {s.alerts.map((a) => (
              <li key={a.code} className="row">
                <div>
                  <span className={LEVEL[a.level].className}>{LEVEL[a.level].label}</span>
                </div>
                <div>
                  <p className="row-title">{a.title}</p>
                  <p className="row-detail">{a.detail}</p>
                  {a.fix ? <p className="row-meta">{a.fix}</p> : null}
                  {a.items.length > 0 ? (
                    <details className="disclosure" style={{ marginTop: 6 }}>
                      <summary>{`Which (${a.items.length})`}</summary>
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

      {buyerLines.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Buyer payments</h2>
            <p>Each matched to a unit from the narration, your earlier choice for the payer, or Tally</p>
          </div>
          {s.can_place ? (
            <ActionForm action={statementChoices.bind(null, s.id)} label="Save the choices" pendingLabel="Checking again" secondary>
              <BuyerTable s={s} lines={buyerLines} editable />
            </ActionForm>
          ) : (
            <BuyerTable s={s} lines={buyerLines} editable={false} />
          )}
        </section>
      ) : null}

      <section className="section">
        <details className="disclosure">
          <summary>{`Every transaction in the statement (${s.lines.length})`}</summary>
          <p className="small muted">
            {`Read from the columns ${Object.values(s.columns).join(", ")}`}
            {s.reversed_order ? "; the bank listed the newest first, so Lekhara put them in order" : ""}.
          </p>
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Narration</th>
                <th className="right">Out</th>
                <th className="right">In</th>
                <th className="right">Balance</th>
                <th>In Lekhara</th>
              </tr>
            </thead>
            <tbody>
              {s.lines.map((l) => (
                <tr key={l.key}>
                  <td className="nowrap">{day(l.on)}</td>
                  <td>
                    {l.narration}
                    {l.note ? (
                      <>
                        <br />
                        <span className="small muted">{l.note}</span>
                      </>
                    ) : null}
                  </td>
                  <td className="right num">{l.debit ? inr(l.debit) : ""}</td>
                  <td className="right num">{l.credit ? inr(l.credit) : ""}</td>
                  <td className="right num">{l.balance ? inr(l.balance) : ""}</td>
                  <td>
                    <span className={OUTCOME_CLASS[l.outcome] ?? "tag"}>{l.outcome_label}</span>
                    {l.unit_label ? <span className="small">{` ${l.unit_label}`}</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      </section>

      {s.can_apply ? (
        <section className="section">
          <ActionForm action={applyStatement.bind(null, s.id)} label="Bring it in" pendingLabel="Bringing it in">
            <p style={{ marginBottom: 12, maxWidth: 720 }}>
              {waiting > 0
                ? `Payments waiting for their unit stay out; everything else comes in now. Bring in the same statement again later once they are placed; nothing is added twice.`
                : "Everything marked above comes in now. Bringing in the same statement again later adds nothing twice."}
            </p>
          </ActionForm>
        </section>
      ) : null}

      {s.can_apply_rest ? (
        <section className="section">
          <ActionForm action={applyStatement.bind(null, s.id)} label="Bring in the rest" pendingLabel="Bringing it in">
            <p style={{ marginBottom: 12, maxWidth: 720 }}>
              {`${plural(added, "payment")} placed since the statement came in can come in now.`}
            </p>
          </ActionForm>
        </section>
      ) : null}

      {s.can_undo ? (
        <section className="section">
          <details className="disclosure">
            <summary>Undo this statement</summary>
            <p className="small muted" style={{ margin: "8px 0 12px", maxWidth: 640 }}>
              Removes the buyer payments it brought in and reverses its movements in the RERA account. Possible for 30 days.
            </p>
            <ActionForm action={undoStatement.bind(null, s.id)} label="Undo the statement" pendingLabel="Undoing" secondary />
          </details>
        </section>
      ) : null}
    </>
  );
}

function Stats({ s }: { s: BankReview }) {
  const t = s.totals;
  return (
    <div className="stats">
      <div className="stat">
        <p className="stat-label">Into the account</p>
        <p className="stat-value">{inr(t.credits)}</p>
        <p className="stat-note">{`${inr(t.debits)} out`}</p>
      </div>
      {s.role !== "rera" || s.buyers_pay_here ? (
        <div className="stat">
          <p className="stat-label">Buyer payments</p>
          <p className="stat-value">{inr(t.buyer_payments)}</p>
          <p className="stat-note">{t.waiting && Number(t.waiting) > 0 ? `${inr(t.waiting)} waiting for their unit` : "Matched to their units"}</p>
        </div>
      ) : null}
      {s.role === "rera" ? (
        <div className="stat">
          <p className="stat-label">RERA account</p>
          <p className="stat-value">{inr(t.deposits)}</p>
          <p className="stat-note">{`deposited; ${inr(t.withdrawals)} withdrawn, ${inr(t.interest)} interest`}</p>
        </div>
      ) : null}
      <div className="stat">
        <p className="stat-label">Balance</p>
        <p className="stat-value">{s.closing ? inr(s.closing) : "Not shown"}</p>
        <p className="stat-note">{s.opening ? `Opened at ${inr(s.opening)}` : "At the end of the statement"}</p>
      </div>
    </div>
  );
}

function BuyerTable({ s, lines, editable }: { s: BankReview; lines: BankLine[]; editable: boolean }) {
  return (
    <div>
      <table className="table" style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>Date</th>
            <th>From</th>
            <th className="right">Amount</th>
            <th>Unit</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((l, i) => {
            const current = l.choice ?? (l.unit_id ?? (l.outcome === "not_buyer" ? "not_buyer" : ""));
            return (
              <tr key={l.key}>
                <td className="nowrap">{day(l.on)}</td>
                <td>
                  {l.payer ?? l.narration}
                  <br />
                  <span className="small muted">
                    {[l.channel, l.reference, l.loan ? "home-loan disbursement" : null, l.how ? `matched by ${l.how}` : null]
                      .filter(Boolean)
                      .join(", ")}
                  </span>
                </td>
                <td className="right num">{inr(l.credit ?? "0")}</td>
                <td>
                  {editable && l.outcome !== "exists" && l.outcome !== "returned" ? (
                    <>
                      <input type="hidden" name={`line_${i}`} value={l.key} />
                      <select name={`choice_${i}`} defaultValue={current} aria-label={`Unit for the payment of ${day(l.on)}`}>
                        <option value="">Choose the unit</option>
                        {s.units.map((u) => (
                          <option key={u.id} value={u.id}>
                            {`${u.label}${u.buyer ? `, ${u.buyer}` : ""}${l.candidates.some((c) => c.id === u.id) ? " (likely)" : ""}`}
                          </option>
                        ))}
                        <option value="not_buyer">Not a buyer&apos;s payment</option>
                        <option value="skip">Leave this line out</option>
                      </select>
                    </>
                  ) : (
                    <span>{l.unit_label ?? l.outcome_label}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
