import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { applyGst, gstChoices, undoGst } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type GstReview, type TallyAlert, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export const metadata: Metadata = { title: "GST return" };

export default function GstPage({ params }: PageProps<"/gst/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Checking the return against your bills</p>}>
      <GstView params={params} />
    </Suspense>
  );
}

const LEVEL: Record<TallyAlert["level"], { label: string; className: string }> = {
  blocking: { label: "Waiting for you", className: "tag tag-fail" },
  missing: { label: "Check", className: "tag tag-soon" },
  info: { label: "Note", className: "tag tag-upcoming" },
};

const OUTCOME: Record<GstReview["lines"][number]["outcome"], { label: string; className: string }> = {
  matched: { label: "Agrees", className: "tag tag-done" },
  differs: { label: "Differs", className: "tag tag-soon" },
  missing: { label: "No bill", className: "tag tag-fail" },
  note: { label: "Note", className: "tag" },
};

async function GstView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const g = await api.gst(id);
  const base = `/projects/${g.project_id}`;
  const c = g.counts;
  const invoices = g.lines.filter((l) => l.kind === "invoice");

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{g.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/import`}>Import</Link>
          </p>
          <h1>{`${g.form}${g.period_label ? `, ${g.period_label}` : ""}`}</h1>
          <p>{`${g.filename}${g.gstin ? `, for GSTIN ${g.gstin}` : ""}. ${plural(invoices.length, "invoice")} from suppliers.`}</p>
        </div>
      </div>

      <p className="status-line">
        {g.status === "applied"
          ? `Brought in: ${plural(g.result?.gstins.length ?? 0, "GSTIN")} filled in, ${plural(g.result?.suppliers.length ?? 0, "supplier")} and ${plural(g.result?.bills.length ?? 0, "bill")} added.`
          : g.status === "undone"
            ? "This return was undone; what it brought in has been taken out."
            : "Nothing is saved yet. Check the return against your bills, then bring in what it adds."}
      </p>

      <div className="stats">
        <div className="stat">
          <p className="stat-label">Agree with your bills</p>
          <p className="stat-value">{c.matched ?? 0}</p>
          <p className="stat-note">{`${c.differs ?? 0} with different amounts`}</p>
        </div>
        <div className="stat">
          <p className="stat-label">Not reported by the supplier</p>
          <p className="stat-value">{c.unreported ?? 0}</p>
          <p className="stat-note">Bills in Lekhara for the month</p>
        </div>
        <div className="stat">
          <p className="stat-label">No bill in Lekhara</p>
          <p className="stat-value">{c.missing ?? 0}</p>
          <p className="stat-note">Reported by suppliers</p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>What needs attention</h2>
        </div>
        {g.alerts.length === 0 ? (
          <p className="empty">The return agrees with your bills.</p>
        ) : (
          <ul className="rows">
            {g.alerts.map((a) => (
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

      {g.unreported.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Bills the suppliers have not reported</h2>
          </div>
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Bill</th>
                <th>Date</th>
                <th className="right">Taxable</th>
              </tr>
            </thead>
            <tbody>
              {g.unreported.map((b) => (
                <tr key={b.bill_id}>
                  <td>{b.supplier}</td>
                  <td>
                    <Link href={`/bills/${b.bill_id}`}>{b.bill_no}</Link>
                  </td>
                  <td className="nowrap">{day(b.bill_date)}</td>
                  <td className="right num">{inr(b.taxable)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="section">
        <details className="disclosure">
          <summary>{`Every invoice in the return (${g.lines.length})`}</summary>
        <table className="table" style={{ marginTop: 12 }}>
          <thead>
            <tr>
              <th>Supplier</th>
              <th>Invoice</th>
              <th>Date</th>
              <th className="right">Taxable</th>
              <th className="right">GST</th>
              <th>In Lekhara</th>
            </tr>
          </thead>
          <tbody>
            {g.lines.map((l, i) => (
              <tr key={`${l.supplier_gstin}-${l.number}-${i}`}>
                <td>
                  {l.supplier_name ?? l.supplier_gstin}
                  <br />
                  <span className="small muted">{l.supplier_gstin}</span>
                </td>
                <td>
                  {l.bill_id ? <Link href={`/bills/${l.bill_id}`}>{l.number}</Link> : l.number}
                  {l.kind !== "invoice" ? <span className="small muted">{l.kind === "credit_note" ? " credit note" : " debit note"}</span> : null}
                </td>
                <td className="nowrap">{l.date ? day(l.date) : ""}</td>
                <td className="right num">{inr(l.taxable)}</td>
                <td className="right num">{inr(l.gst)}</td>
                <td>
                  <span className={OUTCOME[l.outcome].className}>{OUTCOME[l.outcome].label}</span>
                  {l.note ? <span className="small muted">{` ${l.note}`}</span> : null}
                  {l.itc_available === false ? <span className="small muted"> No credit</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </details>
      </section>

      {g.can_edit ? (
        <section className="section">
          <div className="section-head">
            <h2>Bring it in</h2>
            <p>Suppliers&apos; GSTINs are filled in and new suppliers added either way</p>
          </div>
          <div style={{ maxWidth: 720, marginTop: 12 }}>
            <ActionForm action={gstChoices.bind(null, g.id)} label="Save" pendingLabel="Saving" secondary>
              <div className="checks">
                <label>
                  <input type="checkbox" name="add_missing" value="yes" defaultChecked={g.add_missing} />
                  <span className="small">
                    {`Add the ${plural(c.missing ?? 0, "invoice")} with no bill as bills in this project. Leave this off if your bills come from Tally, or if they belong to another project.`}
                  </span>
                </label>
              </div>
            </ActionForm>
            <ActionForm action={applyGst.bind(null, g.id)} label="Bring it in" pendingLabel="Bringing it in" />
          </div>
        </section>
      ) : null}

      {g.can_undo ? (
        <section className="section">
          <details className="disclosure">
            <summary>Undo this return</summary>
            <p className="small muted" style={{ margin: "8px 0 12px", maxWidth: 640 }}>
              Takes out the bills and suppliers it added and the GSTINs it filled in. Possible for 30 days.
            </p>
            <ActionForm action={undoGst.bind(null, g.id)} label="Undo the return" pendingLabel="Undoing" secondary />
          </details>
        </section>
      ) : null}
    </>
  );
}
