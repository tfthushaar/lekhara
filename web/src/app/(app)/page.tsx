import Link from "next/link";
import { Suspense } from "react";

import { ObligationRows } from "@/components/obligations";
import { type Obligation, type SalesToday, type SiteToday, type Status, type Tasks, api } from "@/lib/api";
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
  if (today.kind === "sales") return <SalesDay t={today} />;
  if (today.kind === "site") return <SiteDay t={today} />;
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
      <TaskList tasks={today.tasks} toReview={today.to_review} />

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

type Task = { count: number; title: string; many: string; button: string; href: string };

/** What the person is asked to do beyond the deadlines: approvals, payments, orders. */
function TaskList({ tasks, toReview }: { tasks?: Tasks; toReview: number }) {
  const list: Task[] = [
    { count: tasks?.to_approve ?? 0, title: "bill to approve", many: "bills to approve", button: "Approve", href: "/payables" },
    { count: tasks?.to_pay ?? 0, title: "approved bill to pay", many: "approved bills to pay", button: "Pay", href: "/payables" },
    { count: toReview, title: "file waiting for a choice", many: "files waiting for a choice", button: "Open", href: "/review" },
    {
      count: tasks?.to_order ?? 0,
      title: "material request from site",
      many: "material requests from site",
      button: "Order",
      href: tasks?.to_order_at ? `/projects/${tasks.to_order_at}/materials` : "/projects",
    },
    {
      count: tasks?.late_defects ?? 0,
      title: "defect past the 30 days",
      many: "defects past the 30 days",
      button: "See",
      href: tasks?.late_defects_at ? `/projects/${tasks.late_defects_at}/issues` : "/projects",
    },
    {
      count: tasks?.loan_conditions ?? 0,
      title: "lender's condition due soon",
      many: "lender's conditions due soon",
      button: "See",
      href: tasks?.loan_at ? `/projects/${tasks.loan_at}/cash` : "/projects",
    },
  ].filter((t) => t.count > 0);
  if (!list.length) return null;
  return (
    <ul className="rows" style={{ marginBottom: 32 }}>
      {list.map((t) => (
        <li key={t.title} className="row row-2">
          <p className="row-title">{plural(t.count, t.title, t.many)}</p>
          <div className="row-side">
            <Link href={t.href} className="button">
              {t.button}
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

function CallList({ calls }: { calls: SalesToday["calls"] }) {
  return (
    <ul className="rows">
      {calls.map((l) => (
        <li key={l.id} className="row row-2">
          <div>
            <p className="row-title">
              <Link href={`/leads/${l.id}`}>{l.name}</Link>
              {l.follow_up_late ? <span className="tag tag-overdue" style={{ marginLeft: 8 }}>Late</span> : null}
            </p>
            <p className="row-detail">{[l.project, l.stage_label, l.interest].filter(Boolean).join(", ")}</p>
          </div>
          <div className="row-side">
            {l.phone_key ? (
              <a href={`tel:+91${l.phone_key}`} className="button">
                Call
              </a>
            ) : null}
          </div>
        </li>
      ))}
    </ul>
  );
}

function SalesDay({ t }: { t: SalesToday }) {
  return (
    <>
      <p className="status-line">{t.calls.length ? `${plural(t.calls.length, "person", "people")} to call today.` : "Nobody to call today."}</p>
      {t.first_project ? (
        <p style={{ marginBottom: 24 }}>
          <Link href={`/projects/${t.first_project}/sales`} className="button button-secondary">
            Add someone new
          </Link>
        </p>
      ) : null}
      {t.calls.length > 0 ? <CallList calls={t.calls.slice(0, FIRST)} /> : null}
      {t.calls.length > FIRST ? (
        <details className="disclosure">
          <summary>{`${t.calls.length - FIRST} more`}</summary>
          <CallList calls={t.calls.slice(FIRST)} />
        </details>
      ) : null}
      {t.visits.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Site visits this week</h2>
          </div>
          <ul className="rows">
            {t.visits.map((v) => (
              <li key={v.id} className="row row-1">
                <div>
                  <p className="row-title">
                    <Link href={`/leads/${v.lead_id}`}>{v.lead}</Link>
                  </p>
                  <p className="row-detail">{`${day(v.on)}${v.time ? `, ${v.time}` : ""}, ${v.project}`}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {t.requests > 0 && t.first_project ? (
        <section className="section">
          <ul className="rows">
            <li className="row row-2">
              <p className="row-title">{`${plural(t.requests, "buyer's request", "buyers' requests")} open`}</p>
              <div className="row-side">
                <Link href={`/projects/${t.first_project}/issues`} className="button button-secondary">
                  See
                </Link>
              </div>
            </li>
          </ul>
        </section>
      ) : null}
    </>
  );
}

function SiteDay({ t }: { t: SiteToday }) {
  const left = t.projects.filter((p) => !p.report_filed).length;
  return (
    <>
      <p className="status-line">{left ? `Today's report: ${plural(left, "site")} still to do.` : "Today's reports are all done."}</p>
      <ul className="rows">
        {t.projects.map((p) => {
          const lines = [
            p.requests_waiting ? plural(p.requests_waiting, "material request") + " waiting" : null,
            p.issues_open ? `${plural(p.issues_open, "snag or defect", "snags and defects")} open${p.issues_late ? `, ${p.issues_late} late` : ""}` : null,
            p.low_stock ? `${plural(p.low_stock, "material")} running low` : null,
          ].filter(Boolean);
          return (
            <li key={p.id} className="row row-2 row-stack">
              <div>
                <p className="row-title">{p.name}</p>
                <p className="row-detail">{lines.length ? lines.join(". ") + "." : "Nothing else waiting."}</p>
              </div>
              <div className="row-side">
                {p.report_filed ? (
                  <Link href={`/projects/${p.id}/site`} className="button button-secondary">
                    Report done
                  </Link>
                ) : (
                  <Link href={`/projects/${p.id}/site`} className="button">
                    Write today&apos;s report
                  </Link>
                )}
                {p.requests_waiting || p.low_stock ? (
                  <Link href={`/projects/${p.id}/materials`} className="button button-secondary">
                    Materials
                  </Link>
                ) : null}
                {p.issues_open ? (
                  <Link href={`/projects/${p.id}/issues`} className="button button-secondary">
                    Snags
                  </Link>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
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
