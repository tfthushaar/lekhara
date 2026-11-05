import Link from "next/link";
import { Suspense } from "react";

import { PlainProjectTabs, ProjectTabs } from "@/components/nav";
import { api } from "@/lib/api";
import { day } from "@/lib/format";
import { currentView } from "@/lib/view";

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
  const [p, view, me] = await Promise.all([api.project(id), currentView(), api.me()]);
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
          </p>
          <h1>
            {p.name}
            {p.access.sample ? <span className="tag tag-upcoming" style={{ marginLeft: 12, verticalAlign: "middle" }}>Sample, read-only</span> : null}
          </h1>
          <p>
            {[[p.locality, p.city].filter(Boolean).join(", "), p.possession_due_on ? `possession by ${day(p.possession_due_on)}` : null]
              .filter(Boolean)
              .join(", ")}
          </p>
          <p className="small muted" style={{ marginTop: 4 }}>{`${p.land_structure}. K-RERA ${p.krera_registration}`}</p>
        </div>
      </div>
      <Suspense fallback={<PlainProjectTabs projectId={id} team={p.access.team} view={view} areas={me.areas} />}>
        <ProjectTabs projectId={id} team={p.access.team} view={view} areas={me.areas} />
      </Suspense>
    </>
  );
}
