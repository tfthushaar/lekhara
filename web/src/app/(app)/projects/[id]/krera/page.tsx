import Link from "next/link";
import { Suspense } from "react";

import { deleteFiling, recordEarlierFilings, recordFiling, updateFiling } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { History } from "@/components/history";
import { type FilingPeriod, api } from "@/lib/api";
import { day, plural } from "@/lib/format";

export default function KreraPage({ params }: PageProps<"/projects/[id]/krera">) {
  return (
    <Suspense fallback={<p className="loading">Loading K-RERA filings</p>}>
      <KreraView params={params} />
    </Suspense>
  );
}

const STATE = {
  filed: { text: "Filed", tag: "tag tag-done" },
  late: { text: "Late", tag: "tag tag-overdue" },
  due: { text: "Due", tag: "tag tag-soon" },
  open: { text: "Current", tag: "tag tag-upcoming" },
  unrecorded: { text: "Not recorded", tag: "tag tag-upcoming" },
};

const SHOWN = 4;

async function KreraView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const k = await api.krera(id);
  const late = k.quarters.filter((q) => q.state === "late").length;

  return (
    <>
      {k.unrecorded > 0 ? (
        <div className="notice" style={{ marginBottom: 24 }}>
          <p>
            {`Were the ${k.unrecorded} filings due before ${day(k.known_from)} all made on time? Tell us once, or record each one below.`}
          </p>
          {k.can_edit ? (
            <div style={{ marginTop: 12 }}>
              <ActionForm action={recordEarlierFilings.bind(null, id)} label="Yes, all on time" pendingLabel="Recording" secondary />
            </div>
          ) : null}
        </div>
      ) : null}
      <section className="section">
        <div className="section-head">
          <h2>Quarterly reports</h2>
          <p>
            {`Due ${k.qpr_due_days} days after each quarter ends`}
            {late ? `. ${plural(late, "quarter")} not recorded as filed` : ""}
          </p>
        </div>
        <Periods periods={k.quarters} kind="qpr" canEdit={k.can_edit} projectId={id} label="Quarter" />
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Annual audit</h2>
          <p>{`Your CA audits the project's accounts within ${k.audit_months} months of each year end`}</p>
        </div>
        {k.audits.length === 0 ? (
          <p className="empty">No financial year has ended since the project was registered.</p>
        ) : (
          <Periods periods={k.audits} kind="annual_audit" canEdit={k.can_edit} projectId={id} label="Year" />
        )}
      </section>

      <section className="section">
        <p className="chips" style={{ alignItems: "center" }}>
          {k.can_edit ? (
            <Link href={`/projects/${id}/import`} className="link-action">
              Add a sheet of filings
            </Link>
          ) : null}
          <a href={`/download/projects/${id}/exports/filings.xlsx`} className="link-action">
            Download as Excel
          </a>
        </p>
      </section>
    </>
  );
}

function Periods({
  periods,
  kind,
  canEdit,
  projectId,
  label,
}: {
  periods: FilingPeriod[];
  kind: "qpr" | "annual_audit";
  canEdit: boolean;
  projectId: string;
  label: string;
}) {
  const urgent = periods.filter((q) => q.state === "late" || q.state === "due");
  const others = periods.filter((q) => !urgent.includes(q));
  const first = [...urgent, ...others.slice(0, Math.max(SHOWN - urgent.length, 1))];
  const rest = periods.filter((q) => !first.includes(q));
  const row = (q: FilingPeriod) => <PeriodRow key={q.period_end} q={q} kind={kind} canEdit={canEdit} projectId={projectId} label={label} />;
  return (
    <>
      <ul className="rows">{first.map(row)}</ul>
      {rest.length ? (
        <details className="disclosure">
          <summary>{`${rest.length} earlier`}</summary>
          <ul className="rows">{rest.map(row)}</ul>
        </details>
      ) : null}
    </>
  );
}

function PeriodRow({
  q,
  kind,
  canEdit,
  projectId,
  label,
}: {
  q: FilingPeriod;
  kind: string;
  canEdit: boolean;
  projectId: string;
  label: string;
}) {
  const s = STATE[q.state];
  const f = q.filing;
  return (
    <li className="row">
      <div>
        <span className={s.tag}>{s.text}</span>
      </div>
      <div>
        <p className="row-title">{`${label} ending ${day(q.period_end)}`}</p>
        <p className="row-detail">
          {f
            ? `Filed ${day(f.filed_on)}${f.reference ? `, acknowledgement ${f.reference}` : ""}`
            : q.state === "open"
              ? `From ${day(q.period_start)}. Due ${day(q.due_on)}.`
              : `Due ${day(q.due_on)}`}
        </p>
        {q.state !== "open" ? (
          <p className="row-meta">
            <a href={`/download/projects/${projectId}/packs/${kind === "qpr" ? "qpr" : "audit"}/${q.period_end}.pdf`} className="link-action">
              {kind === "qpr" ? "Figures for the portal (PDF)" : "Pack for your CA (PDF)"}
            </a>
            {"  ·  "}
            <a href={`/download/projects/${projectId}/packs/${kind === "qpr" ? "qpr" : "audit"}/${q.period_end}.xlsx`} className="link-action">
              Excel
            </a>
          </p>
        ) : null}
        {canEdit && !f && q.state !== "open" ? (
          <details className="disclosure">
            <summary>I have filed it</summary>
            <ActionForm action={recordFiling.bind(null, projectId)} label="Save" pendingLabel="Saving">
              <input type="hidden" name="kind" value={kind} />
              <input type="hidden" name="period_end" value={q.period_end} />
              <FilingFields prefix={`f-${kind}-${q.period_end}`} />
            </ActionForm>
          </details>
        ) : null}
        {canEdit && f ? (
          <details className="disclosure">
            <summary>Change</summary>
            <ActionForm action={updateFiling.bind(null, f.id)} label="Save" pendingLabel="Saving" secondary>
              <FilingFields prefix={`f-${f.id}`} filedOn={f.filed_on} reference={f.reference} />
            </ActionForm>
            <ActionForm action={deleteFiling.bind(null, f.id)} label="Not filed after all" pendingLabel="Removing" secondary />
          </details>
        ) : null}
        {f ? <History entries={f.history} /> : null}
      </div>
      <div />
    </li>
  );
}

function FilingFields({ prefix, filedOn, reference }: { prefix: string; filedOn?: string; reference?: string | null }) {
  return (
    <div className="field-grid">
      <div className="field">
        <label htmlFor={`${prefix}-on`}>Filed on</label>
        <input id={`${prefix}-on`} name="filed_on" type="date" defaultValue={filedOn ?? ""} required />
      </div>
      <div className="field">
        <label htmlFor={`${prefix}-ref`}>Acknowledgement number, if you have it</label>
        <input id={`${prefix}-ref`} name="reference" defaultValue={reference ?? ""} />
      </div>
    </div>
  );
}
