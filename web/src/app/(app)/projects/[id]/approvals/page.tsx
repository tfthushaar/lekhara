import Link from "next/link";
import { Suspense } from "react";

import { addStandardApprovals, createApproval, deleteApproval, updateApproval } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { ApprovalFields } from "@/components/approval-fields";
import { History } from "@/components/history";
import { type ApprovalRow, type ApprovalStatus, api } from "@/lib/api";
import { day, plural } from "@/lib/format";

export default function ApprovalsPage({ params }: PageProps<"/projects/[id]/approvals">) {
  return (
    <Suspense fallback={<p className="loading">Loading approvals</p>}>
      <ApprovalsView params={params} />
    </Suspense>
  );
}

const TAG: Record<ApprovalStatus, string> = {
  lapsed: "tag tag-overdue",
  lapsing: "tag tag-soon",
  applied: "tag tag-upcoming",
  to_apply: "tag tag-done",
  granted: "tag tag-pass",
};

function detail(a: ApprovalRow): string {
  const parts = [a.authority, a.reference ? `No. ${a.reference}` : null];
  if (a.granted_on) parts.push(`granted ${day(a.granted_on)}`);
  else if (a.applied_on) parts.push(`applied for ${day(a.applied_on)}`);
  if (a.valid_until) {
    const left = a.days_left ?? 0;
    parts.push(
      left < 0
        ? `lapsed ${day(a.valid_until)}`
        : `valid until ${day(a.valid_until)}${a.status === "lapsing" ? `, ${plural(left, "day")} left` : ""}`,
    );
  }
  return parts.filter(Boolean).join("  ·  ");
}

async function ApprovalsView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const v = await api.approvals(id);
  const c = v.counts;
  const attention = c.lapsed + c.lapsing;

  return (
    <>
      <section className="section">
        <div className="section-head">
          <h2>Approvals</h2>
          <p>
            {v.approvals.length === 0
              ? "Permissions, consents and NOCs, with when each lapses"
              : [
                  attention ? `${attention} to renew` : null,
                  c.applied ? `${c.applied} applied for` : null,
                  c.to_apply ? `${c.to_apply} not applied for` : null,
                  c.granted ? `${c.granted} granted` : null,
                ]
                  .filter(Boolean)
                  .join(", ")}
          </p>
        </div>
        <p className="chips" style={{ alignItems: "center" }}>
          {v.can_edit ? (
            <Link href={`/projects/${id}/import`} className="button button-secondary">
              Import from Excel
            </Link>
          ) : null}
          <a href={`/download/projects/${id}/exports/approvals.xlsx`} className="link-action">
            Download as Excel
          </a>
          {v.can_edit && v.approvals.length > 0 ? (
            <Link href={`/projects/${id}/table/approvals`} className="link-action">
              Edit as a table
            </Link>
          ) : null}
        </p>

        {v.can_edit ? (
          v.approvals.length === 0 ? (
            <div className="empty">
              <p>
                No approvals listed yet. Start from the usual ones for a Karnataka residential project, then fill in the
                dates and delete what does not apply.
              </p>
              <div style={{ marginTop: 12 }}>
                <ActionForm action={addStandardApprovals.bind(null, id)} label="Set up the usual approvals" pendingLabel="Setting up" />
              </div>
            </div>
          ) : (
            <details className="disclosure">
              <summary>Add an approval</summary>
              <ActionForm action={createApproval.bind(null, id)} label="Add the approval" pendingLabel="Adding">
                <ApprovalFields prefix="new-approval" />
              </ActionForm>
            </details>
          )
        ) : v.approvals.length === 0 ? (
          <p className="empty">No approvals listed yet.</p>
        ) : null}

        {v.approvals.length > 0 ? (
          <ul className="rows">
            {v.approvals.map((a) => (
              <li key={a.id} className="row">
                <div>
                  <span className={TAG[a.status]}>{a.status_text}</span>
                </div>
                <div>
                  <p className="row-title">{a.name}</p>
                  <p className="row-detail">{detail(a) || "No dates yet"}</p>
                  {a.note ? <p className="row-meta">{a.note}</p> : null}
                  {v.can_edit ? (
                    <details className="disclosure">
                      <summary>Change</summary>
                      <ActionForm action={updateApproval.bind(null, a.id)} label="Save" pendingLabel="Saving" secondary>
                        <ApprovalFields prefix={`ap-${a.id}`} approval={a} />
                      </ActionForm>
                      <ActionForm action={deleteApproval.bind(null, a.id)} label="Delete the approval" pendingLabel="Deleting" secondary />
                    </details>
                  ) : null}
                  <History entries={a.history} />
                </div>
                <div />
              </li>
            ))}
          </ul>
        ) : null}
        {v.can_edit && v.approvals.length > 0 && v.standard_missing > 0 ? (
          <details className="disclosure">
            <summary>{`Add the usual approvals not listed yet (${v.standard_missing})`}</summary>
            <ActionForm action={addStandardApprovals.bind(null, id)} label="Add them" pendingLabel="Adding" secondary />
          </details>
        ) : null}
      </section>
    </>
  );
}
