import { Suspense } from "react";

import { api } from "@/lib/api";
import { inr, pct } from "@/lib/format";

export default function UnitsPage({ params }: PageProps<"/projects/[id]/units">) {
  return (
    <Suspense fallback={<p className="loading">Loading units and landowners</p>}>
      <UnitsView params={params} />
    </Suspense>
  );
}

async function UnitsView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const u = await api.units(id);
  const s = u.summary;

  return (
    <>
      <div className="stats">
        <div className="stat">
          <p className="stat-label">Units</p>
          <p className="stat-value">{s.total}</p>
          <p className="stat-note">In the project</p>
        </div>
        <div className="stat">
          <p className="stat-label">Yours</p>
          <p className="stat-value">{s.developer}</p>
          <p className="stat-note">
            {s.developer_booked} booked, {s.developer_unbooked} unbooked
          </p>
        </div>
        <div className="stat">
          <p className="stat-label">Landowner&apos;s</p>
          <p className="stat-value">{s.landowner}</p>
          <p className="stat-note">
            {s.landowner ? "Allotted under the joint development agreement" : "No area share"}
          </p>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>Landowners</h2>
          <p>Entitlements and payments under each joint development agreement</p>
        </div>
        {u.landowners.length === 0 ? (
          <p className="empty">This project is on the developer&apos;s own land.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Landowner</th>
                <th>Share</th>
                <th className="right">Refundable deposit</th>
                <th className="right">Paid to date</th>
                <th className="right">TDS deducted</th>
              </tr>
            </thead>
            <tbody>
              {u.landowners.map((o) => (
                <tr key={o.name}>
                  <td>{o.name}</td>
                  <td>
                    {pct(o.share_pct)} of {o.share_type === "area" ? "the built area" : "revenue"}
                  </td>
                  <td className="right num">{inr(o.refundable_deposit)}</td>
                  <td className="right num">{inr(o.paid_to_date)}</td>
                  <td className="right num">{inr(o.tds_to_date)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Units</h2>
          <p>Whose each unit is, and whether it is priced near guidance value</p>
        </div>
        <table className="table">
          <thead>
            <tr>
              <th>Unit</th>
              <th>Tower</th>
              <th className="right">Carpet area</th>
              <th>Whose</th>
              <th>Status</th>
              <th className="right">Price</th>
              <th className="right">Guidance value</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {u.units.map((unit) => (
              <tr key={unit.label}>
                <td>{unit.label}</td>
                <td>{unit.tower}</td>
                <td className="right num">{unit.carpet_area_sqft.toLocaleString("en-IN")} sq ft</td>
                <td>{unit.owner_share === "landowner" ? "Landowner" : "Yours"}</td>
                <td>{unit.owner_share === "landowner" ? "Allotted" : unit.booked ? "Booked" : "Unbooked"}</td>
                <td className="right num">{inr(unit.agreement_value ?? unit.list_price)}</td>
                <td className="right num">{inr(unit.guidance_value)}</td>
                <td>{unit.below_guidance ? <span className="tag tag-soon">Below guidance</span> : null}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
