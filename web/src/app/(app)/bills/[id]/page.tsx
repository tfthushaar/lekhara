import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { deleteBill, updateBill } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { History } from "@/components/history";
import { BillFields } from "@/components/purchase-fields";
import { api } from "@/lib/api";
import { day, inrFull } from "@/lib/format";

export const metadata: Metadata = { title: "Bill" };

export default function BillPage({ params }: PageProps<"/bills/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the bill</p>}>
      <BillView params={params} />
    </Suspense>
  );
}

async function BillView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const b = await api.bill(id);
  const base = `/projects/${b.project_id}`;
  const gst = Number(b.gst_amount ?? 0);
  const cost = Number(b.taxable_value) + (b.gst_is_cost ? gst : 0);

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={base}>{b.project_name}</Link>
            {"  /  "}
            <Link href={`${base}/suppliers`}>Suppliers and bills</Link>
          </p>
          <h1>{`Bill ${b.bill_no}`}</h1>
          <p>
            <Link href={`/suppliers/${b.supplier.id}`}>{b.supplier.name}</Link>
            {`, ${day(b.bill_date)}. ${b.paid_on ? `Paid on ${day(b.paid_on)}.` : "Unpaid."}`}
            {b.source === "Tally" ? " From Tally." : ""}
          </p>
        </div>
      </div>

      <section>
        <ul className="calc" style={{ maxWidth: 640 }}>
          <li>
            <span className="muted">Taxable value</span>
            <span>{inrFull(b.taxable_value)}</span>
          </li>
          <li>
            <span className="muted">GST</span>
            <span>{b.gst_amount ? inrFull(b.gst_amount) : "Not given"}</span>
          </li>
          <li>
            <span className="muted">Accepted on</span>
            <span>{day(b.accepted_on)}</span>
          </li>
          <li>
            <span className="muted">Cost</span>
            <span>
              {b.cost_line
                ? `${inrFull(String(cost))} on ${b.cost_line.code}, ${b.cost_line.name}${b.gst_is_cost && gst ? ", with the GST, as the project's GST scheme gives no input credit" : ""}`
                : "Not counted here: no cost line"}
            </span>
          </li>
          <li>
            <span className="muted">The 80% test</span>
            <span>
              {b.excluded
                ? "Left out"
                : b.supplier.registered
                  ? "Counts as from a registered supplier"
                  : "Counts as from an unregistered supplier"}
            </span>
          </li>
        </ul>
      </section>

      {b.can_edit ? (
        <section className="section">
          <div className="section-head">
            <h2>Change the bill</h2>
            {b.source === "Tally" ? <p>It came from Tally: change it there too, or the next import will not carry the change.</p> : null}
          </div>
          <div style={{ marginTop: 12 }}>
            <ActionForm action={updateBill.bind(null, b.id)} label="Save" pendingLabel="Saving">
              <BillFields prefix="bill" lines={b.cost_lines} suppliers={[]} bill={b} />
            </ActionForm>
          </div>
          {b.can_delete ? (
            <details className="disclosure">
              <summary>Delete the bill</summary>
              <p className="small muted" style={{ margin: "8px 0 12px" }}>
                For a bill entered by mistake. Its cost comes off the cost line; its history is kept.
              </p>
              <ActionForm action={deleteBill.bind(null, b.id, b.project_id)} label="Delete the bill" pendingLabel="Deleting" secondary />
            </details>
          ) : null}
        </section>
      ) : null}

      <section className="section">
        <History entries={b.history} />
      </section>
    </>
  );
}
