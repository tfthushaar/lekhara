import type { Metadata } from "next";
import Link from "next/link";

// Shown at "/" to anyone not signed in (see proxy.ts).
export const metadata: Metadata = {
  title: { absolute: "Lekhara: if you can use WhatsApp, you can use Lekhara" },
  description:
    "Easy software for builders in Karnataka. It tells you what to do today on each project, and does the paperwork for K-RERA, the RERA account, tax, buyers and handovers.",
};

const EASY = [
  {
    title: "It tells you what to do",
    text: "Open it and you see a list of what needs doing today. Each line has one button that does it.",
  },
  {
    title: "One box for every file",
    text: "Tally export, bank statement, GST return, Excel sheet, PDF. Put it in the box and we work out what it is.",
  },
  {
    title: "Your office can start today",
    text: "No training and no computer person needed. Add a project by uploading its K-RERA certificate.",
  },
  {
    title: "Works on your phone",
    text: "See what is late from the site. Tap to call a buyer, and note what they said in one line.",
  },
  {
    title: "Plain words",
    text: "We say what you would say to your CA. Where a legal term can't be avoided, we explain it next to it.",
  },
  {
    title: "You can't break anything",
    text: "You see every file before it is saved, and you can undo it for 30 days.",
  },
];

const LOOKS_AFTER = [
  { title: "Your RERA account", text: "How much you can draw today, with the architect's, engineer's and CA's certificates filled in for you." },
  { title: "K-RERA", text: "Quarterly reports and the annual audit, ready before they are due." },
  { title: "Tax", text: "GST, TDS, labour cess and guidance value, watched through the year so nothing turns into a bill." },
  { title: "Buyers", text: "Leads, site visits, cost sheets, bookings, payments and demand letters, all in one place." },
  { title: "Handover", text: "What is holding up each unit's registration, and the money waiting on it." },
  { title: "Complaints", text: "Every K-RERA, consumer and civil case, with hearing dates and what each could cost." },
];

const STEPS = [
  "Sign up and upload your project's K-RERA certificate.",
  "Add your Tally file, bank statement and list of units.",
  "Open Lekhara each morning and do what it says.",
];

export default function HomePage() {
  return (
    <>
      <section className="site-hero">
        <h1>If you can use WhatsApp, you can use Lekhara.</h1>
        <p className="site-lead">
          It tells you what to do today on each project and does the paperwork for it: K-RERA, the RERA account, tax, buyers
          and handovers. Made for builders in Karnataka, and for offices that have never used software like this.
        </p>
        <div className="site-actions">
          <Link href="/signup" className="button">
            Start your free month
          </Link>
          <Link href="/pricing" className="button button-secondary">
            See the price
          </Link>
        </div>
        <p className="small muted">Free for a month. No card, nothing to install, no training.</p>
      </section>

      <section className="site-section">
        <h2>Easy from the first day</h2>
        <div className="site-grid">
          {EASY.map((item) => (
            <div key={item.title} className="site-item">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="site-section">
        <h2>Three steps</h2>
        <ol className="site-steps">
          {STEPS.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </section>

      <section className="site-section">
        <h2>What it looks after</h2>
        <div className="site-grid">
          {LOOKS_AFTER.map((item) => (
            <div key={item.title} className="site-item">
              <h3>{item.title}</h3>
              <p>{item.text}</p>
            </div>
          ))}
        </div>
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
