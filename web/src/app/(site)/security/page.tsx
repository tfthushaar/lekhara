import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";

export const metadata: Metadata = {
  title: "Security",
  description: "How Lekhara keeps a builder's records safe: who can see them, how people sign in, files, sharing, support and records of who did what.",
};

const SECTIONS = [
  {
    title: "Your records stay yours",
    points: [
      "Each firm's records are kept apart from every other firm's twice over: by the application, and by the database itself, which shows a signed-in person only the rows of their own firm.",
      "Each person sees only what their role allows. Your architect, engineer and CA see only the certificates they sign.",
      "Lekhara reads your Tally and your bank statements and never changes them.",
    ],
  },
  {
    title: "Signing in",
    points: [
      "Sign in with a passkey (your phone's or laptop's fingerprint, face or PIN), which a fake sign-in page cannot use, or with a password and a six-digit code from an authenticator app. An owner can require two-step sign-in for the whole team.",
      "Downloading everything, changing who may do what and sharing outside the firm ask for your password again if you signed in a while ago.",
      "A session unused for 12 hours ends by itself. Settings lists every browser you are signed in on, and ends any of them.",
      "You get an email when someone signs in to your account from a new browser. Passwords already leaked in data breaches elsewhere are refused.",
    ],
  },
  {
    title: "Files",
    points: [
      "Every file uploaded, emailed in or sent by the Tally connector is checked for viruses.",
      "Spreadsheets are checked before they are opened, and the ones Lekhara gives you can never carry formulas from imported data.",
      "Emails that only claim to come from someone you trust are held until a person in your team allows them.",
    ],
  },
  {
    title: "Sharing outside the firm",
    points: [
      "Every certificate signed in Lekhara keeps a record of who signed it, when and from where, and a fingerprint of what they signed. Your bank can check it with the code on the certificate.",
      "Data rooms close on the date you choose, and can be withdrawn at any time.",
      "A room can ask each visitor for their name and email, confirmed with a code sent to that email, and records each document they open.",
      "Every page of a PDF opened from a room carries who opened it and when, so a copy passed on can be traced. Visitors can be asked to accept your confidentiality terms first, and their acceptance is kept.",
    ],
  },
  {
    title: "Our support",
    points: [
      "We see your workspace only if your owner or finance allows it, for a few days at a time. We can look but not change anything, and every page we open is in your access log.",
      "Your owner and finance are emailed when we open it, and can withdraw the permission at once.",
    ],
  },
  {
    title: "A record of who did what",
    points: [
      "Every sign-in, download, change to who may do what and visit by support is in an access log your owner can read, kept a year. Each entry is chained to the one before, so an entry changed or removed later shows.",
      "Every record keeps a history of who changed what, and when.",
    ],
  },
  {
    title: "Encryption and backups",
    points: [
      "Everything between your browser and Lekhara is encrypted, and browsers are told to use nothing else.",
      "Passwords are kept only as hashes. Statement passwords and authenticator secrets are sealed with a key kept apart from the database.",
      "Backups are encrypted, and checked piece by piece, with every document against its fingerprint, before they are restored.",
    ],
  },
  {
    title: "If something goes wrong",
    points: [
      "We have a written plan for security incidents. We report to CERT-In within six hours, as the law requires, and tell your firm within 24 hours, as our data processing terms promise.",
    ],
  },
];

export default function SecurityPage() {
  return (
    <>
      <section className="site-hero">
        <h1>How Lekhara keeps your records safe.</h1>
        <p className="site-lead">
          Builders keep their escrow, buyers&apos; payments, landowners&apos; shares and legal cases in Lekhara. This is what
          protects them, in plain words.
        </p>
      </section>
      <section className="site-section">
        <div className="site-grid site-grid-two">
          {SECTIONS.map((section) => (
            <div key={section.title} className="site-item">
              <h3>{section.title}</h3>
              <ul className="site-list">
                {section.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
      <section className="site-section">
        <h2>Found a weakness?</h2>
        <Suspense fallback={null}>
          <Report />
        </Suspense>
      </section>
    </>
  );
}

async function Report() {
  const info = await api.legal();
  return (
    <p className="site-note" style={{ color: "var(--ink-2)" }}>
      Write to <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a> with what you found and how to see it, and
      give us time to fix it before telling anyone else. See also our <Link href="/legal/privacy">privacy notice</Link> and{" "}
      <Link href="/legal/data-processing">data processing terms</Link>.
    </p>
  );
}
