import Link from "next/link";
import { Suspense } from "react";

import { createLandowner, createUnit, updateLandowner } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { UnitFields } from "@/components/unit-fields";
import { api } from "@/lib/api";
import { inr, pct } from "@/lib/format";

export default function UnitsPage({ params, searchParams }: PageProps<"/projects/[id]/units">) {
  return (
    <Suspense fallback={<p className="loading">Loading units and landowners</p>}>
      <UnitsView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

const PAGE = 50;

async function UnitsView({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const one = (key: string) => (typeof query[key] === "string" ? (query[key] as string) : "");
  const [tower, status, search, all] = [one("tower"), one("status"), one("q").trim(), one("all") === "1"];
  const [u, list] = await Promise.all([api.units(id), api.imports(id)]);
  const s = u.summary;
  const towers = [...new Set(u.units.map((x) => x.tower).filter(Boolean))].sort();
  const needle = search.toLowerCase();
  const shown = u.units.filter(
    (x) =>
      (!tower || x.tower === tower) &&
      (!status ||
        (status === "sold" && x.booked) ||
        (status === "unsold" && !x.booked && x.owner_share !== "landowner") ||
        (status === "landowner" && x.owner_share === "landowner") ||
        (status === "below" && x.below_guidance)) &&
      (!needle || x.label.toLowerCase().includes(needle) || (x.buyer_name ?? "").toLowerCase().includes(needle)),
  );
  const filtered = Boolean(tower || status || needle);
  const visible = all ? shown : shown.slice(0, PAGE);

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
        {list.can_import ? (
          <details className="disclosure">
            <summary>Add a landowner</summary>
            <ActionForm action={createLandowner.bind(null, id)} label="Add the landowner" pendingLabel="Adding">
              <LandownerFields prefix="new-lo" />
            </ActionForm>
          </details>
        ) : null}
        {u.landowners.length === 0 ? (
          <p className="empty">No landowners recorded. Add them if this project is a joint development.</p>
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
                <tr key={o.id}>
                  <td>
                    {o.name}
                    <br />
                    <span className="small muted">{o.pan ? `PAN ${o.pan}` : "PAN not recorded"}</span>
                    {list.can_import ? (
                      <details className="disclosure">
                        <summary>Change</summary>
                        <ActionForm action={updateLandowner.bind(null, o.id)} label="Save" pendingLabel="Saving" secondary>
                          <LandownerFields prefix={`lo-${o.id}`} owner={o} />
                        </ActionForm>
                      </details>
                    ) : null}
                  </td>
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
        <p className="chips" style={{ alignItems: "center" }}>
          {list.can_import ? (
            <Link href={`/projects/${id}/import`} className="button">
              Import from Excel
            </Link>
          ) : null}
          <a href={`/download/projects/${id}/exports/units.xlsx`} className="button button-secondary">
            Download as Excel
          </a>
          <a href={`/download/projects/${id}/exports/units.csv`} className="link-action">
            or CSV
          </a>
        </p>
        {list.can_import ? (
          <details className="disclosure">
            <summary>Add a unit by hand</summary>
            <ActionForm action={createUnit.bind(null, id)} label="Add the unit" pendingLabel="Adding">
              <UnitFields prefix="new-unit" />
            </ActionForm>
          </details>
        ) : null}
        {u.units.length === 0 ? (
          <p className="empty" style={{ marginTop: 16 }}>
            No units yet. Import them from your sales sheet, or add them one by one.
          </p>
        ) : null}
        {u.units.length > 0 ? (
          <form method="get" className="filters">
            <div className="field">
              <label htmlFor="units-q">Unit or buyer</label>
              <input id="units-q" name="q" defaultValue={search} placeholder="A-0101 or a name" />
            </div>
            {towers.length > 1 ? (
              <div className="field">
                <label htmlFor="units-tower">Tower</label>
                <select id="units-tower" name="tower" defaultValue={tower}>
                  <option value="">All towers</option>
                  {towers.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
            <div className="field">
              <label htmlFor="units-status">Which</label>
              <select id="units-status" name="status" defaultValue={status}>
                <option value="">All units</option>
                <option value="sold">Sold</option>
                <option value="unsold">Not sold</option>
                <option value="landowner">Landowner&apos;s</option>
                <option value="below">Priced below guidance</option>
              </select>
            </div>
            <button type="submit" className="button button-secondary">
              Show
            </button>
            {filtered ? (
              <Link href={`/projects/${id}/units`} className="link-action">
                Clear
              </Link>
            ) : null}
          </form>
        ) : null}
        {filtered ? <p className="small muted">{`${shown.length} of ${u.units.length} units`}</p> : null}
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
            {visible.map((unit) => (
              <tr key={unit.id}>
                <td>
                  <Link href={`/units/${unit.id}`}>{unit.label}</Link>
                </td>
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
        {!all && shown.length > PAGE ? (
          <p className="small" style={{ marginTop: 12 }}>
            <Link
              href={`/projects/${id}/units?${new URLSearchParams({ ...(tower && { tower }), ...(status && { status }), ...(search && { q: search }), all: "1" })}`}
              className="link-action"
            >
              {`Show all ${shown.length} units`}
            </Link>
          </p>
        ) : null}
      </section>
    </>
  );
}

function LandownerFields({
  prefix,
  owner,
}: {
  prefix: string;
  owner?: { name: string; share_type: string; share_pct: string; refundable_deposit: string; pan: string | null };
}) {
  return (
    <div className="field-grid">
      <div className="field">
        <label htmlFor={`${prefix}-name`}>Name</label>
        <input id={`${prefix}-name`} name="name" defaultValue={owner?.name ?? ""} required={!owner} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-type`}>Share of</label>
        <select id={`${prefix}-type`} name="share_type" defaultValue={owner?.share_type ?? "area"}>
          <option value="area">The built area</option>
          <option value="revenue">Revenue</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-pct`}>Share (per cent)</label>
        <input id={`${prefix}-pct`} name="share_pct" inputMode="decimal" defaultValue={owner?.share_pct ?? ""} required={!owner} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-deposit`}>Refundable deposit (rupees)</label>
        <input id={`${prefix}-deposit`} name="refundable_deposit" defaultValue={owner?.refundable_deposit ?? ""} />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-pan`}>PAN</label>
        <input id={`${prefix}-pan`} name="pan" defaultValue={owner?.pan ?? ""} placeholder="ABCDE1234F" />
      </div>
    </div>
  );
}
