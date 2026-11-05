import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { StatusTag } from "@/components/obligations";
import { type ProjectCard, api } from "@/lib/api";
import { inr, pct } from "@/lib/format";
import { projectHome } from "@/lib/places";

export const metadata: Metadata = { title: "Projects" };

export default function ProjectsPage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Projects</h1>
          <p>Your projects.</p>
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
        <ProjectList projects={own} areas={me.areas} />
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
          <ProjectList projects={samples} areas={me.areas} />
        </section>
      ) : null}
    </>
  );
}

function ProjectList({ projects, areas }: { projects: ProjectCard[]; areas: string[] }) {
  return (
    <ul className="rows">
      {projects.map((p) => (
        <li key={p.id} className="row row-2 row-stack">
          <div>
            <Link href={projectHome(p.id, areas)} className="row-title">
              {p.name}
            </Link>
            <p className="row-detail">{`${p.locality}, ${p.land_structure.toLowerCase()}`}</p>
            {!p.limited ? (
              <p className="row-meta">
                {[p.progress_pct ? `${pct(p.progress_pct)} built` : null, p.drawable_now ? `${inr(p.drawable_now)} can be drawn` : null, attention(p)]
                  .filter(Boolean)
                  .join(". ")}
              </p>
            ) : null}
          </div>
          <div className="row-side">
            {p.next ? <StatusTag status={p.next.status} /> : null}
            <Link href={projectHome(p.id, areas)} className="button button-secondary">
              Open
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}
