import type { Metadata } from "next";
import Link from "next/link";

// Shown at "/" to anyone not signed in (see proxy.ts).
export const metadata: Metadata = {
  title: { absolute: "Lekhara: what your projects owe, worked out" },
  description:
    "What each project owes K-RERA, the escrow bank, the tax department, landowners and buyers, prepared from your own records. For builders in Karnataka.",
};

const ONLY = [
  {
    title: "What you can withdraw today",
    text: "From your RERA designated account, worked out from your costs. The architect's, engineer's and CA's certificates are drafted, checked against each other, and followed until the bank releases the money.",
  },
  {
    title: "K-RERA, on time",
    text: "Quarterly progress reports and the annual audit prepared from your records, with the figures for the portal and a pack for your CA. Delay interest is shown as it builds up.",
  },
  {
    title: "Tax traps, before they are bills",
    text: "The 80% registered-supplier test through the year, GST on development rights, sales below guidance value, TDS on payments to landowners, labour cess and the 45-day limit for MSME suppliers.",
  },
  {
    title: "Every unit registered",
    text: "Unit by unit, what stands between the buyer and registration, and the money waiting on it. Possession letters, and the handover to the residents' association, item by item.",
  },
  {
    title: "Complaints and orders",
    text: "Every K-RERA, consumer and civil case in one register, with hearings, deadlines and what each could cost. Orders worked out to the rupee, with the last day to appeal.",
  },
  {
    title: "Landowners' shares",
    text: "Each unit marked as yours or the landowner's, with entitlements, payments and TDS under each joint development agreement.",
  },
];

const SOURCES = [
  { title: "Tally", text: "Connect it once and your books come in every few minutes, or drop in an export." },
  { title: "Your bank", text: "Statements from any bank's net banking, matched to units, buyers and the RERA account." },
  { title: "Your sales sheet or CRM", text: "Excel, or exports from Sell.Do, LeadSquared, Zoho CRM, Salesforce and HubSpot." },
  { title: "Email", text: "Each project has its own address. Forward statements, bills and documents to it." },
  { title: "The GST portal", text: "Your GSTR-2B, checked against your suppliers' bills." },
  { title: "Anything else", text: "A template for every kind of record, or type it in. Change many records at once as a table." },
];

const STEPS = [
  "Sign up, add your firm from its GSTIN, and add each project from its K-RERA certificate.",
  "Bring in Tally, bank statements and your unit list. Each project shows what is missing and what it switches on.",
  "Today lists what needs you across every project, most urgent first.",
  "Your architect, engineer and CA review and sign from their own access. Nothing is filed, signed or paid without the person responsible.",
];

export default function HomePage() {
  return (
    <>
      <section className="site-hero">
        <h1>Everything your projects owe outside your accounts, worked out and ready before it is due.</h1>
        <p className="site-lead">
          Lekhara works out what each project owes K-RERA, the escrow bank, the tax department, landowners and buyers,
          prepares it from your own records, and tells you each morning what needs you. Built for builders in Karnataka.
        </p>
        <div className="site-actions">
          <Link href="/signup" className="button">
            Start your free month
          </Link>
          <Link href="/pricing" className="button button-secondary">
            See the price
          </Link>
        </div>
        <p className="small muted">Free for a month, with no card needed and nothing to install.</p>
      </section>

      <section className="site-section">
        <h2>What only Lekhara does</h2>
        <div className="site-grid">
          {ONLY.map((item) => (
            <div key={item.title} className="site-item">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="site-section">
        <h2>It starts from what you already have</h2>
        <div className="site-grid">
          {SOURCES.map((item) => (
            <div key={item.title} className="site-item">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
        <p className="site-note">
          Every import is shown to you before it is saved, and can be undone for 30 days. Every list exports to Excel, and
          your whole workspace in one step.
        </p>
      </section>

      <section className="site-section">
        <h2>How it works</h2>
        <ol className="site-steps">
          {STEPS.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>

      <section className="site-section site-two">
        <div>
          <h2>Your data</h2>
          <ul className="site-list">
            <li>Lekhara reads your systems and never changes them.</li>
            <li>Each person sees only what they need. Your CA sees only what they certify.</li>
            <li>Kept in India, with two-step sign-in and every file checked for viruses.</li>
            <li>Every sign-in and download is recorded in a log your owner can read.</li>
            <li>Take everything out at any time, in one step.</li>
          </ul>
        </div>
        <div>
          <h2>What Lekhara does not do</h2>
          <ul className="site-list">
            <li>It does not replace Tally.</li>
            <li>It never files, signs, submits or pays anything on its own.</li>
            <li>It does not run your site: no labour attendance or site diaries.</li>
          </ul>
        </div>
      </section>

      <section className="site-section site-close">
        <h2>Try it on your own projects</h2>
        <p>One subscription covers your whole firm. Your architect, engineer and CA join free.</p>
        <div className="site-actions">
          <Link href="/signup" className="button">
            Start your free month
          </Link>
          <Link href="/contact" className="button button-secondary">
            Talk to us
          </Link>
        </div>
      </section>
    </>
  );
}
