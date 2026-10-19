import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";
import { inrFull } from "@/lib/format";

export const metadata: Metadata = {
  title: "Pricing",
  description: "One subscription for your whole firm: every project and everyone on your team. Free for the first month.",
};

const INCLUDED = [
  "Escrow withdrawals, with the architect's, engineer's and CA's certificates",
  "K-RERA deadlines, quarterly report figures and annual audit packs",
  "The real-estate tax checks: the 80% test, development rights, guidance value, TDS, labour cess, MSME",
  "Collections: payment plans, demand letters and the 70% deposit check",
  "Registration, possession letters and the handover to the residents' association",
  "Disputes, hearings and orders",
  "Landowners and joint development agreements",
  "Suppliers, bills and work orders",
  "Approvals, with reminders before they lapse",
  "The document vault, and data rooms for lenders",
  "Imports from Tally, bank statements, your CRM and the GST portal, and the Tally connector",
  "Every list in Excel, and your whole workspace in one download",
];

export default function PricingPage() {
  return (
    <>
      <section className="site-hero">
        <h1>One subscription for your whole firm.</h1>
        <p className="site-lead">Every project and everyone on your team. Your architect, engineer and CA join free.</p>
        <Suspense fallback={<div className="site-price" />}>
          <Price />
        </Suspense>
      </section>

      <section className="site-section">
        <h2>Everything is included</h2>
        <ul className="site-list site-list-two">
          {INCLUDED.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="site-section">
        <h2>How paying works</h2>
        <dl className="site-terms">
          <dt>Your first month</dt>
          <dd>Free, with everything in it. No card is needed to start.</dd>
          <dt>After that</dt>
          <dd>Pay monthly by UPI AutoPay, card or bank mandate. Every payment comes with a GST invoice.</dd>
          <dt>Cancelling</dt>
          <dd>
            Cancel at any time. You keep using Lekhara to the end of the month you have paid for.{" "}
            <Link href="/legal/refunds">Cancellation and refunds</Link>
          </dd>
          <dt>If a payment stops</dt>
          <dd>Your workspace becomes read-only. You can still see and download everything in it.</dd>
          <dt>Leaving</dt>
          <dd>Close your firm&apos;s account and everything stays ready to download for 30 days. Then it is deleted.</dd>
        </dl>
      </section>
    </>
  );
}

async function Price() {
  const info = await api.legal();
  const monthly = info.price_per_month;
  return (
    <div className="site-price">
      {monthly ? (
        <>
          <p className="site-amount">
            {inrFull(String(monthly))}
            <span> a month, plus GST</span>
          </p>
          <p className="muted">
            {`Or pay yearly, twelve months for the price of ${info.months_charged_per_year}: ${inrFull(
              String(monthly * info.months_charged_per_year),
            )} a year, plus GST.`}
          </p>
        </>
      ) : (
        <p className="site-amount-pending">
          We are setting the price with our first builders. <Link href="/contact">Write to us</Link> for yours.
        </p>
      )}
      <div className="site-actions">
        <Link href="/signup" className="button">
          Start your free month
        </Link>
      </div>
      <p className="small muted">{`Free for ${info.trial_days} days. No card needed.`}</p>
    </div>
  );
}
