import type { Metadata } from "next";

import { Suspense } from "react";

import { api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Data processing terms" };

async function DataProcessingBody() {
  const info = await api.legal();
  const us = info.company_name;
  return (
    <article>
      <h1>Data processing terms</h1>
      <p className="muted">{`Version of ${day(info.version)}. Part of the terms of service.`}</p>
      <p>
        {`These terms cover personal data your firm puts into Lekhara about other people: buyers, landowners, suppliers' contacts, tenants and anyone else in your records. For that data your firm is the data fiduciary and ${us} is its data processor, under India's Digital Personal Data Protection Act, 2023.`}
      </p>

      <h2>1. Only on your instructions</h2>
      <p>
        We process it only to provide Lekhara to your firm, as your firm uses and sets it up, and for nothing of our own. Our
        people who can reach it are bound to keep it confidential, and reach it only when needed to run or support Lekhara.
      </p>

      <h2>2. Security</h2>
      <p>
        We keep it with reasonable security safeguards: encryption in transit and at rest, access limited by role, passwords
        stored only as hashes, secrets sealed, an access log, and backups.
      </p>

      <h2>3. Who else handles it</h2>
      <ul>
        {info.sub_processors.map((s) => (
          <li key={s.what}>{`${s.what}: ${s.who}.`}</li>
        ))}
      </ul>
      <p>
        Each is bound to the same duties. We tell your firm 30 days before adding another, and your firm may object or end the
        agreement.
      </p>

      <h2>4. Where</h2>
      <p>In India, unless your firm chooses otherwise for AI document reading.</p>

      <h2>5. If something goes wrong</h2>
      <p>
        We tell your firm of a personal data breach without delay, and within 24 hours of becoming aware of it, with what we know,
        so that your firm can tell the Data Protection Board and the people affected. We help with those notices, report to
        CERT-In as the law requires, and keep a record of every incident.
      </p>

      <h2>6. Requests from the people concerned</h2>
      <p>
        If a buyer or landowner asks your firm to see, correct or erase their data, Lekhara lets your firm do so, and we help
        where it cannot. If they write to us, we pass the request to your firm.
      </p>

      <h2>7. When the subscription ends</h2>
      <p>
        {`Your firm can download everything at any time. When its account is closed, the data is deleted ${info.close_after_days} days later, and from backups within the following 30 days, except what the law requires us to keep.`}
      </p>

      <h2>8. Showing compliance</h2>
      <p>
        We give your firm the information it reasonably needs to show that these terms are kept, and allow an audit once a
        year on reasonable notice.
      </p>

      <h2>9. Your firm&apos;s part</h2>
      <p>
        Your firm makes sure it may collect and use the data it puts in, gives the people concerned the notices the law asks
        for, and puts in only what it needs.
      </p>
    </article>
  );
}

export default function DataProcessingPage() {
  return (
    <Suspense fallback={<p className="loading">Loading the data processing terms</p>}>
      <DataProcessingBody />
    </Suspense>
  );
}
