import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { bookUnit, holdUnit, logActivity, planVisit, recordVisit, releaseHold, reopenLead, updateLead } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type LeadDetail, api } from "@/lib/api";
import { day, inr, moment } from "@/lib/format";

export const metadata: Metadata = { title: "Lead" };

export default function LeadPage({ params }: PageProps<"/leads/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the lead</p>}>
      <LeadView params={params} />
    </Suspense>
  );
}

function PlanVisit({ l }: { l: LeadDetail }) {
  return (
    <ActionForm action={planVisit.bind(null, l.id)} label="Plan the visit" pendingLabel="Saving">
      <div className="field-grid">
        <div className="field">
          <label htmlFor="visit-on">Which day?</label>
          <input id="visit-on" name="on" type="date" required />
        </div>
        <div className="field">
          <label htmlFor="visit-time">What time?</label>
          <input id="visit-time" name="time" placeholder="11:00" />
        </div>
      </div>
    </ActionForm>
  );
}

function DidTheyCome({ l }: { l: LeadDetail }) {
  const v = l.planned_visit;
  if (!v) return null;
  return (
    <section className="section">
      <div className="section-head">
        <h2>{`Site visit on ${day(v.on)}${v.time ? `, ${v.time}` : ""}`}</h2>
      </div>
      <ActionForm action={recordVisit.bind(null, v.id, "done")} label="They came" pendingLabel="Saving">
        <div className="field field-wide">
          <label htmlFor="visit-feedback">What did they say?</label>
          <textarea id="visit-feedback" name="feedback" rows={2} />
        </div>
      </ActionForm>
      <ActionForm action={recordVisit.bind(null, v.id, "no_show")} label="They did not come" pendingLabel="Saving" secondary />
    </section>
  );
}

function HoldForm({ l }: { l: LeadDetail }) {
  return (
    <ActionForm action={holdUnit.bind(null, l.id)} label="Hold it" pendingLabel="Holding" secondary>
      <div className="field">
        <label htmlFor="hold-unit">Which unit?</label>
        <select id="hold-unit" name="unit_id" required defaultValue="">
          <option value="" disabled>
            Choose a unit
          </option>
          {l.units
            .filter((u) => !u.held_by_other && !u.held_by_this_lead)
            .map((u) => (
              <option key={u.id} value={u.id}>
                {`${u.label}, ${u.carpet_area_sqft} sq ft${u.price ? `, ${inr(u.price)}` : ""}`}
              </option>
            ))}
        </select>
      </div>
    </ActionForm>
  );
}

function BookingForm({ l }: { l: LeadDetail }) {
  const held = l.units.find((u) => u.held_by_this_lead);
  return (
    <ActionForm action={bookUnit.bind(null, l.id)} label="Book the unit" pendingLabel="Booking">
      <div className="field-grid">
        <div className="field">
          <label htmlFor="book-unit">Which unit?</label>
          <select id="book-unit" name="unit_id" defaultValue={held?.id ?? ""} required>
            <option value="" disabled>
              Choose a unit
            </option>
            {l.units
              .filter((u) => !u.held_by_other)
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {`${u.label}, ${u.carpet_area_sqft} sq ft${u.price ? `, ${inr(u.price)}` : ""}`}
                </option>
              ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="book-amount">Booking amount received, in rupees</label>
          <input id="book-amount" name="booking_amount" required inputMode="decimal" />
        </div>
        <div className="field">
          <label htmlFor="book-pan">Buyer&apos;s PAN</label>
          <input id="book-pan" name="buyer_pan" placeholder="ABCDE1234F" />
        </div>
      </div>
      <details className="disclosure">
        <summary>More details</summary>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="book-on">Booked on (today if blank)</label>
            <input id="book-on" name="booked_on" type="date" />
          </div>
          <div className="field">
            <label htmlFor="book-ref">Cheque or UTR number</label>
            <input id="book-ref" name="reference" />
          </div>
          <div className="field">
            <label htmlFor="book-discount">Discount a sq ft</label>
            <input id="book-discount" name="discount_per_sqft" inputMode="decimal" />
          </div>
          <div className="field">
            <label htmlFor="book-aadhaar">Last four digits of Aadhaar</label>
            <input id="book-aadhaar" name="aadhaar_last4" inputMode="numeric" maxLength={4} />
          </div>
          {l.partners.length > 0 ? (
            <div className="field">
              <label htmlFor="book-partner">Channel partner</label>
              <select id="book-partner" name="partner_id" defaultValue={l.partner?.id ?? ""}>
                <option value="">None</option>
                {l.partners.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </div>
        {l.plc.length > 0 ? (
          <div className="field">
            <span>Location charges that apply</span>
            {l.plc.map((name) => (
              <label key={name} className="field-check">
                <input type="checkbox" name="plc" value={name} /> {name}
              </label>
            ))}
          </div>
        ) : null}
        <div className="field field-wide">
          <label htmlFor="book-address">Buyer&apos;s address</label>
          <textarea id="book-address" name="buyer_address" rows={2} />
        </div>
      </details>
    </ActionForm>
  );
}

function NotInterested({ l }: { l: LeadDetail }) {
  return (
    <ActionForm action={updateLead.bind(null, l.id)} label="Mark as not interested" pendingLabel="Saving" secondary>
      <input type="hidden" name="stage" value="lost" />
      <div className="field">
        <label htmlFor="lost-reason">Why?</label>
        <select id="lost-reason" name="lost_reason" defaultValue="Bought elsewhere">
          <option>Bought elsewhere</option>
          <option>Budget too low</option>
          <option>Location does not suit</option>
          <option>Cannot reach them</option>
          <option>Put off buying</option>
        </select>
      </div>
    </ActionForm>
  );
}

function ChangeDetails({ l }: { l: LeadDetail }) {
  return (
    <ActionForm action={updateLead.bind(null, l.id)} label="Save" pendingLabel="Saving" secondary>
      <div className="field-grid">
        <div className="field">
          <label htmlFor="lead-interest">Looking for</label>
          <input id="lead-interest" name="interest" defaultValue={l.interest ?? ""} />
        </div>
        <div className="field">
          <label htmlFor="lead-budget">Budget</label>
          <input id="lead-budget" name="budget" defaultValue={l.budget ? String(Number(l.budget)) : ""} />
        </div>
        <div className="field">
          <label htmlFor="lead-owner">Who follows up</label>
          <select id="lead-owner" name="owner_user_id" defaultValue={l.team.find((t) => t.name === l.owner)?.id ?? ""}>
            <option value="">Nobody yet</option>
            {l.team.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="lead-project">Project</label>
          <select id="lead-project" name="project_id" defaultValue={l.project?.id ?? ""}>
            {l.project ? null : <option value="">Not chosen</option>}
            {l.projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>
    </ActionForm>
  );
}

/** The one thing to do next, from where the lead has got to. */
function NextStep({ l }: { l: LeadDetail }) {
  if (l.stage === "visit_planned" && l.planned_visit) return <DidTheyCome l={l} />;
  if (l.stage === "visited" || l.stage === "negotiating") {
    return (
      <section className="section">
        <div className="section-head">
          <h2>Ready to book?</h2>
        </div>
        {l.project && l.has_prices ? (
          <BookingForm l={l} />
        ) : (
          <p className="notice" style={{ marginTop: 12 }}>
            {"Add the project's prices first. "}
            {l.project ? <Link href={`/projects/${l.project.id}/sales`}>Open prices</Link> : null}
          </p>
        )}
      </section>
    );
  }
  return (
    <section className="section">
      <div className="section-head">
        <h2>Invite them to see the site</h2>
      </div>
      <PlanVisit l={l} />
    </section>
  );
}

async function LeadView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const l = await api.lead(id);
  const open = !["booked", "lost"].includes(l.stage);
  const bookable = Boolean(l.project && l.has_prices);
  const showingBooking = l.stage === "visited" || l.stage === "negotiating";

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            {l.project ? <Link href={`/projects/${l.project.id}/sales`}>{`${l.project.name}, leads`}</Link> : <Link href="/projects">Projects</Link>}
          </p>
          <h1>{l.name}</h1>
          <p>
            {[l.interest, l.budget ? inr(l.budget) : null, `from ${l.source_label}`, l.partner ? `through ${l.partner.name}` : null].filter(Boolean).join(", ")}
          </p>
          {l.phone_key ? (
            <p className="chips">
              <a href={`tel:+91${l.phone_key}`} className="button">
                {`Call ${l.phone}`}
              </a>
              <a href={`https://wa.me/91${l.phone_key}`} target="_blank" rel="noreferrer" className="button button-secondary">
                WhatsApp
              </a>
            </p>
          ) : l.email ? (
            <p>{l.email}</p>
          ) : null}
        </div>
        <div className="head-side">
          <p className="stat-label">{l.stage === "lost" && l.lost_reason ? `Not interested: ${l.lost_reason}` : l.stage_label}</p>
          {l.next_follow_up_on && open ? (
            <p className="head-side-value">
              {l.follow_up_late ? <span className="tag tag-overdue">{`Call was due ${day(l.next_follow_up_on)}`}</span> : `Call on ${day(l.next_follow_up_on)}`}
            </p>
          ) : null}
        </div>
      </div>

      {l.booking ? (
        <section>
          <div className="section-head">
            <h2>{`Booked unit ${l.booking.unit}`}</h2>
            <p>{`${day(l.booking.booked_on)}, ${inr(l.booking.agreement_value)}`}</p>
          </div>
          <p className="chips">
            <a href={`/download/bookings/${l.booking.id}/allotment.pdf`} className="button">
              Print the allotment letter
            </a>
            <Link href={`/units/${l.booking.unit_id}`} className="button button-secondary">
              Open the unit
            </Link>
          </p>
        </section>
      ) : null}

      {l.stage === "lost" && l.can_edit ? (
        <section>
          <ActionForm action={reopenLead.bind(null, l.id)} label="Bring this lead back" pendingLabel="Saving" secondary />
        </section>
      ) : null}

      {l.can_edit && open ? (
        <>
          <section>
            <div className="section-head">
              <h2>What happened?</h2>
            </div>
            <ActionForm action={logActivity.bind(null, l.id)} label="Save" pendingLabel="Saving">
              <input type="hidden" name="kind" value="call" />
              <div className="field field-wide">
                <label htmlFor="act-detail">What did they say?</label>
                <textarea id="act-detail" name="detail" rows={2} required />
              </div>
              <div className="field">
                <label htmlFor="act-follow">Call them again on</label>
                <input id="act-follow" name="next_follow_up_on" type="date" defaultValue={l.call_again_on} />
              </div>
            </ActionForm>
          </section>

          <NextStep l={l} />
        </>
      ) : null}

      {open && l.units.some((u) => u.held_by_this_lead) ? (
        <section className="section">
          {l.units
            .filter((u) => u.held_by_this_lead)
            .map((u) => (
              <div key={u.id} className="row" style={{ gridTemplateColumns: "1fr auto" }}>
                <div>
                  <p className="row-title">{`Unit ${u.label} is held for them`}</p>
                  <p className="row-detail">{`Until ${moment(u.held_until)}`}</p>
                </div>
                <div className="row-side">
                  {l.project ? (
                    <Link href={`/projects/${l.project.id}/sales/cost-sheet/${u.id}`} className="button button-secondary">
                      Cost sheet
                    </Link>
                  ) : null}
                  {l.can_edit && u.hold_id ? (
                    <ActionForm action={releaseHold.bind(null, u.hold_id)} label="Release it" pendingLabel="Releasing" secondary />
                  ) : null}
                </div>
              </div>
            ))}
        </section>
      ) : null}

      {l.can_edit && l.stage !== "booked" ? (
        <section className="section">
          <details className="disclosure">
            <summary>Something else</summary>
            {open && bookable ? (
              <details className="disclosure">
                <summary>Hold a unit for 48 hours</summary>
                <HoldForm l={l} />
              </details>
            ) : null}
            {open && bookable && !showingBooking ? (
              <details className="disclosure">
                <summary>Book a unit</summary>
                <BookingForm l={l} />
              </details>
            ) : null}
            {open && l.stage !== "new" && l.stage !== "contacted" && !l.planned_visit ? (
              <details className="disclosure">
                <summary>Plan another site visit</summary>
                <PlanVisit l={l} />
              </details>
            ) : null}
            {open ? (
              <details className="disclosure">
                <summary>They are not interested</summary>
                <NotInterested l={l} />
              </details>
            ) : null}
            <details className="disclosure">
              <summary>Change their details</summary>
              <ChangeDetails l={l} />
            </details>
          </details>
        </section>
      ) : null}

      <section className="section">
        <div className="section-head">
          <h2>What has happened so far</h2>
        </div>
        <ul className="rows">
          {l.activities.map((a, i) => (
            <li key={`${a.at}-${i}`} className="row" style={{ gridTemplateColumns: "1fr" }}>
              <div>
                <p>{a.detail}</p>
                <p className="row-meta">{`${moment(a.at)}${a.by ? `, ${a.by}` : ""}`}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
