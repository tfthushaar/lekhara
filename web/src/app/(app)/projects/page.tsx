import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusTag } from "@/components/obligations";
import { type ProjectCard, api } from "@/lib/api";
import { inr, pct } from "@/lib/format";

export const metadata: Metadata = { title: "Projects" };

export default function ProjectsPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Projects</h1>
          <p>Every live project, with what it can draw and what needs attention.</p>
        </div>
      </div>
      <Suspense fallback={<p className="loading">Loading projects</p>}>
        <ProjectSections />
      </Suspense>
    </>
  );
}

function attention(p: ProjectCard): string {
  const parts = [
    p.counts.overdue ? `${p.counts.overdue} overdue` : null,
    p.counts.due_soon ? `${p.counts.due_soon} due soon` : null,
    p.counts.at_risk ? `${p.counts.at_risk} at risk` : null,
  ].filter(Boolean);
  return parts.length ? parts.join(", ") : "Nothing pressing";
}

async function ProjectSections() {
  const [projects, me] = await Promise.all([api.projects(), api.me()]);
  const own = projects.filter((p) => !p.sample);
  const samples = projects.filter((p) => p.sample);
  const org = me.organization;
  const canAdd = Boolean(org?.can_add_projects && org.access !== "read_only" && !org.is_sample);
  return (
    <>
      {canAdd ? (
        <p style={{ marginBottom: 24 }}>
          <Link href="/projects/new" className="button">
            Add a project
          </Link>
        </p>
      ) : null}
      {own.length > 0 ? (
        <ProjectList projects={own} />
      ) : (
        <p className="empty">
          {canAdd ? "No projects yet. Add your first one above." : "No projects to show yet."}
        </p>
      )}
      {samples.length > 0 ? (
        <section className="section">
          <div className="section-head">
            <h2>Sample projects</h2>
            <p>A fictional developer, to show what Lekhara does. Read-only.</p>
          </div>
          <ProjectList projects={samples} />
        </section>
      ) : null}
    </>
  );
}

function ProjectList({ projects }: { projects: ProjectCard[] }) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Project</th>
          <th className="right">Certified progress</th>
          <th className="right">Final cost</th>
          <th className="right">Can draw now</th>
          <th>Needs attention</th>
        </tr>
      </thead>
      <tbody>
        {projects.map((p) => {
          const over = Number(p.anticipated_final_cost) - Number(p.budget);
          return (
            <tr key={p.id}>
              <td>
                <Link href={`/projects/${p.id}`} className="row-title">
                  {p.name}
                </Link>
                <p className="row-detail">
                  {p.locality}, {p.land_structure.toLowerCase()}
                </p>
              </td>
              <td className="right num">{pct(p.progress_pct)}</td>
              <td className="right num">
                {inr(p.anticipated_final_cost)}
                <p className="row-detail">
                  {over > 0 ? `${inr(String(over))} over budget` : "Within budget"}
                </p>
              </td>
              <td className="right num">{inr(p.drawable_now)}</td>
              <td>
                {p.next ? <StatusTag status={p.next.status} /> : null}
                <p className="row-detail">{attention(p)}</p>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
