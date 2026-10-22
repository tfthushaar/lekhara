import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { confirmTwoStep, startTwoStep } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Set up two-step sign-in" };

/** Where someone lands when their firm requires two-step sign-in and they have not set it up. */
export default function SecurePage() {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Set up two-step sign-in</h1>
          <p>
            Your firm asks everyone to sign in with a six-digit code from an authenticator app on their phone, as well as
            their password. It takes a minute, and then Lekhara opens as usual.
          </p>
        </div>
      </div>
      <Suspense fallback={null}>
        <Steps />
      </Suspense>
    </>
  );
}

async function Steps() {
  const me = await api.me();
  if (!me.two_step_needed) {
    return (
      <p>
        Two-step sign-in is on. <Link href="/">Go to Today</Link>
      </p>
    );
  }
  return (
    <div style={{ maxWidth: 640 }}>
      <ol className="small" style={{ paddingLeft: 18, marginBottom: 16 }}>
        <li>Install Google Authenticator, Microsoft Authenticator or any authenticator app on your phone.</li>
        <li>Press Set it up, and add the key shown to the app.</li>
        <li>Enter the six-digit code the app shows, and keep the recovery codes somewhere safe.</li>
      </ol>
      <ActionForm action={startTwoStep} label="Set it up" pendingLabel="Starting" secondary />
      <ActionForm action={confirmTwoStep} label="Turn it on" pendingLabel="Checking">
        <div className="field" style={{ maxWidth: 360 }}>
          <label htmlFor="secure-code">The six-digit code from your app</label>
          <input id="secure-code" name="code" inputMode="numeric" autoComplete="one-time-code" required />
        </div>
      </ActionForm>
      <p className="small" style={{ marginTop: 16 }}>
        Once it is on, <Link href="/">go to Today</Link>.
      </p>
    </div>
  );
}
