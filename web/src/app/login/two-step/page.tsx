import type { Metadata } from "next";
import Link from "next/link";

import { signInCode } from "@/app/actions";
import { ActionForm } from "@/components/action-form";

export const metadata: Metadata = { title: "Sign in" };

export default function TwoStepPage() {
  return (
    <main className="login">
      <Link href="/" className="wordmark login-wordmark">
        Lekhara
      </Link>
      <div className="login-card">
        <h1>The code from your app</h1>
        <p className="muted" style={{ marginTop: 6, marginBottom: 24 }}>
          Open your authenticator app and enter the six-digit code it shows for Lekhara. Lost your phone? Enter one of
          your recovery codes instead.
        </p>
        <ActionForm action={signInCode} label="Sign in" pendingLabel="Checking">
          <div className="field">
            <label htmlFor="code">Code</label>
            <input id="code" name="code" inputMode="numeric" autoComplete="one-time-code" autoFocus required />
          </div>
        </ActionForm>
        <p className="login-links">
          <Link href="/login">Start again</Link>
        </p>
      </div>
    </main>
  );
}
