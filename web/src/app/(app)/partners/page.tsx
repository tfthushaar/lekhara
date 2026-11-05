import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { addPartner, payCommission, updatePartner } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type Partners, api } from "@/lib/api";
import { day, inr } from "@/lib/format";

export const metadata: Metadata = { title: "Channel partners" };

export default function PartnersPage() {
  return (
    <Suspense fallback={<p className="loading">Loading channel partners</p>}>
      <PartnersView />
    </Suspense>
  );
}

type Partner = Partners["partners"][number];
type Owed = Partners["to_pay"][number];

function PartnerFields({ p, prefix }: { p?: Partner; prefix: string }) {
  const field = (name: keyof Partner & string, label: string, extra: Record<string, string> = {}) => (
    <div className="field">
      <label htmlFor={`${prefix}-${name}`}>{label}</label>
      <input id={`${prefix}-${name}`} name={name} defaultValue={p ? String(p[name] ?? "") : ""} {...extra} />
    </div>
  );
  return (
    <>
      <div className="field-grid">
        {field("name", "Name", p ? {} : { required: "" })}
        {field("phone", "Phone")}
        {field("commission_pct", "Commission, as a % of the price", { placeholder: "2" })}
        {field("krera_number", "K-RERA agent number")}
        {field("krera_valid_until", "K-RERA valid until", { type: "date" })}
      </div>
      <details className="disclosure">
        <summary>More details</summary>
        <div className="field-grid">
          {field("firm", "Firm")}
          {field("email", "Email")}
          {field("gstin", "GSTIN, if they have one")}
          {field("pan", "PAN")}
          {field("payable_after_pct", "Pay them once the buyer has paid this % of the price", { placeholder: "10" })}
        </div>
      </details>
    </>
  );
}

function sum(c: Owed): string {
  const parts = [`${inr(c.amount)} commission`];
  if (Number(c.gst) > 0) parts.push(`plus ${inr(c.gst)} GST`);
  if (Number(c.tds) > 0) parts.push(`less ${inr(c.tds)} TDS`);
  return parts.join(", ");
}

async function PartnersView() {
  const data = await api.partners();

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
          </p>
          <h1>Channel partners</h1>
          <p>The brokers who bring you buyers, and what you owe them.</p>
        </div>
      </div>

      <section>
        <div className="section-head">
          <h2>To pay</h2>
        </div>
        {data.to_pay.length === 0 ? (
          <p className="empty">Nothing to pay right now.</p>
        ) : (
          <ul className="rows">
            {data.to_pay.map((c) => (
              <li key={c.id} className="row" style={{ gridTemplateColumns: "1fr auto" }}>
                <div>
                  <p className="row-title">{`${inr(c.payable)} to ${c.partner}`}</p>
                  <p className="row-detail">{`For ${c.buyer}, unit ${c.unit}, ${c.project}. ${sum(c)}.`}</p>
                </div>
                <div className="row-side">
                  {data.can_edit ? (
                    <ActionForm action={payCommission.bind(null, c.id)} label="Mark paid" pendingLabel="Saving" secondary className="inline-form">
                      <div className="field">
                        <label htmlFor={`pay-${c.id}`}>UTR or cheque number</label>
                        <input id={`pay-${c.id}`} name="reference" />
                      </div>
                    </ActionForm>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
        {data.waiting.length > 0 ? (
          <details className="disclosure">
            <summary>{`Not due yet (${data.waiting.length})`}</summary>
            <p className="small muted">These fall due once the buyer has paid enough of the price.</p>
            <ul className="rows">
              {data.waiting.map((c) => (
                <li key={c.id} className="row" style={{ gridTemplateColumns: "1fr" }}>
                  <div>
                    <p className="row-title">{`${inr(c.payable)} to ${c.partner}`}</p>
                    <p className="row-detail">{`For ${c.buyer}, unit ${c.unit}, ${c.project}.`}</p>
                  </div>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Your partners</h2>
          <p>A booking can only go to a partner whose K-RERA registration is valid on the day.</p>
        </div>
        {data.can_edit ? (
          <details className="disclosure">
            <summary>Add a partner</summary>
            <ActionForm action={addPartner} label="Add the partner" pendingLabel="Adding">
              <PartnerFields prefix="new-partner" />
            </ActionForm>
          </details>
        ) : null}
        {data.partners.length === 0 ? (
          <p className="empty">No channel partners yet.</p>
        ) : (
          <ul className="rows">
            {data.partners.map((p) => (
              <li key={p.id} className="row" style={{ gridTemplateColumns: "1fr" }}>
                <div>
                  <p className="row-title">
                    {p.firm ? `${p.name}, ${p.firm}` : p.name}
                    {p.active ? null : <span className="muted">{" (not working with them now)"}</span>}
                  </p>
                  <p className="row-detail">
                    {`${p.leads} leads, ${p.bookings} booked, ${inr(p.paid)} paid so far. `}
                    {p.krera_valid_until && !p.krera_lapsed ? `K-RERA valid until ${day(p.krera_valid_until)}.` : null}
                  </p>
                  {p.krera_lapsed ? (
                    <p>
                      <span className="tag tag-overdue">{p.krera_valid_until ? `K-RERA ended ${day(p.krera_valid_until)}` : "No K-RERA date recorded"}</span>
                    </p>
                  ) : null}
                  {data.can_edit ? (
                    <details className="disclosure">
                      <summary>Change their details</summary>
                      <ActionForm action={updatePartner.bind(null, p.id)} label="Save" pendingLabel="Saving" secondary>
                        <PartnerFields p={p} prefix={`partner-${p.id}`} />
                        <label className="field-check">
                          <input type="checkbox" name="active" value="yes" defaultChecked={p.active} /> We are working with them now
                        </label>
                      </ActionForm>
                    </details>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
