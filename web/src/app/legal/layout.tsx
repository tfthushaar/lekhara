import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="wordmark">
            Lekhara
          </Link>
          <nav className="nav" aria-label="Legal">
            <Link href="/legal/terms">Terms of service</Link>
            <Link href="/legal/privacy">Privacy notice</Link>
            <Link href="/legal/data-processing">Data processing terms</Link>
          </nav>
        </div>
      </header>
      <main className="main legal">
        {children}
        <Suspense fallback={null}>
          <Contact />
        </Suspense>
      </main>
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
