import { Suspense } from "react";

import { addLoan, addLoanCondition, addLoanMove, meetLoanCondition } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type Cash, api } from "@/lib/api";
import { day, inr } from "@/lib/format";

export default function CashPage({ params }: PageProps<"/projects/[id]/cash">) {
  return (
    <Suspense fallback={<p className="loading">Working out the cash</p>}>
      <CashView params={params} />
    </Suspense>
  );
}

function month(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-IN", { month: "long", timeZone: "UTC" });
}

type Loan = Cash["loans"][number];

function LoanCard({ loan, c }: { loan: Loan; c: Cash }) {
  const open = loan.conditions.filter((x) => !x.met_on);
  return (
    <section className="card">
      <div className="card-head">
        <h2>{loan.lender}</h2>
        {loan.rate_pct ? <span className="muted small">{`${Number(loan.rate_pct)}% a year`}</span> : null}
      </div>
      <div className="tile-grid" style={{ marginTop: 12 }}>
        <div className="tile">
          <p className="tile-label">Owed now</p>
          <p className="tile-value">{inr(loan.outstanding)}</p>
        </div>
        <div className="tile">
          <p className="tile-label">Can still draw</p>
          <p className="tile-value">{inr(loan.can_draw)}</p>
        </div>
      </div>
      <p className="small muted" style={{ marginTop: 10 }}>
        {`${inr(loan.sanctioned)} sanctioned, ${inr(loan.drawn)} drawn, ${inr(loan.repaid)} repaid.`}
        {loan.next ? ` ${loan.next.kind === "Drawn" ? "Next drawing" : "Next payment"}: ${inr(loan.next.amount)} on ${day(loan.next.on)}.` : ""}
      </p>
      {open.length > 0 ? (
        <ul className="rows" style={{ marginTop: 12 }}>
          {open.map((x) => (
            <li key={x.id} className="row row-2">
              <div>
                <p className="row-title">{x.text}</p>
                <p className="row-meta">
                  {x.late ? <span className="tag tag-overdue">{`Was due ${day(x.due_on)}`}</span> : x.due_on ? `Due ${day(x.due_on)}` : "No date"}
                </p>
              </div>
              <div className="row-side">{c.can_edit ? <ActionForm action={meetLoanCondition.bind(null, x.id)} label="Done" pendingLabel="Saving" secondary /> : null}</div>
            </li>
          ))}
        </ul>
      ) : null}
      {c.can_edit ? (
        <>
          <details className="disclosure" style={{ marginTop: 12 }}>
            <summary>Record money drawn or paid</summary>
            <ActionForm action={addLoanMove.bind(null, loan.id)} label="Save" pendingLabel="Saving">
              <fieldset className="choice-pills">
                {c.kinds.map((k, n) => (
                  <label key={k.value}>
                    <input type="radio" name="kind" value={k.value} defaultChecked={n === 0} />
                    <span>{k.label}</span>
                  </label>
                ))}
              </fieldset>
              <div className="field-grid">
                <div className="field">
                  <label htmlFor={`lm-${loan.id}-a`}>Amount</label>
                  <input id={`lm-${loan.id}-a`} name="amount" inputMode="decimal" required placeholder="50 lakh" />
                </div>
                <div className="field">
                  <label htmlFor={`lm-${loan.id}-on`}>On (a later date is a plan)</label>
                  <input id={`lm-${loan.id}-on`} name="on" type="date" />
                </div>
              </div>
            </ActionForm>
          </details>
          <details className="disclosure">
            <summary>Add something the lender needs</summary>
            <ActionForm action={addLoanCondition.bind(null, loan.id)} label="Add it" pendingLabel="Adding" secondary>
              <div className="field-grid">
                <div className="field">
                  <label htmlFor={`lc-${loan.id}-t`}>What</label>
                  <input id={`lc-${loan.id}-t`} name="text" required placeholder="Quarterly progress certificate" />
                </div>
                <div className="field">
                  <label htmlFor={`lc-${loan.id}-d`}>By</label>
                  <input id={`lc-${loan.id}-d`} name="due_on" type="date" />
                </div>
              </div>
            </ActionForm>
          </details>
        </>
      ) : null}
      {loan.moves.length > 0 ? (
        <details className="disclosure">
          <summary>{`Every payment (${loan.moves.length})`}</summary>
          <ul className="calc">
            {loan.moves.map((m, n) => (
              <li key={`${m.on}-${n}`}>
                <span>{`${day(m.on)}, ${m.kind_label.toLowerCase()}${m.planned ? " (planned)" : ""}`}</span>
                <span className="num">{inr(m.amount)}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

async function CashView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const c = await api.cash(id);

  return (
    <>
      <section>
        <div className="section-head">
          <h2>The next three months</h2>
        </div>
        <div className="tile-grid">
          {c.forecast.map((m) => (
            <div key={m.month} className="tile">
              <p className="tile-label">{month(m.month)}</p>
              <p className="tile-value">{`${Number(m.net) < 0 ? "−" : "+"}${inr(String(Math.abs(Number(m.net))))}`}</p>
              <p className="small muted">{`${inr(m.in)} in, ${inr(m.out)} out`}</p>
            </div>
          ))}
        </div>
        <p className="small muted" style={{ marginTop: 12, maxWidth: 760 }}>
          {`From what buyers owe on demands already raised, bills not yet paid, and loan payments planned. Besides this, ${inr(c.drawable)} can be drawn from the RERA account today.`}
        </p>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Loans</h2>
        </div>
        {c.loans.length === 0 ? <p className="empty">No loans on this project.</p> : null}
        <div className="rows">
          {c.loans.map((loan) => (
            <LoanCard key={loan.id} loan={loan} c={c} />
          ))}
        </div>
        {c.can_edit ? (
          <details className="disclosure" style={{ marginTop: 12 }}>
            <summary>Add a loan</summary>
            <ActionForm action={addLoan.bind(null, id)} label="Add the loan" pendingLabel="Adding">
              <div className="field-grid">
                <div className="field">
                  <label htmlFor="ln-lender">Lender</label>
                  <input id="ln-lender" name="lender" required placeholder="Canara Bank" />
                </div>
                <div className="field">
                  <label htmlFor="ln-amount">Sanctioned</label>
                  <input id="ln-amount" name="sanctioned" required placeholder="40 crore" />
                </div>
                <div className="field">
                  <label htmlFor="ln-rate">Interest, % a year</label>
                  <input id="ln-rate" name="rate_pct" inputMode="decimal" />
                </div>
                <div className="field">
                  <label htmlFor="ln-on">Sanctioned on</label>
                  <input id="ln-on" name="sanctioned_on" type="date" />
                </div>
              </div>
            </ActionForm>
          </details>
        ) : null}
      </section>
    </>
  );
}
