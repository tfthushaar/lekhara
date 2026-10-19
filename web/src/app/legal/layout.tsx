import { Suspense } from "react";

import { POLICIES, SiteFooter, SiteHeader } from "@/components/site";
import { LinkRow } from "@/components/site-nav";
import { api } from "@/lib/api";

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main className="main legal">
        <Suspense fallback={<LinkRow links={POLICIES} label="Policies" className="tabs" plain />}>
          <LinkRow links={POLICIES} label="Policies" className="tabs" />
        </Suspense>
        {children}
        <Suspense fallback={null}>
          <Contact />
        </Suspense>
      </main>
      <SiteFooter />
    </>
  );
}

async function Contact() {
  const info = await api.legal();
  return (
    <section className="legal-contact">
      <h2>Questions and complaints</h2>
      <p>
        {`${info.company_name}, ${info.company_address}. Grievance officer: ${info.grievance_officer}, `}
        <a href={`mailto:${info.grievance_email}`}>{info.grievance_email}</a>
        {". We reply within 30 days. If you are not satisfied with the reply, you may complain to the Data Protection Board of India."}
      </p>
    </section>
  );
}
