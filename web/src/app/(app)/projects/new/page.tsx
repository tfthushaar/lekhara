import type { Metadata } from "next";
import Link from "next/link";

import { createProject } from "@/app/actions";
import { ActionForm } from "@/components/action-form";

export const metadata: Metadata = { title: "Add a project" };

export default function NewProjectPage() {
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
        <ActionForm action={createProject} label="Add the project" pendingLabel="Adding">
          <div className="field-grid">
            <div className="field">
              <label htmlFor="name">Project name</label>
              <input id="name" name="name" required />
            </div>
            <div className="field">
              <label htmlFor="krera">K-RERA registration number</label>
              <input id="krera" name="krera_registration" required placeholder="PRM/KA/RERA/1251/..." />
            </div>
            <div className="field">
              <label htmlFor="registered_on">Registered on</label>
              <input id="registered_on" name="registered_on" type="date" required />
            </div>
            <div className="field">
              <label htmlFor="possession">Possession promised by</label>
              <input id="possession" name="possession_due_on" type="date" />
            </div>
            <div className="field">
              <label htmlFor="locality">Locality</label>
              <input id="locality" name="locality" placeholder="Yelahanka" />
            </div>
            <div className="field">
              <label htmlFor="city">City</label>
              <input id="city" name="city" defaultValue="Bengaluru" />
            </div>
            <div className="field">
              <label htmlFor="spv">Promoter as registered</label>
              <input id="spv" name="spv_name" placeholder="Your firm's legal name, if different" />
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
