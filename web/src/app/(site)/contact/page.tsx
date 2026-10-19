import type { Metadata } from "next";
import { Suspense } from "react";

import { api } from "@/lib/api";

export const metadata: Metadata = {
  title: "Contact",
  description: "Write to Lekhara about the product, a walkthrough on one of your own projects, or your account.",
};

export default function ContactPage() {
  return (
    <>
      <section className="site-hero">
        <h1>Talk to us.</h1>
        <p className="site-lead">
          About Lekhara, a walkthrough on one of your own projects, or your account. Tell us your firm&apos;s name and how
          many projects you run.
        </p>
      </section>
      <section className="site-section">
        <Suspense fallback={null}>
          <Details />
        </Suspense>
      </section>
    </>
  );
}

async function Details() {
  const info = await api.legal();
  return (
    <dl className="site-terms">
      <dt>Email</dt>
      <dd>
        <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a>
      </dd>
      {info.contact_phone ? (
        <>
          <dt>Phone</dt>
          <dd>
            <a href={`tel:${info.contact_phone.replace(/\s/g, "")}`}>{info.contact_phone}</a>
          </dd>
        </>
      ) : null}
      <dt>Office</dt>
      <dd>{`${info.company_name}, ${info.company_address}`}</dd>
      <dt>Personal data</dt>
      <dd>
        {`Questions or complaints about personal data go to our grievance officer, ${info.grievance_officer}, at `}
        <a href={`mailto:${info.grievance_email}`}>{info.grievance_email}</a>
        {". We reply within 30 days."}
      </dd>
    </dl>
  );
}
