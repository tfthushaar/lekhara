import type { Metadata } from "next";
import Link from "next/link";

import { Suspense } from "react";

import { api } from "@/lib/api";
import { day } from "@/lib/format";

export const metadata: Metadata = { title: "Privacy notice" };

async function PrivacyBody() {
  const info = await api.legal();
  return (
    <article>
      <h1>Privacy notice</h1>
      <p className="muted">{`Version of ${day(info.version)}.`}</p>
      <p>
        {`This notice says what personal data ${info.company_name} keeps about the people who use Lekhara (your firm's team, the architects, engineers and chartered accountants you invite, and people who open a data room you share), why, and what you can do about it. It follows India's Digital Personal Data Protection Act, 2023.`}
      </p>

      <h2>What we keep</h2>
      <ul>
        <li>Your account: name, email, phone if given, firm and role.</li>
        <li>
          {`Sign-ins and important actions (exports, downloads, changes to who may do what), with the address and browser they came from: the access log, kept for ${info.log_days} days because India's cyber security rules require at least 180.`}
        </li>
        <li>What you change in Lekhara, kept in each record&apos;s history.</li>
        <li>Emails sent to a project&apos;s Lekhara address, and the files in them.</li>
        <li>Your firm&apos;s subscription. Card and bank details are handled by Razorpay, never by us.</li>
      </ul>

      <h2>Why</h2>
      <p>
        To provide Lekhara to your firm, to keep it secure, to meet our legal duties, to bill your firm and to write to you about
        your account. We do not sell personal data, show advertising, or use your data to train AI models.
      </p>

      <h2>Your buyers&apos; and landowners&apos; data</h2>
      <p>
        Personal data your firm puts into Lekhara about its buyers, landowners and suppliers belongs to your firm, which decides
        how it is used. We handle it only on your firm&apos;s behalf, under our <Link href="/legal/data-processing">data
        processing terms</Link>. Buyers and landowners should contact the builder about it.
      </p>

      <h2>Who else sees it</h2>
      <ul>
        {info.sub_processors.map((s) => (
          <li key={s.what}>{`${s.what}: ${s.who}.`}</li>
        ))}
        <li>Authorities, when the law requires us to disclose it.</li>
      </ul>

      <h2>Where</h2>
      <p>
        In India. AI document reading runs in India too unless your firm chooses otherwise; if it does, we say which provider
        and where before anything is sent.
      </p>

      <h2>How long</h2>
      <p>
        {`While your account is open. When you delete your account, your details are taken out and the records you made stay under "A former user". When your firm's account is closed, its data is deleted ${info.close_after_days} days later. Invoices and the records tax law requires are kept for as long as it requires (currently up to eight years).`}
      </p>

      <h2>Your rights</h2>
      <p>
        You can see and correct your details in Settings, delete your account there, ask us what we hold about you, withdraw
        consent, name someone to act for you, and complain to our grievance officer (below), and then to the Data Protection
        Board of India. Lekhara is not meant for anyone under 18.
      </p>

      <h2>Changes</h2>
      <p>If this notice changes in a way that matters to you, we tell you and ask you to read it again.</p>
    </article>
  );
}

export default function PrivacyPage() {
  return (
    <Suspense fallback={<p className="loading">Loading the privacy notice</p>}>
      <PrivacyBody />
    </Suspense>
  );
}
