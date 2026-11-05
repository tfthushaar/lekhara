import Link from "next/link";
import { Suspense } from "react";

import { addLead, savePriceList } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type SalesPage, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

export default function SalesTab({ params, searchParams }: PageProps<"/projects/[id]/sales">) {
  return (
    <Suspense fallback={<p className="loading">Loading leads</p>}>
      <SalesView params={params} searchParams={searchParams} />
    </Suspense>
  );
}

function month(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-IN", { month: "short", year: "numeric", timeZone: "UTC" });
}

function rate(part: number, whole: number): string {
  return whole ? `${Math.round((part / whole) * 100)}%` : "None yet";
}

function LeadForm({ s }: { s: SalesPage }) {
  return (
    <>
      <div className="field-grid">
        <div className="field">
          <label htmlFor="lead-name">Name</label>
          <input id="lead-name" name="name" required />
        </div>
        <div className="field">
          <label htmlFor="lead-phone">Phone</label>
          <input id="lead-phone" name="phone" inputMode="tel" placeholder="98450 12345" />
        </div>
        <div className="field">
          <label htmlFor="lead-source">Where did they hear of you?</label>
          <select id="lead-source" name="source" defaultValue="walk_in">
            {s.sources.map((x) => (
              <option key={x.value} value={x.value}>
                {x.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <details className="disclosure">
        <summary>More details</summary>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="lead-interest">Looking for</label>
            <input id="lead-interest" name="interest" placeholder="3 BHK, high floor" />
          </div>
          <div className="field">
            <label htmlFor="lead-budget">Budget</label>
            <input id="lead-budget" name="budget" placeholder="95 lakh or 1.2 crore" />
          </div>
          <div className="field">
            <label htmlFor="lead-email">Email</label>
            <input id="lead-email" name="email" type="email" />
          </div>
          {s.partners.length > 0 ? (
            <div className="field">
              <label htmlFor="lead-partner">Brought by a channel partner</label>
              <select id="lead-partner" name="partner_id" defaultValue="">
                <option value="">No</option>
                {s.partners.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.firm ? `${p.name}, ${p.firm}` : p.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </div>
      </details>
    </>
  );
}

function PriceFields({ s }: { s: SalesPage }) {
  const p = s.price_list;
  const plc = p ? Object.entries(p.plc).map(([k, v]) => `${k}: ${Number(v)}`).join("\n") : "";
  const field = (name: string, label: string, value: string | number | undefined, hint?: string) => (
    <div className="field">
      <label htmlFor={`price-${name}`}>{label}</label>
      <input id={`price-${name}`} name={name} defaultValue={value === undefined ? "" : String(Number(value))} placeholder={hint} />
    </div>
  );
  return (
    <>
      <div className="field-grid">
        {field("base_rate", "Rate a sq ft", p?.base_rate, "10400")}
        {field("car_park", "Car park", p?.car_park)}
        {field("amenities", "Amenities and clubhouse", p?.amenities)}
      </div>
      <details className="disclosure">
        <summary>More charges</summary>
        <div className="field-grid">
          {field("floor_rise", "Floor rise a sq ft, each floor", p?.floor_rise, "35")}
          {field("floor_rise_from", "Floor rise starts at floor", p?.floor_rise_from ?? 2)}
          {field("other_charges", "BESCOM, BWSSB and legal charges", p?.other_charges)}
          {field("corpus_per_sqft", "Corpus fund a sq ft", p?.corpus_per_sqft)}
          {field("maintenance_per_sqft_month", "Maintenance a sq ft a month", p?.maintenance_per_sqft_month)}
          {field("maintenance_months", "Months of maintenance taken in advance", p?.maintenance_months ?? 12)}
        </div>
        <div className="field field-wide">
          <label htmlFor="price-plc">Location charges a sq ft, one to a line</label>
          <textarea id="price-plc" name="plc" rows={3} defaultValue={plc} placeholder={"Corner: 150\nPark facing: 100"} />
        </div>
      </details>
    </>
  );
}

async function SalesView({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const stage = typeof query.stage === "string" ? query.stage : undefined;
  const s = await api.sales(id, stage);
  const open = s.stages.filter((x) => !["booked", "lost"].includes(x.value)).reduce((n, x) => n + x.count, 0);
  const showing = s.stages.find((x) => x.value === s.stage);

  return (
    <>
      {s.can_edit ? (
        <section>
          <div className="section-head">
            <h2>Someone new asked?</h2>
          </div>
          <ActionForm action={addLead.bind(null, id)} label="Add them" pendingLabel="Adding">
            <LeadForm s={s} />
          </ActionForm>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>{`Call today (${s.call_today.length})`}</h2>
        </div>
        {s.call_today.length === 0 ? (
          <p className="empty">{s.conversion.leads === 0 ? "No leads yet. Add the first one above." : "Nobody to call today."}</p>
        ) : (
          <ul className="rows">
            {s.call_today.map((l) => (
              <li key={l.id} className="row" style={{ gridTemplateColumns: "1fr auto" }}>
                <div>
                  <p className="row-title">
                    <Link href={`/leads/${l.id}`}>{l.name}</Link>
                    {l.follow_up_late ? <span className="tag tag-overdue" style={{ marginLeft: 8 }}>Late</span> : null}
                  </p>
                  <p className="row-detail">{[l.stage_label, l.interest].filter(Boolean).join(", ")}</p>
                </div>
                <div className="row-side">
                  {l.phone_key ? (
                    <a href={`tel:+91${l.phone_key}`} className="button button-secondary">
                      {l.phone}
                    </a>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {s.visits.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Site visits coming up</h2>
          </div>
          <ul className="rows">
            {s.visits.map((v) => (
              <li key={v.id} className="row" style={{ gridTemplateColumns: "1fr" }}>
                <div>
                  <p className="row-title">
                    <Link href={`/leads/${v.lead_id}`}>{v.lead}</Link>
                  </p>
                  <p className="row-detail">{`${day(v.on)}${v.time ? `, ${v.time}` : ""}`}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="section">
        <details className="disclosure" open={Boolean(s.stage)}>
          <summary>{`All leads (${s.conversion.leads})`}</summary>
          <p className="chips">
            <Link href={`/projects/${id}/sales`} className={`chip${s.stage ? "" : " chip-on"}`}>
              {`Open, ${open}`}
            </Link>
            {s.stages.map((x) => (
              <Link key={x.value} href={`/projects/${id}/sales?stage=${x.value}`} className={`chip${s.stage === x.value ? " chip-on" : ""}`}>
                {`${x.label}, ${x.count}`}
              </Link>
            ))}
          </p>
          {s.leads.length === 0 ? (
            <p className="empty">{showing ? `Nobody at ${showing.label.toLowerCase()}.` : "No open leads."}</p>
          ) : (
            <div className="table-scroll">
              <table className="table" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Where they are</th>
                    <th>Looking for</th>
                    <th>Call on</th>
                  </tr>
                </thead>
                <tbody>
                  {s.leads.map((l) => (
                    <tr key={l.id}>
                      <td>
                        <Link href={`/leads/${l.id}`}>{l.name}</Link>
                      </td>
                      <td>{l.stage_label}</td>
                      <td>{l.interest ?? ""}</td>
                      <td className="nowrap">{l.next_follow_up_on ? day(l.next_follow_up_on) : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {s.can_edit ? (
            <p className="small muted" style={{ marginTop: 12 }}>
              {"Have leads in a 99acres, MagicBricks or Facebook file? "}
              <Link href={`/projects/${id}/import`}>Add the file</Link>
            </p>
          ) : null}
        </details>

        <details className="disclosure">
          <summary>{`Unsold units (${s.inventory.units.length}), ${inr(s.inventory.unsold_value)}`}</summary>
          {s.inventory.units.length === 0 ? (
            <p className="empty">Every unit is sold.</p>
          ) : (
            <div className="table-scroll">
              <table className="table" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Unit</th>
                    <th className="right">Carpet area</th>
                    <th className="right">List price</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {s.inventory.units.map((u) => (
                    <tr key={u.id}>
                      <td>
                        {u.label}
                        {u.held_for ? <span className="small muted">{` held for ${u.held_for}`}</span> : null}
                      </td>
                      <td className="right num">{`${u.carpet_area_sqft} sq ft`}</td>
                      <td className="right num">{inr(u.list_price)}</td>
                      <td>
                        {s.price_list ? (
                          <Link href={`/projects/${id}/sales/cost-sheet/${u.id}`} className="link-action">
                            Cost sheet
                          </Link>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </details>

        <details className="disclosure">
          <summary>{`Bookings (${s.bookings.length})`}</summary>
          {s.bookings.length === 0 ? (
            <p className="empty">No bookings yet. Book a unit from the lead&apos;s page.</p>
          ) : (
            <div className="table-scroll">
              <table className="table" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Unit</th>
                    <th>Buyer</th>
                    <th>Booked</th>
                    <th className="right">Price</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {s.bookings.map((b) => (
                    <tr key={b.id}>
                      <td>
                        <Link href={`/units/${b.unit_id}`}>{b.unit}</Link>
                      </td>
                      <td>{b.buyer}</td>
                      <td className="nowrap">{day(b.booked_on)}</td>
                      <td className="right num">{inr(b.agreement_value)}</td>
                      <td>
                        <a href={`/download/bookings/${b.id}/allotment.pdf`} className="link-action">
                          Allotment letter
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </details>

        <details className="disclosure">
          <summary>How sales are going</summary>
          <div className="stats">
            <div className="stat">
              <p className="stat-label">Visits that booked</p>
              <p className="stat-value">{rate(s.conversion.booked, s.conversion.visited)}</p>
              <p className="stat-note">{`${s.conversion.booked} of ${s.conversion.visited} who visited`}</p>
            </div>
            <div className="stat">
              <p className="stat-label">Open leads</p>
              <p className="stat-value">{open}</p>
              <p className="stat-note">{s.follow_ups_late ? `${plural(s.follow_ups_late, "call")} late` : "No calls late"}</p>
            </div>
          </div>
          <div className="grid-2">
            <div className="table-scroll">
              <table className="table" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Where leads come from</th>
                    <th className="right">Leads</th>
                    <th className="right">Booked</th>
                  </tr>
                </thead>
                <tbody>
                  {s.by_source.map((r) => (
                    <tr key={r.source}>
                      <td>{r.label}</td>
                      <td className="right num">{r.leads}</td>
                      <td className="right num">{r.booked}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-scroll">
              <table className="table" style={{ marginTop: 12 }}>
                <thead>
                  <tr>
                    <th>Bookings by month</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {s.bookings_by_month.map((m) => (
                    <tr key={m.month}>
                      <td>{month(m.month)}</td>
                      <td className="right num">{m.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </details>

        <details className="disclosure" open={!s.price_list && s.can_edit}>
          <summary>{s.price_list ? `Prices (${inr(s.price_list.base_rate)} a sq ft)` : "Prices, needed for cost sheets and bookings"}</summary>
          {s.can_edit ? (
            <ActionForm action={savePriceList.bind(null, id)} label="Save the prices" pendingLabel="Saving">
              <PriceFields s={s} />
            </ActionForm>
          ) : null}
        </details>

        <p style={{ marginTop: 16 }}>
          <Link href="/partners">Channel partners and what you owe them</Link>
        </p>
      </section>
    </>
  );
}
