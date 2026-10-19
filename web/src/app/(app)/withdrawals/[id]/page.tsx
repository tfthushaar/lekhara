import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import {
  rejectWithdrawal,
  releaseWithdrawal,
  signCertificate,
  submitWithdrawal,
  updateFigure,
} from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import {
  type CertificateView,
  type CheckView,
  type Figure,
  type Me,
  type Withdrawal,
  api,
} from "@/lib/api";
import { day, inr, inrFull, pct } from "@/lib/format";

export const metadata: Metadata = { title: "Withdrawal" };

export default function WithdrawalPage({ params }: PageProps<"/withdrawals/[id]">) {
  return (
    <Suspense fallback={<p className="loading">Loading the withdrawal</p>}>
      <WithdrawalView params={params} />
    </Suspense>
  );
}

const CHECK_TAG: Record<CheckView["status"], { label: string; className: string }> = {
  pass: { label: "Pass", className: "tag tag-pass" },
  warn: { label: "Check", className: "tag tag-warn" },
  fail: { label: "Fails", className: "tag tag-fail" },
  pending: { label: "Waiting", className: "tag tag-upcoming" },
};

function headline(w: Withdrawal): string {
  switch (w.status) {
    case "released":
      return `Released on ${day(w.released_on)}`;
    case "rejected":
      return "The bank rejected this request";
    case "submitted":
      return "With the bank";
    case "ready":
      return "Ready to send to the bank";
    default:
      return `Waiting for ${w.waiting_on}`;
  }
}

function figureValue(f: Figure): string {
  if (f.value === null) return "Not entered";
  return f.kind === "percent" ? pct(f.value) : inr(f.value);
}

function differs(f: Figure): boolean {
  return !f.matches_books;
}

async function WithdrawalView({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [w, me] = await Promise.all([api.withdrawal(id), api.me()]);
  const failing = w.checks.some((c) => c.status === "fail");

  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
            {"  /  "}
            <Link href={`/projects/${w.project_id}`}>{w.project_name}</Link>
            {"  /  "}
            <Link href={`/projects/${w.project_id}/escrow`}>Escrow</Link>
          </p>
          <h1>Withdrawal of {inr(w.amount)}</h1>
          <p>
            From the RERA account{w.escrow_bank ? ` at ${w.escrow_bank}` : ""}. Started{" "}
            {day(w.created_on)}.
          </p>
        </div>
        <div>
          <a href={`/download/withdrawals/${w.id}/pack.pdf`} className="button button-secondary">
            The pack for the bank
          </a>
        </div>
      </div>

      <p className="status-line">{headline(w)}</p>
      <ol className="steps" style={{ marginBottom: 40 }}>
        {w.steps.map((s) => (
          <li key={s.name} className={`step step-${s.status}`}>
            {s.name}
          </li>
        ))}
      </ol>

      <section>
        <div className="section-head">
          <h2>Certificates</h2>
          <p>Prepared by Lekhara from the books. Each certifier reviews, changes if needed, and signs.</p>
        </div>
        <div className="grid-3">
          {w.certificates.map((c) => (
            <CertificateCard
              key={c.role}
              w={w}
              c={c}
              me={me}
              mine={w.permissions.sign_roles.includes(c.role)}
            />
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Checks before the bank sees it</h2>
          <p>The same checks a bank or the K-RERA auditor would run</p>
        </div>
        <ul className="rows">
          {w.checks.map((c) => (
            <li key={c.code} className="row">
              <div>
                <span className={CHECK_TAG[c.status].className}>{CHECK_TAG[c.status].label}</span>
              </div>
              <div>
                <p className="row-title">{c.title}</p>
                <p className="row-detail">{c.detail}</p>
              </div>
              <div />
            </li>
          ))}
        </ul>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Next step</h2>
        </div>
        <div style={{ marginTop: 16, maxWidth: 560 }}>
          <NextStep w={w} failing={failing} />
        </div>
      </section>
    </>
  );
}

function CertificateCard({
  w,
  c,
  me,
  mine,
}: {
  w: Withdrawal;
  c: CertificateView;
  me: Me;
  mine: boolean;
}) {
  return (
    <div className={c.signed ? "card card-done" : "card"}>
      <div className="card-head">
        <h3>{c.label}</h3>
        <span className={c.signed ? "tag tag-pass" : "tag tag-soon"}>
          {c.signed ? "Signed" : "To sign"}
        </span>
      </div>
      <p className="small muted">Certifies: {c.certifies.toLowerCase()}</p>

      {c.figures.map((f) => (
        <div key={f.field} className="figure">
          <p className="stat-label">{f.label}</p>
          <p className="figure-value">{figureValue(f)}</p>
          <p className={differs(f) ? "small strong" : "small muted"}>
            {differs(f) ? "Differs from the books: " : "The books: "}
            {f.kind === "percent" ? pct(f.books) : inr(f.books)}
          </p>
        </div>
      ))}

      {c.signed ? (
        <p className="small" style={{ marginTop: 16 }}>
          Signed by {c.signer_name}, {c.signer_firm}, on {day(c.issued_on)}.
        </p>
      ) : mine ? (
        <>
          <details className="disclosure">
            <summary>Change a figure</summary>
            {c.figures.map((f) => (
              <ActionForm
                key={f.field}
                action={updateFigure.bind(null, w.id, c.role, f.field)}
                label="Update"
                pendingLabel="Updating"
                secondary
                className="inline-form"
              >
                <div className="field">
                  <label htmlFor={`${c.role}-${f.field}`}>
                    {f.label} {f.kind === "percent" ? "(percent)" : "(rupees)"}
                  </label>
                  <input
                    id={`${c.role}-${f.field}`}
                    name="value"
                    inputMode="decimal"
                    defaultValue={f.value ?? ""}
                  />
                  {f.kind === "money" && f.value ? (
                    <span className="small muted">Now {inrFull(f.value)}</span>
                  ) : null}
                </div>
              </ActionForm>
            ))}
          </details>
          <ActionForm
            action={signCertificate.bind(null, w.id, c.role)}
            label="Sign this certificate"
            pendingLabel="Signing"
            className="sign-form"
          >
            <p className="small muted" style={{ marginBottom: 12 }}>
              Signs as {me.user.name}
              {me.user.firm ? `, ${me.user.firm}` : ""}, dated today.
            </p>
          </ActionForm>
        </>
      ) : (
        <p className="small muted" style={{ marginTop: 16 }}>
          Waiting for the project&apos;s {c.label.toLowerCase()}.
        </p>
      )}
    </div>
  );
}

function NextStep({ w, failing }: { w: Withdrawal; failing: boolean }) {
  if (w.status === "awaiting_signatures") {
    return (
      <p>
        {failing
          ? "Fix the figures marked Fails, then the certifier can sign again."
          : `Waiting for ${w.waiting_on}. Once all three have signed and every check passes, you can send it to the bank.`}
      </p>
    );
  }
  if (w.status === "ready" && !w.permissions.can_submit) {
    return <p>All three certificates are signed. The developer&apos;s team sends the pack to the bank.</p>;
  }
  if (w.status === "ready") {
    return (
      <>
        <p style={{ marginBottom: 16 }}>
          All three certificates are signed and every check passes. Send the signed pack to{" "}
          {w.escrow_bank ?? "the bank"}, then mark it as sent.
        </p>
        <ActionForm
          action={submitWithdrawal.bind(null, w.id)}
          label="Mark as sent to the bank"
          pendingLabel="Saving"
        />
      </>
    );
  }
  if (w.status === "submitted" && !w.permissions.can_release) {
    return (
      <p>
        With {w.escrow_bank ?? "the bank"}. The owner or finance records the release when the money
        arrives.
      </p>
    );
  }
  if (w.status === "submitted") {
    return (
      <>
        <p style={{ marginBottom: 16 }}>When the bank releases the money, record it here.</p>
        <ActionForm
          action={releaseWithdrawal.bind(null, w.id)}
          label="Record the release"
          pendingLabel="Saving"
        >
          <div className="field">
            <label htmlFor="amount">Amount released (rupees)</label>
            <input id="amount" name="amount" inputMode="decimal" defaultValue={w.amount} />
          </div>
          <div className="field">
            <label htmlFor="bank_reference">Bank reference</label>
            <input id="bank_reference" name="bank_reference" />
          </div>
        </ActionForm>
        <details className="disclosure" style={{ marginTop: 24 }}>
          <summary>The bank rejected it</summary>
          <ActionForm
            action={rejectWithdrawal.bind(null, w.id)}
            label="Record the rejection"
            pendingLabel="Saving"
            secondary
          >
            <div className="field">
              <label htmlFor="reason">What the bank said</label>
              <input id="reason" name="reason" />
            </div>
          </ActionForm>
        </details>
      </>
    );
  }
  if (w.status === "released") {
    return (
      <p>
        {inr(w.released_amount)} was released on {day(w.released_on)}
        {w.bank_reference ? `, reference ${w.bank_reference}` : ""}. It is now part of the
        withdrawals for this project.
      </p>
    );
  }
  return (
    <p>
      {w.rejection_reason ? `The bank said: ${w.rejection_reason}. ` : ""}
      <Link href={`/projects/${w.project_id}/escrow`} className="link-action">
        Start a new withdrawal
      </Link>
    </p>
  );
}
