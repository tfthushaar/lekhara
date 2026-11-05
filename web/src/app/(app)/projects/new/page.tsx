import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { createProject, readCertificate } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { api } from "@/lib/api";

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
  const me = await api.me();
  const details = (open: boolean) => (
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
      </div>
      <details className="disclosure" open={open}>
        <summary>More details</summary>
        <div className="field-grid">
          <div className="field">
            <label htmlFor="locality">Locality</label>
            <input id="locality" name="locality" placeholder="Yelahanka" defaultValue={v("locality")} />
          </div>
          <div className="field">
            <label htmlFor="city">City</label>
            <input id="city" name="city" defaultValue={v("city") || "Bengaluru"} />
          </div>
          <div className="field">
            <label htmlFor="spv">Promoter, if different from your firm</label>
            <input id="spv" name="spv_name" defaultValue={v("spv_name")} />
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
              <option value="residential_5pc">Residential, 5%</option>
              <option value="affordable_1pc">Affordable housing, 1%</option>
              <option value="commercial_12pc">Commercial, 12%</option>
              <option value="rrep_mixed">Residential with some commercial</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="bank">Bank holding the RERA account</label>
            <input id="bank" name="escrow_bank" />
          </div>
        </div>
      </details>
    </ActionForm>
  );
  return (
    <>
      <div className="page-head">
        <div>
          <p className="crumb">
            <Link href="/projects">Projects</Link>
          </p>
          <h1>Add a project</h1>
          <p>Upload its K-RERA certificate and we fill in the rest.</p>
        </div>
      </div>
      <div style={{ maxWidth: 880 }}>
        {read ? (
          <p className="notice" style={{ marginBottom: 24 }}>
            {v("missing")
              ? `We read your certificate. Check the details, and fill in ${v("missing")}.`
              : "We read your certificate. Check the details, then add the project."}
          </p>
        ) : (
          <div style={{ marginBottom: 24 }}>
            <ActionForm action={readCertificate} label="Read the certificate" pendingLabel="Reading">
              <div className="field" style={{ maxWidth: 520 }}>
                <label htmlFor="certificate">The K-RERA certificate (PDF)</label>
                <input id="certificate" name="file" type="file" accept=".pdf" required />
              </div>
            </ActionForm>
            {me.demo ? (
              <p className="small muted">
                No certificate to hand?{" "}
                <a href="/download/demo/samples/krera-certificate.pdf">Download a sample one</a>, then choose it above.
              </p>
            ) : null}
          </div>
        )}
        {read ? details(true) : (
          <details className="disclosure">
            <summary>No certificate to hand? Type the details</summary>
            {details(false)}
          </details>
        )}
      </div>
    </>
  );
}
