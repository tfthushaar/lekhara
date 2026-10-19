import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { createProject, readCertificate } from "@/app/actions";
import { ActionForm } from "@/components/action-form";

export const metadata: Metadata = { title: "Add a project" };

export default function NewProjectPage({ searchParams }: PageProps<"/projects/new">) {
  return (
    <Suspense fallback={<p className="loading">Opening the form</p>}>
      <NewProject searchParams={searchParams} />
    </Suspense>
  );
}

async function NewProject({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const v = (key: string) => (typeof query[key] === "string" ? (query[key] as string) : "");
  const read = v("from") === "certificate";
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
          </p>
          <h1>Add a project</h1>
          <p>The details on its K-RERA registration. You can change any of them later.</p>
        </div>
      </div>
      <div style={{ maxWidth: 880 }}>
        {read ? (
          <p className="notice" style={{ marginBottom: 24 }}>
            {v("missing")
              ? `Read from the certificate. Check each detail, and fill in ${v("missing")}, which it did not show clearly.`
              : "Read from the certificate. Check each detail before adding the project."}
          </p>
        ) : (
          <details className="disclosure" style={{ marginBottom: 24 }} open>
            <summary>Read the details from the K-RERA registration certificate</summary>
            <ActionForm action={readCertificate} label="Read the certificate" pendingLabel="Reading">
              <div className="field" style={{ maxWidth: 520 }}>
                <label htmlFor="certificate">The certificate (PDF)</label>
                <input id="certificate" name="file" type="file" accept=".pdf" required />
              </div>
            </ActionForm>
            <p className="small muted">Or type them below.</p>
          </details>
        )}
        <ActionForm action={createProject} label="Add the project" pendingLabel="Adding">
          <div className="field-grid">
            <div className="field">
              <label htmlFor="name">Project name</label>
              <input id="name" name="name" required defaultValue={v("name")} />
            </div>
            <div className="field">
              <label htmlFor="krera">K-RERA registration number</label>
              <input id="krera" name="krera_registration" required placeholder="PRM/KA/RERA/1251/..." defaultValue={v("krera_registration")} />
            </div>
            <div className="field">
              <label htmlFor="registered_on">Registered on</label>
              <input id="registered_on" name="registered_on" type="date" required defaultValue={v("registered_on")} />
            </div>
            <div className="field">
              <label htmlFor="possession">Possession promised by</label>
              <input id="possession" name="possession_due_on" type="date" defaultValue={v("possession_due_on")} />
            </div>
            <div className="field">
              <label htmlFor="locality">Locality</label>
              <input id="locality" name="locality" placeholder="Yelahanka" defaultValue={v("locality")} />
            </div>
            <div className="field">
              <label htmlFor="city">City</label>
              <input id="city" name="city" defaultValue={v("city") || "Bengaluru"} />
            </div>
            <div className="field">
              <label htmlFor="spv">Promoter as registered</label>
              <input id="spv" name="spv_name" placeholder="Your firm's legal name, if different" defaultValue={v("spv_name")} />
            </div>
            <div className="field">
              <label htmlFor="land">Land</label>
              <select id="land" name="land_structure" defaultValue="own">
                <option value="own">Own land</option>
                <option value="jda_area_share">Joint development, area share</option>
                <option value="jda_revenue_share">Joint development, revenue share</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="gst">GST on sales</label>
              <select id="gst" name="gst_regime" defaultValue="residential_5pc">
                <option value="residential_5pc">Residential, 5% without input credit</option>
                <option value="affordable_1pc">Affordable housing, 1% without input credit</option>
                <option value="commercial_12pc">Commercial, 12% with input credit</option>
                <option value="rrep_mixed">Residential with commercial space</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="bank">Bank holding the RERA account</label>
              <input id="bank" name="escrow_bank" />
            </div>
          </div>
        </ActionForm>
      </div>
    </>
  );
}
