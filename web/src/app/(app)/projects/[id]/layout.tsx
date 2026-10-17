import Link from "next/link";
import { Suspense } from "react";

import { PlainProjectTabs, ProjectTabs } from "@/components/nav";
import { api } from "@/lib/api";
import { day } from "@/lib/format";

export default function ProjectLayout({ children, params }: LayoutProps<"/projects/[id]">) {
  return (
    <>
      <Suspense
        fallback={
          <div className="page-head">
            <div>
              <p className="crumb">
                <Link href="/projects">Projects</Link>
              </p>
              <h1 className="muted">Loading project</h1>
            </div>
          </div>
        }
      >
        <ProjectHeader params={params} />
      </Suspense>
      {children}
    </>
  );
}

async function ProjectHeader({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = await api.project(id);
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
          </p>
          <h1>{p.name}</h1>
          <p>
            {p.locality}, {p.city}. {p.land_structure}. K-RERA {p.krera_registration}
          </p>
        </div>
        {p.possession_due_on ? (
          <div className="head-side">
            <p className="stat-label">Possession committed</p>
            <p className="head-side-value">{day(p.possession_due_on)}</p>
          </div>
        ) : null}
      </div>
      <Suspense fallback={<PlainProjectTabs projectId={id} team={p.access.team} />}>
        <ProjectTabs projectId={id} team={p.access.team} />
      </Suspense>
    </>
  );
}
