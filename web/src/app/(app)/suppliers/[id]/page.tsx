import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { deleteSupplier, updateSupplier } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { History } from "@/components/history";
import { SupplierFields } from "@/components/purchase-fields";
import { api } from "@/lib/api";
import { day, inr } from "@/lib/format";

export const metadata: Metadata = { title: "Supplier" };

export default function SupplierPage({ params }: PageProps<"/suppliers/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the supplier</p>}>
      <SupplierView params={params} />
    </Suspense>
  );
}

async function SupplierView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = await api.supplier(id);

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
          </p>
          <h1>{s.name}</h1>
          <p>
            {s.gstin ? `GSTIN ${s.gstin}` : "Not registered for GST"}
            {s.state ? `, ${s.state}` : ""}. {s.msme_label}
            {s.udyam_number ? `, ${s.udyam_number}` : ""}.
          </p>
        </div>
      </div>

      <section>
        <div className="section-head">
          <h2>Bills</h2>
          <p>{`${s.bills} in all, ${s.unpaid} unpaid`}</p>
        </div>
        {s.bill_list.length === 0 ? (
          <p className="empty">No bills from this supplier yet.</p>
        ) : (
          <table className="table" style={{ marginTop: 12 }}>
            <thead>
              <tr>
                <th>Bill</th>
                <th>Project</th>
                <th>Date</th>
                <th className="right">Taxable</th>
                <th>Paid</th>
              </tr>
            </thead>
            <tbody>
              {s.bill_list.map((b) => (
                <tr key={b.id}>
                  <td>
                    <Link href={`/bills/${b.id}`}>{b.bill_no}</Link>
                  </td>
                  <td>{b.project}</td>
                  <td className="nowrap">{day(b.bill_date)}</td>
                  <td className="right num">{inr(b.taxable_value)}</td>
                  <td className="nowrap">{b.paid_on ? day(b.paid_on) : <span className="muted">Unpaid</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {s.can_edit ? (
        <section className="section">
          <div className="section-head">
            <h2>Change the details</h2>
            <p>For every project; the 80% test and the MSME clock follow at once</p>
          </div>
          <div style={{ marginTop: 12 }}>
            <ActionForm action={updateSupplier.bind(null, s.id)} label="Save" pendingLabel="Saving">
              <SupplierFields prefix="supplier" supplier={s} />
            </ActionForm>
          </div>
          {s.can_delete ? (
            <details className="disclosure">
              <summary>Delete the supplier</summary>
              <p className="small muted" style={{ margin: "8px 0 12px" }}>
                Only a supplier with no bills or orders can be deleted.
              </p>
              <ActionForm action={deleteSupplier.bind(null, s.id, "/projects")} label="Delete the supplier" pendingLabel="Deleting" secondary />
            </details>
          ) : null}
        </section>
      ) : null}

      <section className="section">
        <History entries={s.history} />
      </section>
    </>
  );
}
