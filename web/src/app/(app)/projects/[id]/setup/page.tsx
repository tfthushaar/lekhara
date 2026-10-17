import Link from "next/link";
import { Suspense } from "react";

import { recordProgress, updateProject } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { type Setup, api } from "@/lib/api";

export default function SetupPage({ params }: PageProps<"/projects/[id]/setup">) {
  return (
    <Suspense fallback={<p className="loading">Checking what is in</p>}>
      <SetupView params={params} />
    </Suspense>
  );
}

const STATUS: Record<Setup["items"][number]["status"], { label: string; className: string }> = {
  done: { label: "In", className: "tag tag-done" },
  partial: { label: "Partly in", className: "tag tag-soon" },
  stale: { label: "Out of date", className: "tag tag-soon" },
  missing: { label: "Not yet", className: "tag tag-fail" },
};

async function SetupView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = await api.setup(id);

  return (
    <>
      <p className="status-line">
        {s.summary.done === s.summary.total
          ? "Everything Lekhara needs for this project is in."
          : `${s.summary.done} of ${s.summary.total} in. Each one left switches on more of Lekhara.`}
      </p>
      <ul className="rows">
        {s.items.map((item) => (
          <li key={item.key} className="row">
            <div>
              <span className={STATUS[item.status].className}>{STATUS[item.status].label}</span>
            </div>
            <div>
              <p className="row-title">{item.title}</p>
              <p className="row-detail">{item.detail}</p>
              <p className="row-meta">{`Switches on: ${item.unlocks}`}</p>
            </div>
            <div className="row-side">
              {item.status !== "done" || item.href.includes("#") ? (
                <Link href={item.href} className="link-action">
                  {item.action}
                </Link>
              ) : null}
            </div>
          </li>
        ))}
      </ul>

      {s.can_edit ? (
        <>
          <section className="section" id="progress">
            <div className="section-head">
              <h2>Certified progress</h2>
              <p>From the architect&apos;s or engineer&apos;s latest certificate of completion</p>
            </div>
            <div style={{ maxWidth: 880, marginTop: 12 }}>
              <ActionForm action={recordProgress.bind(null, id)} label="Record the certificate" pendingLabel="Saving">
                <div className="field-grid">
                  <div className="field">
                    <label htmlFor="progress-date">Certificate dated</label>
                    <input id="progress-date" name="as_of" type="date" required />
                  </div>
                  <div className="field">
                    <label htmlFor="progress-pct">Complete (per cent)</label>
                    <input id="progress-pct" name="completion_pct" inputMode="decimal" required />
                  </div>
                  <div className="field">
                    <label htmlFor="progress-by">Certified by</label>
                    <input id="progress-by" name="certified_by" placeholder="The architect's firm" />
                  </div>
                </div>
              </ActionForm>
            </div>
          </section>

          <section className="section" id="details">
            <div className="section-head">
              <h2>Project details</h2>
              <p>As on the K-RERA registration; the occupancy certificate and the handover to the association when they come</p>
            </div>
            <div style={{ marginTop: 12 }}>
              <ActionForm action={updateProject.bind(null, id)} label="Save the details" pendingLabel="Saving">
                <DetailFields d={s.details} />
              </ActionForm>
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}

function DetailFields({ d }: { d: Setup["details"] }) {
  const text = (name: keyof Setup["details"], label: string, required = false) => (
    <div className="field">
      <label htmlFor={`p-${name}`}>{label}</label>
      <input id={`p-${name}`} name={name} defaultValue={d[name] ?? ""} required={required} />
    </div>
  );
  const date = (name: keyof Setup["details"], label: string) => (
    <div className="field">
      <label htmlFor={`p-${name}`}>{label}</label>
      <input id={`p-${name}`} name={name} type="date" defaultValue={d[name] ?? ""} />
    </div>
  );
  return (
    <>
      <div className="field-grid">
        {text("name", "Project name", true)}
        {text("krera_registration", "K-RERA registration number", true)}
        {date("registered_on", "Registered on")}
        {date("possession_due_on", "Possession promised by")}
        {text("locality", "Locality")}
        {text("city", "City")}
        {text("spv_name", "Promoter as registered")}
        <div className="field">
          <label htmlFor="p-land">Land</label>
          <select id="p-land" name="land_structure" defaultValue={d.land_structure}>
            <option value="own">Own land</option>
            <option value="jda_area_share">Joint development, area share</option>
            <option value="jda_revenue_share">Joint development, revenue share</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="p-gst">GST on sales</label>
          <select id="p-gst" name="gst_regime" defaultValue={d.gst_regime}>
            <option value="residential_5pc">Residential, 5% without input credit</option>
            <option value="affordable_1pc">Affordable housing, 1% without input credit</option>
            <option value="commercial_12pc">Commercial, 12% with input credit</option>
            <option value="rrep_mixed">Residential with commercial space</option>
          </select>
        </div>
        {text("escrow_bank", "Bank holding the RERA account")}
        {text("statutory_auditor_firm", "Auditor for the annual K-RERA audit")}
        {text("development_rights_value", "Value of development rights (rupees, for a JDA)")}
        {text("cess_paid", "Labour cess paid so far (rupees)")}
      </div>
      <p className="small muted" style={{ margin: "4px 0 12px" }}>Occupancy certificate and handover</p>
      <div className="field-grid">
        <div className="field">
          <label htmlFor="p-oc">Occupancy certificate</label>
          <select id="p-oc" name="oc_status" defaultValue={d.oc_status}>
            <option value="none">Not applied for</option>
            <option value="applied">Applied for</option>
            <option value="partial">Partial OC received</option>
            <option value="received">Received</option>
          </select>
        </div>
        {date("oc_received_on", "OC received on")}
        {text("oc_reference", "OC number")}
        {date("association_formed_on", "Association formed on")}
        {date("common_areas_conveyed_on", "Common areas conveyed on")}
      </div>
    </>
  );
}
