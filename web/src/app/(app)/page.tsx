import Link from "next/link";
import { Suspense } from "react";

import { ObligationRows } from "@/components/obligations";
import { type Obligation, type Status, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

const FIRST = 8;
const MONEY = 4;

export default function TodayPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Today</h1>
          <p>What to do next, the most urgent first.</p>
        </div>
      </div>
      <Suspense fallback={<p className="loading">Loading what needs you</p>}>
        <TodayView />
      </Suspense>
    </>
  );
}

async function TodayView() {
  const today = await api.today();
  if (today.kind === "certifier") {
    return (
      <>
        <p className="muted small" style={{ marginBottom: 16 }}>
          {today.organization}, certifying {plural(today.summary.projects, "project")}, as of{" "}
          {day(today.as_of)}
        </p>
        <div className="stats">
          <div className="stat">
            <p className="stat-label">Waiting for your signature</p>
            <p className="stat-value">{today.summary.waiting}</p>
            <p className="stat-note">Figures are prepared from each developer&apos;s books</p>
          </div>
        </div>
        <section className="section">
          <div className="section-head">
            <h2>To review and sign</h2>
            <p>Check each figure against the books, change it if you need to, then sign</p>
          </div>
          <ObligationRows
            items={today.items}
            today={today.as_of}
            empty="Nothing is waiting for your signature."
          />
        </section>
      </>
    );
  }
  const { summary } = today;
  if (summary.projects === 0) return <Welcome />;
  const pick = (statuses: Status[]): Obligation[] => today.items.filter((o) => statuses.includes(o.status));
  const now = pick(["overdue", "due_soon", "at_risk"]);
  const money = pick(["opportunity"]);
  const later = pick(["upcoming"]);

  return (
    <>
      <p className="status-line">
        {now.length === 0
          ? "Nothing needs you right now."
          : `${plural(now.length, "thing")} ${now.length === 1 ? "needs" : "need"} you. If they are missed, ${inr(summary.at_stake)} is at stake.`}
      </p>
      {today.to_review > 0 ? (
        <p className="notice" style={{ marginBottom: 24 }}>
          {`${plural(today.to_review, "file")} ${today.to_review === 1 ? "is" : "are"} waiting for a choice from you. `}
          <a href="/review" className="link-action">
            Open them
          </a>
        </p>
      ) : null}

      <section className="section">
        <ObligationRows items={now.slice(0, FIRST)} today={today.as_of} empty="All done for now." />
        {now.length > FIRST ? (
          <details className="disclosure">
            <summary>{`${now.length - FIRST} more`}</summary>
            <ObligationRows items={now.slice(FIRST)} today={today.as_of} />
          </details>
        ) : null}
      </section>

      {money.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>{`Money you can draw: ${inr(summary.drawable_now)}`}</h2>
          </div>
          <ObligationRows items={money.slice(0, MONEY)} today={today.as_of} quiet />
          {money.length > MONEY ? (
            <details className="disclosure">
              <summary>{`${money.length - MONEY} more`}</summary>
              <ObligationRows items={money.slice(MONEY)} today={today.as_of} quiet />
            </details>
          ) : null}
        </section>
      ) : null}

      {later.length > 0 ? (
        <section className="section">
          <details className="disclosure">
            <summary>{`Coming up later (${later.length})`}</summary>
            <ObligationRows items={later} today={today.as_of} />
          </details>
        </section>
      ) : null}
    </>
  );
}

async function Welcome() {
  const me = await api.me();
  const org = me.organization;
  return (
    <section>
      <h2>{`Welcome to Lekhara${org ? `, ${org.name}` : ""}`}</h2>
      <p className="muted" style={{ marginTop: 6, maxWidth: 720 }}>
        {org?.access === "trial" ? `Your free month has started: ${org.days_left} days left. ` : ""}
        Add a project and this page will tell you what to do next.
      </p>
      <ol className="steps-list">
        <li>
          <div>
            <p className="row-title">Add your first project</p>
            <p className="row-detail">Upload its K-RERA certificate and we fill in the rest.</p>
          </div>
          {org?.can_add_projects && org.access !== "read_only" ? (
            <Link href="/projects/new" className="button">
              Add a project
            </Link>
          ) : null}
        </li>
        <li>
          <div>
            <p className="row-title">Or look around first</p>
            <p className="row-detail">Three sample projects, all filled in. Nothing there can be changed, so press anything.</p>
          </div>
          <Link href="/projects" className="button button-secondary">
            See the samples
          </Link>
        </li>
      </ol>
    </section>
  );
}
