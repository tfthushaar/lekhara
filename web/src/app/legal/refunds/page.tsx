import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Cancellation and refunds" };

export default function RefundsPage() {
  return (
    <Suspense fallback={<h1>Cancellation and refunds</h1>}>
      <RefundsBody />
    </Suspense>
  );
}

async function RefundsBody() {
  const info = await api.legal();
  return (
    <article>
      <h1>Cancellation and refunds</h1>
      <p>
        {`This is how cancelling a Lekhara subscription works, and when ${info.company_name} refunds a payment.`}
      </p>

      <h2>The free month</h2>
      <p>
        {`The first ${info.trial_days} days are free and no card is asked for, so there is nothing to cancel or refund. If your firm does not subscribe, its workspace becomes read-only, and everything in it can still be seen and downloaded.`}
      </p>

      <h2>Paying monthly</h2>
      <ul>
        <li>The subscription renews each month until it is cancelled.</li>
        <li>
          An owner can cancel at any time. Lekhara stays fully usable to the end of the month already paid for, and nothing
          more is charged.
        </li>
        <li>The month in progress is not refunded in part.</li>
      </ul>

      <h2>Paying yearly</h2>
      <ul>
        <li>{`A year costs the price of ${info.months_charged_per_year} months.`}</li>
        <li>
          On cancelling, Lekhara stays usable to the end of the month in progress, and every whole month left in the year is
          refunded, at the yearly rate.
        </li>
      </ul>

      <h2>Payments taken in error</h2>
      <p>A payment taken twice, or taken after the subscription was cancelled, is refunded in full.</p>

      <h2>How refunds are paid</h2>
      <p>
        To the card, UPI account or bank account the payment came from, within 7 working days of the cancellation or of
        our agreeing the refund, with a GST credit note. Your bank may take a few more days to show it.
      </p>

      <h2>After cancelling</h2>
      <p>
        {`The workspace becomes read-only when the paid period ends, and everything in it can still be downloaded. An owner can close the firm's account instead: everything then stays ready to download for ${info.close_after_days} days, and is then deleted.`}
      </p>

      <h2>To cancel or ask for a refund</h2>
      <p>
        Write to <a href={`mailto:${info.contact_email}`}>{info.contact_email}</a> from the owner&apos;s email address, or
        see <Link href="/contact">how to reach us</Link>.
      </p>
    </article>
  );
}
