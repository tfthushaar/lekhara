import Link from "next/link";
import { Suspense } from "react";

import { createBill, createSupplier } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { BillFields, SupplierFields } from "@/components/purchase-fields";
import { api } from "@/lib/api";
import { day, inr } from "@/lib/format";

export default function SuppliersPage({ params }: PageProps<"/projects/[id]/suppliers">) {
  return (
    <Suspense fallback={<p className="loading">Loading suppliers and bills</p>}>
      <SuppliersView params={params} />
    </Suspense>
  );
}

async function SuppliersView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await api.purchases(id);
  const withGst = p.bills.some((b) => b.gst_amount);
  const withLine = p.bills.some((b) => b.cost_line);
  const withSource = p.bills.some((b) => b.source !== "Lekhara");
  const withUdyam = p.suppliers.some((x) => x.udyam_number);

  return (
    <>
      <section className="section">
        <div className="section-head">
          <h2>Suppliers&apos; bills</h2>
          <p>{`${p.bills.length} bills, ${p.totals.unpaid} unpaid`}</p>
        </div>
        <p className="small" style={{ marginTop: 12 }}>
          <a href={`/download/projects/${id}/exports/bills.xlsx`} className="link-action">
            Download as Excel
          </a>
          {"  ·  "}
          <Link href={`/projects/${id}/import`} className="link-action">
            Add a sheet of bills
          </Link>
          {p.can_edit && p.bills.length > 0 ? (
            <>
              {"  ·  "}
              <Link href={`/projects/${id}/table/bills`} className="link-action">
                Edit as a table
              </Link>
            </>
          ) : null}
        </p>
        {p.can_edit ? (
          <details className="disclosure">
            <summary>Add a bill</summary>
            <ActionForm action={createBill.bind(null, id)} label="Add the bill" pendingLabel="Adding">
              <BillFields prefix="new-bill" lines={p.cost_lines} suppliers={p.suppliers} />
            </ActionForm>
          </details>
        ) : null}
        {p.bills.length === 0 ? (
          <p className="empty">No bills yet. Add your Tally file and they come in by themselves, or add one here.</p>
        ) : (
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Supplier</th>
                <th>Bill</th>
                <th>Date</th>
                <th className="right">Taxable</th>
                {withGst ? <th className="right">GST</th> : null}
                {withLine ? <th>Cost line</th> : null}
                <th>Paid</th>
                {withSource ? <th>From</th> : null}
              </tr>
            </thead>
            <tbody>
              {p.bills.map((b) => (
                <tr key={b.id}>
                  <td>
                    <Link href={`/suppliers/${b.supplier.id}`}>{b.supplier.name}</Link>
                    {!b.supplier.registered ? <span className="small muted"> unregistered</span> : null}
                  </td>
                  <td>
                    <Link href={`/bills/${b.id}`}>{b.bill_no}</Link>
                  </td>
                  <td className="nowrap">{day(b.bill_date)}</td>
                  <td className="right num">{inr(b.taxable_value)}</td>
                  {withGst ? <td className="right num">{b.gst_amount ? inr(b.gst_amount) : ""}</td> : null}
                  {withLine ? <td>{b.cost_line ? b.cost_line.code : ""}</td> : null}
                  <td className="nowrap">{b.paid_on ? day(b.paid_on) : <span className="muted">Unpaid</span>}</td>
                  {withSource ? <td className="small muted">{b.source}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <details className="disclosure">
<summary>{`Your suppliers (${p.suppliers.length})`}</summary>
<section className="section">
        <div className="section-head">
          <h2>Suppliers</h2>
          <p>Shared by all your projects</p>
        </div>
        <p className="small" style={{ marginTop: 12 }}>
          <a href={`/download/projects/${id}/exports/suppliers.xlsx`} className="link-action">
            Export to Excel
          </a>
          {"  ·  "}
          <Link href={`/projects/${id}/import#purchases`} className="link-action">
            Import a list of suppliers
          </Link>
          {p.can_edit && p.suppliers.length > 0 ? (
            <>
              {"  ·  "}
              <Link href={`/projects/${id}/table/suppliers`} className="link-action">
                Edit as a table
              </Link>
            </>
          ) : null}
        </p>
        {p.can_edit ? (
          <details className="disclosure">
            <summary>Add a supplier</summary>
            <ActionForm action={createSupplier.bind(null, id)} label="Add the supplier" pendingLabel="Adding">
              <SupplierFields prefix="new-supplier" />
            </ActionForm>
          </details>
        ) : null}
        {p.suppliers.length === 0 ? (
          <p className="empty">No suppliers yet.</p>
        ) : (
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Supplier</th>
                <th>GSTIN</th>
                <th>MSME</th>
                {withUdyam ? <th>Udyam</th> : null}
                <th className="right">Bills here</th>
              </tr>
            </thead>
            <tbody>
              {p.suppliers.map((s) => (
                <tr key={s.id}>
                  <td>
                    <Link href={`/suppliers/${s.id}`}>{s.name}</Link>
                  </td>
                  <td className="nowrap">{s.gstin ?? <span className="muted">Not registered</span>}</td>
                  <td>{s.msme_label}</td>
                  {withUdyam ? <td className="nowrap">{s.udyam_number ?? ""}</td> : null}
                  <td className="right num">
                    {s.bills ? `${s.bills}${s.unpaid ? ` (${s.unpaid} unpaid)` : ""}` : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
</details>
    </>
  );
}
