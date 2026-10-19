import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Shipping and delivery" };

export default function DeliveryPage() {
  return (
    <Suspense fallback={<h1>Shipping and delivery</h1>}>
      <DeliveryBody />
    </Suspense>
  );
}

async function DeliveryBody() {
  const info = await api.legal();
  return (
    <article>
      <h1>Shipping and delivery</h1>
      <p>Lekhara is a service used online. Nothing is shipped.</p>

      <h2>When you can use it</h2>
      <ul>
        <li>{`The free month starts as soon as you sign up, and lasts ${info.trial_days} days.`}</li>
        <li>A subscription is active as soon as your payment is confirmed, usually at once.</li>
        <li>Your team, and the architects, engineers and CAs you invite, can use it as soon as they accept the invitation.</li>
      </ul>

      <h2>What you receive</h2>
      <ul>
        <li>Access to your firm&apos;s workspace, in a browser on a computer or phone.</li>
        <li>A GST invoice by email for every payment.</li>
        <li>
          If you choose, the Lekhara Connector, downloaded and installed on the computer with Tally. Nothing is posted to you.
        </li>
      </ul>

      <h2>If something has not arrived</h2>
      <p>
        If your subscription is not active within an hour of paying, or an invoice has not come, write to{" "}
        <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a> or see <Link href="/contact">how to reach us</Link>.
      </p>
    </article>
  );
}
