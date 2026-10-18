import type { Metadata } from "next";
import Link from "next/link";

import { Suspense } from "react";

import { api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Terms of service" };

async function TermsBody() {
  const info = await api.legal();
  const us = info.company_name;
  return (
    <article>
      <h1>Terms of service</h1>
      <p className="muted">{`Version of ${day(info.version)}.`}</p>

      <h2>1. These terms</h2>
      <p>
        {`These terms are an agreement between ${us} ("we") and the firm that signs up for Lekhara ("your firm"). The person who signs up, or accepts an invitation, confirms they may accept them for the firm. Our `}
        <Link href="/legal/privacy">privacy notice</Link> and <Link href="/legal/data-processing">data processing terms</Link> are
        part of them.
      </p>

      <h2>2. What Lekhara does, and does not</h2>
      <p>
        Lekhara keeps your projects&apos; records, works out what they owe and are owed, and prepares filings, certificates,
        letters and packs. People sign; Lekhara prepares. Lekhara is not legal, tax or accounting advice. Certificates are
        given by your chartered accountant, architect and engineer under their own names, after they have checked them. Rates
        and rules marked &quot;to confirm&quot; must be confirmed by your advisers before you rely on them. You decide what to
        file, pay and sign, and remain responsible for it.
      </p>

      <h2>3. Your account</h2>
      <p>
        Keep your details accurate and your password to yourself. Your firm is responsible for the people it invites and what
        they do in Lekhara, and chooses what each may see and change.
      </p>

      <h2>4. The free month and the subscription</h2>
      <ul>
        <li>Your first month is free, with no payment details asked for.</li>
        <li>
          After that, one monthly subscription covers your whole firm. The price, with GST, is shown before you subscribe, and
          a GST invoice is issued for every payment.
        </li>
        <li>
          You pay by a mandate you set up yourself (UPI AutoPay, card or bank mandate). You are told before each payment is
          taken.
        </li>
        <li>
          You can cancel at any time in Settings, as easily as you subscribed. The subscription then ends at the end of the
          month already paid for; that month is not refunded.
        </li>
        <li>
          If the free month or the subscription ends unpaid, your firm&apos;s workspace becomes read-only: you can still see
          and export everything.
        </li>
      </ul>

      <h2>5. Your data</h2>
      <p>
        {`Your firm's data is yours. We use it only to provide Lekhara to your firm, as our data processing terms set out, and never sell it or use it to train AI models. You can download everything, with every document, at any time. If an owner closes your firm's account, its data is deleted ${info.close_after_days} days later, and from our backups within the following 30 days.`}
      </p>

      <h2>6. Fair use</h2>
      <p>
        Do not use Lekhara to break the law, to store anything you have no right to, to attack or overload it, or to copy it.
        Do not resell access to people outside your firm.
      </p>

      <h2>7. Other services</h2>
      <p>
        Lekhara reads what you bring from Tally, your banks, the GST portal and email. We are not responsible for mistakes in
        what those sources contain; Lekhara points out what it finds missing or inconsistent.
      </p>

      <h2>8. AI</h2>
      <p>
        Some features read documents with AI. What AI reads or drafts is marked as such, and counts only once a person in your
        firm has confirmed it. AI can be wrong; check it as you would a new colleague&apos;s work.
      </p>

      <h2>9. Availability and changes</h2>
      <p>
        We work to keep Lekhara available and tell you ahead of planned maintenance. We improve Lekhara over time. If we change
        these terms in a way that matters to you, we tell you at least 30 days ahead and ask you to accept the new version.
      </p>

      <h2>10. Liability</h2>
      <p>
        As far as the law allows, our total liability to your firm is limited to the subscription fees it paid in the twelve
        months before the claim, and we are not liable for indirect losses, or for penalties, interest or tax arising from what
        your firm files, pays or decides. Nothing in these terms limits liability that the law does not allow to be limited.
      </p>

      <h2>11. Suspension and ending</h2>
      <p>
        We may suspend access that breaks these terms or puts others at risk, and will tell you why. Either side may end the
        agreement; your firm by cancelling or closing its account, we with 30 days&apos; notice. Your right to export your data
        lasts until it is deleted.
      </p>

      <h2>12. Law and disputes</h2>
      <p>
        These terms are governed by the laws of India. Write to our grievance officer first; if a dispute is not settled within
        30 days, the courts at Bengaluru have jurisdiction.
      </p>
    </article>
  );
}

export default function TermsPage() {
  return (
    <Suspense fallback={<p className="loading">Loading the terms</p>}>
      <TermsBody />
    </Suspense>
  );
}
