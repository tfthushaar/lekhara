import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { saveGst, undoGst } from "@/app/actions";
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

const IMS: Record<GstReview["lines"][number]["ims_action"], string> = {
  accept: "tag tag-done",
  pending: "tag tag-soon",
  reject: "tag tag-fail",
  check: "tag",
};

function imsSummary(n: GstReview["ims"]): string {
  const parts = [
    n.accept ? `${n.accept} to accept` : "",
    n.pending ? `${n.pending} to keep pending` : "",
    n.reject ? `${n.reject} to reject` : "",
    n.check ? `${n.check} to check` : "",
  ].filter(Boolean);
  return parts.length ? `${parts.join(", ")}.` : "Nothing in the return.";
}

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
            <Link href={`${base}/import`}>Add files</Link>
          </p>
          <h1>{`${g.form}${g.period_label ? `, ${g.period_label}` : ""}`}</h1>
          <p>{`${g.filename}${g.gstin ? `, for GSTIN ${g.gstin}` : ""}. ${plural(invoices.length, "invoice")} from suppliers.`}</p>
        </div>
      </div>

      <p className="status-line">
        {g.status === "applied"
          ? `Saved: ${plural(g.result?.gstins.length ?? 0, "GSTIN")} filled in, ${plural(g.result?.suppliers.length ?? 0, "supplier")} and ${plural(g.result?.bills.length ?? 0, "bill")} added.`
          : g.status === "undone"
            ? "This return was undone; what it added has been taken out."
            : `${c.matched ?? 0} of your bills agree with the return. ${(c.differs ?? 0) + (c.unreported ?? 0) + (c.missing ?? 0) ? "The rest need a look, below." : "Nothing needs a look."}`}
      </p>

      {g.can_edit ? (
        <section>
          <ActionForm action={saveGst.bind(null, g.id)} label="Save it" pendingLabel="Saving">
            {(c.missing ?? 0) > 0 ? (
              <div className="checks" style={{ maxWidth: 720, marginBottom: 12 }}>
                <input type="hidden" name="asked" value="yes" />
                <label>
                  <input type="checkbox" name="add_missing" value="yes" defaultChecked={g.add_missing} />
                  <span>
                    {`Also add the ${plural(c.missing ?? 0, "invoice")} you have no bill for. Leave this off if your bills come from Tally.`}
                  </span>
                </label>
              </div>
            ) : null}
            <p className="small muted" style={{ marginBottom: 12 }}>Your suppliers&apos; GSTINs are filled in and new suppliers added.</p>
          </ActionForm>
        </section>
      ) : null}


      <section className="section">
        <div className="section-head">
          <h2>Before you save</h2>
        </div>
        {g.alerts.filter((a) => a.level !== "info").length === 0 && g.alerts.filter((a) => a.level === "info").length === 0 ? (
          <p className="empty">The return agrees with your bills.</p>
        ) : (
          <>
          <ul className="rows">
            {g.alerts.filter((a) => a.level !== "info").map((a) => (
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
          {g.alerts.filter((a) => a.level === "info").length > 0 ? (
            <details className="disclosure">
              <summary>{`Notes (${g.alerts.filter((a) => a.level === "info").length})`}</summary>
              <ul className="rows">
                {g.alerts.filter((a) => a.level === "info").map((a) => (
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
            </details>
          ) : null}
          </>
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
        <div className="section-head">
          <h2>What to accept on the GST portal</h2>
          <p>{imsSummary(g.ims)}</p>
        </div>
        <details className="disclosure">
          <summary>How accepting works</summary>
        <p className="small muted" style={{ maxWidth: 760, marginTop: 12 }}>
          On the GST portal, accept, reject or keep pending each invoice your suppliers report. GSTR-2B is drawn up on
          the 14th of the next month from what you accepted and what you left untouched, which counts as accepted. You
          can change your choices, and have GSTR-2B computed again, until you file GSTR-3B. The portal shows which
          choices each record allows.
        </p>
        </details>
        {g.lines.some((l) => l.ims_action !== "accept") ? (
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Invoice</th>
                <th className="right">GST</th>
                <th>Do</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {g.lines
                .filter((l) => l.ims_action !== "accept")
                .map((l, i) => (
                  <tr key={`${l.supplier_gstin}-${l.number}-${i}`}>
                    <td>{l.supplier_name ?? l.supplier_gstin}</td>
                    <td className="nowrap">
                      {l.number}
                      {l.kind !== "invoice" ? <span className="small muted">{l.kind === "credit_note" ? " credit note" : " debit note"}</span> : null}
                    </td>
                    <td className="right num">{inr(l.gst)}</td>
                    <td className="nowrap">
                      <span className={IMS[l.ims_action]}>{l.ims_label}</span>
                    </td>
                    <td className="small">{l.ims_reason}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        ) : (
          <p className="empty">Every invoice agrees with a bill: accept them all.</p>
        )}
        <div style={{ marginTop: 12 }}>
          <a href={`/download/gst/${g.id}/ims.csv`} className="link-action">
            Download the whole list, with what to do with each
          </a>
        </div>
      </section>

      <section className="section">
        <details className="disclosure">
          <summary>The numbers</summary>
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
        </details>
      </section>

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
              <th>In IMS</th>
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
                <td className="nowrap">
                  <span className={IMS[l.ims_action]}>{l.ims_label}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </details>
      </section>

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
