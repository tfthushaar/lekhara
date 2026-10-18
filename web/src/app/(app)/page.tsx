import Link from "next/link";
import { Suspense } from "react";

import { ObligationRows } from "@/components/obligations";
import { type Obligation, type Status, api } from "@/lib/api";
import { day, inr, plural } from "@/lib/format";

const SECTIONS: { title: string; note: string; statuses: Status[]; empty: string }[] = [
  {
    title: "Needs you now",
    note: "Late, or due within two weeks",
    statuses: ["overdue", "due_soon"],
    empty: "Nothing is late or due soon.",
  },
  {
    title: "Money waiting",
    note: "Cash you can draw, or that is on its way",
    statuses: ["opportunity"],
    empty: "No money is waiting to be drawn.",
  },
  {
    title: "At risk",
    note: "Act before these become bills",
    statuses: ["at_risk"],
    empty: "No exposures right now.",
  },
  {
    title: "Coming up",
    note: "Later deadlines, so nothing is a surprise",
    statuses: ["upcoming"],
    empty: "Nothing else is scheduled.",
  },
];

export default function TodayPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Today</h1>
          <p>What needs you, in order of what matters most.</p>
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
  const pick = (statuses: Status[]): Obligation[] =>
    today.items.filter((o) => statuses.includes(o.status));

  return (
    <>
      <p className="muted small" style={{ marginBottom: 16 }}>
        {today.organization}, {plural(summary.projects, "project")}, as of {day(today.as_of)}
      </p>
      {today.to_review > 0 ? (
        <p className="notice" style={{ marginBottom: 24 }}>
          {`${plural(today.to_review, "thing")} brought in by you or by email ${today.to_review === 1 ? "waits" : "wait"} for a choice. `}
          <a href="/review" className="link-action">
            Open the review queue
          </a>
        </p>
      ) : null}
      <div className="stats">
        <div className="stat">
          <p className="stat-label">You can draw now</p>
          <p className="stat-value">{inr(summary.drawable_now)}</p>
          <p className="stat-note">From the RERA accounts of all projects</p>
        </div>
        <div className="stat">
          <p className="stat-label">Due this week</p>
          <p className="stat-value">{summary.due_this_week}</p>
          <p className="stat-note">Including anything already late</p>
        </div>
        <div className="stat">
          <p className="stat-label">Money at stake</p>
          <p className="stat-value">{inr(summary.at_stake)}</p>
          <p className="stat-note">Penalties, tax and shortfalls if nothing is done</p>
        </div>
      </div>

      {SECTIONS.map((section) => (
        <section key={section.title} className="section">
          <div className="section-head">
            <h2>{section.title}</h2>
            <p>{section.note}</p>
          </div>
          <ObligationRows items={pick(section.statuses)} today={today.as_of} empty={section.empty} />
        </section>
      ))}
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
        {org?.access === "trial"
          ? `Your free month has started: ${org.days_left} days on your own projects. `
          : ""}
        Three steps and this page starts telling you what each project owes, and to whom.
      </p>
      <ol className="steps-list">
        <li>
          <div>
            <p className="row-title">Add your first project</p>
            <p className="row-detail">The name, K-RERA number and dates from its registration.</p>
          </div>
          {org?.can_add_projects && org.access !== "read_only" ? (
            <Link href="/projects/new" className="button">
              Add a project
            </Link>
          ) : null}
        </li>
        <li>
          <div>
            <p className="row-title">See what Lekhara does with real data</p>
            <p className="row-detail">
              Three sample Bengaluru projects, with escrow, collections, handover, disputes and
              documents filled in. Look around; nothing there can be changed.
            </p>
          </div>
          <Link href="/projects" className="button button-secondary">
            Explore the samples
          </Link>
        </li>
        <li>
          <div>
            <p className="row-title">Bring in your team and certifiers</p>
            <p className="row-detail">
              Accounts, finance, and the architect, engineer and CA who sign your withdrawals. One
              subscription covers everyone.
            </p>
          </div>
          <Link href="/settings" className="button button-secondary">
            Invite people
          </Link>
        </li>
      </ol>
    </section>
  );
}
