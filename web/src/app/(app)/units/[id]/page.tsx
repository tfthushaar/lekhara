import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { deleteReceipt, deleteUnit, markUnsold, recordReceipt, updateHandover, updateUnit } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { History } from "@/components/history";
import { LinkedDocuments } from "@/components/documents";
import { PrintButton } from "@/components/print-button";
import { UnitFields } from "@/components/unit-fields";
import { type UnitDetail, type UnitHandover, api } from "@/lib/api";
import { day, inr, inrFull } from "@/lib/format";

export const metadata: Metadata = { title: "Unit" };

export default function UnitPage({ params }: PageProps<"/units/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the unit</p>}>
      <UnitView params={params} />
    </Suspense>
  );
}

function stepClass(u: UnitHandover, stage: string, done: boolean): string {
  if (done) return "step step-done";
  return u.blocker === stage ? "step step-current" : "step";
}


async function UnitView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const unit = await api.unit(id);
  const base = `/projects/${unit.project_id}`;

  return (
    <>
      <div className="page-head no-print">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{unit.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/units`}>Units</Link>
          </p>
          <h1>Unit {unit.label}</h1>
          <p>
            {unit.booked ? `Sold to ${unit.buyer_name}` : "Not sold"}
            {unit.tower ? `. ${unit.tower}` : ""}. {unit.carpet_area_sqft.toLocaleString("en-IN")} sq ft carpet.
          </p>
        </div>
      </div>

      <UnitDetails unit={unit} />
      {unit.booked ? <Payments unit={unit} /> : null}

      {unit.booked ? (
        <Suspense fallback={<p className="loading">Loading the handover steps</p>}>
          <HandoverView id={id} />
        </Suspense>
      ) : (
        <Suspense fallback={null}>
          <LinkedDocuments
            linkType="unit"
            linkId={unit.id}
            category="agreement"
            hint="The booking form, allotment letter and agreement for sale"
          />
        </Suspense>
      )}
    </>
  );
}

function UnitDetails({ unit }: { unit: UnitDetail }) {
  return (
    <section className="no-print" style={{ marginBottom: 40 }}>
      <div className="section-head">
        <h2>Details</h2>
        <p>Whose it is, its price and its buyer</p>
      </div>
      <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
        <Fact label="Whose share" value={unit.owner_share_label} />
        <Fact label="List price" value={inrFull(unit.list_price)} />
        <Fact label="Guidance value" value={inrFull(unit.guidance_value)} />
        {unit.booked ? (
          <>
            <Fact label="Buyer" value={unit.buyer_name ?? ""} />
            <Fact label="Phone and email" value={[unit.buyer_phone, unit.buyer_email].filter(Boolean).join(", ") || "Not recorded"} />
            <Fact label="Booked on" value={day(unit.booked_on)} />
            <Fact label="Agreement value" value={inrFull(unit.agreement_value)} />
          </>
        ) : null}
      </ul>
      {unit.can_edit ? (
        <>
          <details className="disclosure">
            <summary>Change the details</summary>
            <ActionForm action={updateUnit.bind(null, unit.id)} label="Save the changes" pendingLabel="Saving">
              <UnitFields unit={unit} prefix="edit-unit" />
            </ActionForm>
          </details>
          {unit.booked ? (
            <details className="disclosure">
              <summary>The booking was cancelled</summary>
              <p className="small muted" style={{ margin: "8px 0 12px", maxWidth: 640 }}>
                Marks the unit unsold and clears the buyer. Not possible once demands have been
                raised or money received.
              </p>
              <ActionForm action={markUnsold.bind(null, unit.id)} label="Mark as unsold" pendingLabel="Saving" secondary />
            </details>
          ) : null}
          {unit.can_delete ? (
            <details className="disclosure">
              <summary>Delete this unit</summary>
              <p className="small muted" style={{ margin: "8px 0 12px" }}>
                For a unit entered by mistake. Its history is kept.
              </p>
              <ActionForm action={deleteUnit.bind(null, unit.id)} label="Delete the unit" pendingLabel="Deleting" secondary />
            </details>
          ) : null}
        </>
      ) : null}
      <History entries={unit.history} />
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <li>
      <span className="muted">{label}</span>
      <span>{value}</span>
    </li>
  );
}

async function HandoverView({ id }: { id: string }) {
  const u = await api.unitHandover(id);

  return (
    <>
      <div className="no-print">
        <div className="section-head">
          <h2>Handover</h2>
          <p>From the occupancy certificate to possession</p>
        </div>
        <p className="status-line">{u.blocker_text}</p>
        <ol className="steps steps-8" style={{ marginBottom: 40 }}>
          {u.steps.map((s) => (
            <li key={s.stage} className={stepClass(u, s.stage, s.done)}>
              {s.label}
            </li>
          ))}
        </ol>

        <section>
          <div className="section-head">
            <h2>Next step</h2>
          </div>
          <div style={{ marginTop: 16, maxWidth: 560 }}>
            <NextStep u={u} />
          </div>
        </section>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Sale deed fact sheet</h2>
          <p>The facts your lawyer needs for the deed, taken from the books</p>
        </div>
        <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
          {u.fact_sheet.map((f) => (
            <li key={f.label}>
              <span className="muted">{f.label}</span>
              <span>{f.value}</span>
            </li>
          ))}
        </ul>
        <div className="no-print" style={{ marginTop: 16 }}>
          <PrintButton label="Print the fact sheet" />
        </div>
      </section>

      <section className="section no-print">
        <div className="section-head">
          <h2>Stamp duty and fees, estimated</h2>
          <p>Paid by the buyer at registration. Confirm the rates before quoting them.</p>
        </div>
        <ul className="calc" style={{ marginTop: 12, maxWidth: 640 }}>
          <li>
            <span>Worked out on the higher of the agreement value and the guidance value</span>
            <span className="num">{inrFull(u.cost.base)}</span>
          </li>
          <li>
            <span>Stamp duty</span>
            <span className="num">{inrFull(u.cost.stamp_duty)}</span>
          </li>
          <li>
            <span>Cess on the stamp duty</span>
            <span className="num">{inrFull(u.cost.cess)}</span>
          </li>
          <li>
            <span>Registration fee</span>
            <span className="num">{inrFull(u.cost.registration_fee)}</span>
          </li>
          <li className="calc-total">
            <span>Total</span>
            <span className="num">{inrFull(u.cost.total)}</span>
          </li>
        </ul>
      </section>

      <Suspense fallback={null}>
        <LinkedDocuments
          linkType="unit"
          linkId={u.unit_id}
          category={u.registered_on ? "sale_deed" : "ekhata"}
          hint="The e-Khata, the registered sale deed and the possession letter"
        />
      </Suspense>

      {u.can_edit ? (
        <section className="section no-print">
          <details className="disclosure">
            <summary>Correct a recorded detail</summary>
            <ActionForm
              action={updateHandover.bind(null, u.unit_id)}
              label="Save the changes"
              pendingLabel="Saving"
              secondary
            >
              <div className="field-grid">
                <EkhataFields u={u} prefix="fix-" />
                <DateField
                  name="deed_drafted_on"
                  label="Sale deed drafted on"
                  value={u.deed_drafted_on}
                  prefix="fix-"
                />
                <DateField
                  name="appointment_on"
                  label="Registration appointment"
                  value={u.appointment_on}
                  prefix="fix-"
                />
                <DateField
                  name="registered_on"
                  label="Registered on"
                  value={u.registered_on}
                  prefix="fix-"
                />
                <div className="field">
                  <label htmlFor="fix-document_no">Registered document number</label>
                  <input
                    id="fix-document_no"
                    name="document_no"
                    defaultValue={u.document_no ?? ""}
                  />
                </div>
                <DateField
                  name="possession_on"
                  label="Possession handed over on"
                  value={u.possession_on}
                  prefix="fix-"
                />
              </div>
            </ActionForm>
          </details>
        </section>
      ) : null}
    </>
  );
}

function DateField({
  name,
  label,
  value,
  required = false,
  prefix = "",
}: {
  name: string;
  label: string;
  value?: string | null;
  required?: boolean;
  prefix?: string;
}) {
  return (
    <div className="field">
      <label htmlFor={prefix + name}>{label}</label>
      <input
        id={prefix + name}
        name={name}
        type="date"
        defaultValue={value ?? ""}
        required={required}
      />
    </div>
  );
}

function EkhataFields({ u, prefix = "" }: { u: UnitHandover; prefix?: string }) {
  return (
    <>
      <div className="field">
        <label htmlFor={`${prefix}ekhata_status`}>e-Khata</label>
        <select id={`${prefix}ekhata_status`} name="ekhata_status" defaultValue={u.ekhata_status}>
          <option value="none">Not applied</option>
          <option value="applied">Applied</option>
          <option value="draft">Draft received</option>
          <option value="final">Final received</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}khata_type`}>Khata type</label>
        <select id={`${prefix}khata_type`} name="khata_type" defaultValue={u.khata_type ?? ""}>
          <option value="">Not known yet</option>
          <option value="A">A-Khata</option>
          <option value="B">B-Khata</option>
        </select>
      </div>
    </>
  );
}

function NextStep({ u }: { u: UnitHandover }) {
  const base = `/projects/${u.project_id}`;
  const form = (label: string, children: React.ReactNode) =>
    u.can_edit ? (
      <ActionForm action={updateHandover.bind(null, u.unit_id)} label={label} pendingLabel="Saving">
        {children}
      </ActionForm>
    ) : (
      <p className="muted">The developer&apos;s team records this step.</p>
    );

  switch (u.blocker) {
    case "oc":
      return (
        <p>
          A sale deed can be registered only after the occupancy certificate is in. Nothing to do
          for this unit until then.
        </p>
      );
    case "ekhata":
      return (
        <>
          <p style={{ marginBottom: 16 }}>
            Since July 2025 a final e-Khata is needed before a flat can be registered in
            Bengaluru. Record it when it comes in.
          </p>
          {form("Save the e-Khata", <EkhataFields u={u} />)}
        </>
      );
    case "final_demand":
      return (
        <p>
          The instalment due on possession has not been demanded from this buyer yet.{" "}
          <Link href={`${base}/collections`} className="link-action">
            Raise it from collections
          </Link>
        </p>
      );
    case "payment":
      return (
        <p>
          The buyer still owes {inrFull(u.balance_due)}, including GST. The deed waits until the
          balance is paid; TDS the buyer deducted counts as paid.
        </p>
      );
    case "deed":
      return (
        <>
          <p style={{ marginBottom: 16 }}>
            Send the fact sheet below to your lawyer. Record the date once the deed is drafted and
            the buyer has seen it.
          </p>
          {form(
            "Mark the deed as drafted",
            <DateField name="deed_drafted_on" label="Drafted on" required />,
          )}
        </>
      );
    case "appointment":
      return (
        <>
          <p style={{ marginBottom: 16 }}>
            Book a slot at the sub-registrar office through Kaveri and let the buyer know.
          </p>
          {form(
            "Save the appointment",
            <DateField name="appointment_on" label="Appointment on" required />,
          )}
        </>
      );
    case "registration":
      return (
        <>
          <p style={{ marginBottom: 16 }}>
            Appointment on {day(u.appointment_on)}. Once the deed is registered, record the
            document number.
          </p>
          {form(
            "Record the registration",
            <>
              <DateField name="registered_on" label="Registered on" required />
              <div className="field">
                <label htmlFor="document_no">Registered document number</label>
                <input id="document_no" name="document_no" required />
              </div>
            </>,
          )}
        </>
      );
    case "possession":
      return (
        <>
          <p style={{ marginBottom: 16 }}>
            Registered on {day(u.registered_on)}, document {u.document_no}. Hand over the keys and
            the possession letter.
          </p>
          {form(
            "Record the handover",
            <DateField name="possession_on" label="Handed over on" required />,
          )}
        </>
      );
    default:
      return (
        <p>
          Registered on {day(u.registered_on)}, document {u.document_no}. Possession handed over on{" "}
          {day(u.possession_on)}. Nothing left for this unit
          {Number(u.balance_due) > 0 ? `; ${inr(u.balance_due)} is still owed` : ""}.
        </p>
      );
  }
}

function Payments({ unit }: { unit: UnitDetail }) {
  const total = unit.receipts.reduce((sum, r) => sum + Number(r.amount) + Number(r.tds), 0);
  return (
    <section className="no-print" style={{ marginBottom: 40 }}>
      <div className="section-head">
        <h2>Payments received</h2>
        <p>{`${inrFull(String(total))} so far, counting TDS the buyer deducted`}</p>
      </div>
      {unit.receipts.length === 0 ? (
        <p className="empty">No payments recorded yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>Received</th>
              <th className="right">Amount</th>
              <th className="right">TDS</th>
              <th>Reference</th>
              <th>From</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {unit.receipts.map((r) => (
              <tr key={r.id}>
                <td className="nowrap">{day(r.received_on)}</td>
                <td className="right num">{inrFull(r.amount)}</td>
                <td className="right num">{Number(r.tds) ? inrFull(r.tds) : ""}</td>
                <td>{r.reference}</td>
                <td className="small muted">{r.source}</td>
                <td className="right">
                  {unit.can_edit && r.can_delete ? (
                    <ActionForm action={deleteReceipt.bind(null, r.id)} label="Delete" pendingLabel="Deleting" secondary />
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {unit.can_edit ? (
        <details className="disclosure">
          <summary>Record a payment</summary>
          <ActionForm action={recordReceipt.bind(null, unit.id)} label="Record the payment" pendingLabel="Saving">
            <div className="field-grid">
              <div className="field">
                <label htmlFor="pay-on">Received on</label>
                <input id="pay-on" name="received_on" type="date" required />
              </div>
              <div className="field">
                <label htmlFor="pay-amount">Amount received (rupees)</label>
                <input id="pay-amount" name="amount" inputMode="decimal" required />
              </div>
              <div className="field">
                <label htmlFor="pay-tds">TDS the buyer deducted</label>
                <input id="pay-tds" name="tds_deducted" inputMode="decimal" />
              </div>
              <div className="field">
                <label htmlFor="pay-ref">UTR or cheque number</label>
                <input id="pay-ref" name="reference" />
              </div>
            </div>
          </ActionForm>
        </details>
      ) : null}
    </section>
  );
}
