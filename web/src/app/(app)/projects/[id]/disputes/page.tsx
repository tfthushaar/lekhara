import Link from "next/link";
import { Suspense } from "react";

import { createCase } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type CaseEvent, type Disputes, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export default function DisputesPage({ params }: PageProps<"/projects/[id]/disputes">) {
  return (
    <Suspense fallback={<p className="loading">Working out what each case could cost</p>}>
      <DisputesView params={params} />
    </Suspense>
  );
}

const EVENT_TAG: Record<CaseEvent["kind"], string> = {
  reply: "Reply",
  hearing: "Hearing",
  comply: "Comply",
  appeal: "Appeal",
};

async function DisputesView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const r = await api.disputes(id);
  const s = r.summary;
  const open = r.cases.filter((c) => c.open);
  const closed = r.cases.filter((c) => !c.open);

  return (
    <>
      <div className="stats">
        <div className="stat">
          <p className="stat-label">Open cases</p>
          <p className="stat-value">{s.open}</p>
          <p className="stat-note">At K-RERA, consumer commissions and courts</p>
        </div>
        <div className="stat">
          <p className="stat-label">Could cost</p>
          <p className="stat-value">{inr(s.at_stake)}</p>
          <p className="stat-note">If every open case goes against you, at today&apos;s figures</p>
        </div>
        <div className="stat">
          <p className="stat-label">Ordered and unpaid</p>
          <p className="stat-value">{inr(s.owed_under_orders)}</p>
          <p className="stat-note">
            {s.overdue_orders > 0
              ? `${plural(s.overdue_orders, "order")} past the date to comply`
              : "No order is past its date"}
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Next date</p>
          <p className="stat-value">{s.next ? day(s.next.on) : "None"}</p>
          <p className="stat-note">{s.next ? s.next.text : "Nothing is scheduled"}</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Coming up</h2>
          <p>Replies, hearings, dates to comply with an order and the last days to appeal</p>
        </div>
        {r.events.length === 0 ? (
          <p className="empty">Nothing is due in any open case.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>What</th>
                <th>For</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {r.events.map((e) => (
                <tr key={`${e.case_id}-${e.kind}-${e.on}`}>
                  <td className="nowrap">{day(e.on)}</td>
                  <td>{EVENT_TAG[e.kind]}</td>
                  <td>{e.text}</td>
                  <td className="right">
                    <Link href={`/cases/${e.case_id}`} className="link-action">
                      Open
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Open cases</h2>
          <p>What each one could still cost: the order if one is passed, otherwise the claim</p>
        </div>
        {open.length === 0 ? (
          <p className="empty">No case is open on this project.</p>
        ) : (
          <CaseTable cases={open} />
        )}
        {closed.length > 0 ? (
          <details className="disclosure">
            <summary>Closed cases ({closed.length})</summary>
            <CaseTable cases={closed} />
          </details>
        ) : null}
      </section>

      {r.patterns.total > 0 ? <PatternsSection r={r} /> : null}

      {r.can_edit ? <NewCase r={r} projectId={id} /> : null}
    </>
  );
}

function CaseTable({ cases }: { cases: Disputes["cases"] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Case</th>
          <th>Brought by</th>
          <th>Sought</th>
          <th>Status</th>
          <th className="right">Could cost</th>
          <th>Next</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {cases.map((c) => (
          <tr key={c.id}>
            <td>
              {c.case_number}
              <br />
              <span className="small muted">{c.forum_label}</span>
            </td>
            <td>
              {c.complainant}
              {c.unit ? <span className="small muted">{`, ${c.unit}`}</span> : null}
            </td>
            <td>{c.relief_label}</td>
            <td>{c.status_label}</td>
            <td className="right num">{Number(c.at_stake) > 0 ? inr(c.at_stake) : ""}</td>
            <td className="nowrap">{c.next ? `${EVENT_TAG[c.next.kind]}, ${day(c.next.on)}` : ""}</td>
            <td className="right">
              <Link href={`/cases/${c.id}`} className="link-action">
                Open
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PatternsSection({ r }: { r: Disputes }) {
  const p = r.patterns;
  return (
    <section className="section">
      <div className="section-head">
        <h2>Patterns</h2>
        <p>Where complaints come from, to deal with the cause and not only the case</p>
      </div>
      <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
        {p.possession_due_on ? (
          <li>
            <span>Filed after the promised possession date ({day(p.possession_due_on)})</span>
            <span className="num">
              {p.filed_after_possession_due} of {p.with_filing_date}
            </span>
          </li>
        ) : null}
        <li>
          <span>Booked units with a case</span>
          <span className="num">
            {p.units_with_cases} of {p.booked_units}
          </span>
        </li>
        {p.by_relief.map((x) => (
          <li key={`relief-${x.label}`}>
            <span className="muted">Seeking: {x.label.toLowerCase()}</span>
            <span className="num">{x.count}</span>
          </li>
        ))}
        {p.by_forum.map((x) => (
          <li key={`forum-${x.label}`}>
            <span className="muted">At the {x.label}</span>
            <span className="num">{x.count}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function NewCase({ r, projectId }: { r: Disputes; projectId: string }) {
  return (
    <section className="section">
      <details className="disclosure">
        <summary>Record a new case</summary>
        <p className="small muted" style={{ marginBottom: 12 }}>
          From the notice or the complaint. Choose the unit and Lekhara fills in the buyer and works
          out what the case could cost from what they paid.
        </p>
        <ActionForm
          action={createCase.bind(null, projectId)}
          label="Record the case"
          pendingLabel="Recording"
        >
          <div className="field-grid">
            <div className="field">
              <label htmlFor="forum">Where</label>
              <select id="forum" name="forum" defaultValue="krera">
                {r.choices.forums.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="case_number">Case number</label>
              <input id="case_number" name="case_number" required />
            </div>
            <div className="field">
              <label htmlFor="relief">What is sought</label>
              <select id="relief" name="relief" defaultValue="delay_interest">
                {r.choices.reliefs.map((x) => (
                  <option key={x.value} value={x.value}>
                    {x.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="unit">Unit, if a buyer brought it</label>
              <input id="unit" name="unit" list="booked-units" autoComplete="off" />
              <datalist id="booked-units">
                {r.units.map((u) => (
                  <option key={u} value={u} />
                ))}
              </datalist>
            </div>
            <div className="field">
              <label htmlFor="complainant">Brought by, if not a buyer</label>
              <input id="complainant" name="complainant" />
            </div>
            <div className="field">
              <label htmlFor="claim_amount">Amount claimed (rupees, if any)</label>
              <input id="claim_amount" name="claim_amount" inputMode="decimal" />
            </div>
            <div className="field">
              <label htmlFor="filed_on">Filed on</label>
              <input id="filed_on" name="filed_on" type="date" />
            </div>
            <div className="field">
              <label htmlFor="notice_received_on">Notice received on</label>
              <input id="notice_received_on" name="notice_received_on" type="date" />
            </div>
            <div className="field">
              <label htmlFor="reply_due_on">Reply due by</label>
              <input id="reply_due_on" name="reply_due_on" type="date" />
            </div>
            <div className="field">
              <label htmlFor="next_hearing_on">First hearing</label>
              <input id="next_hearing_on" name="next_hearing_on" type="date" />
            </div>
            <div className="field">
              <label htmlFor="lawyer">Your lawyer</label>
              <input id="lawyer" name="lawyer" />
            </div>
            <div className="field field-wide">
              <label htmlFor="summary">What the complaint says</label>
              <textarea id="summary" name="summary" rows={3} />
            </div>
          </div>
        </ActionForm>
      </details>
    </section>
  );
}
