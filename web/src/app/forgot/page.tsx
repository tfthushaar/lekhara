import type { Metadata } from "next";
import Link from "next/link";

import { forgotPassword } from "@/app/actions";
import { ActionForm } from "@/components/action-form";

export const metadata: Metadata = { title: "Reset your password" };

export default function ForgotPage() {
  return (
    <main className="login">
      <p className="wordmark login-wordmark">Lekhara</p>
      <div className="login-card">
        <h1>Reset your password</h1>
        <p className="muted" style={{ marginTop: 6, marginBottom: 24 }}>
          Enter the email you sign in with. We will send a link to set a new password.
        </p>
        <ActionForm action={forgotPassword} label="Send the link" pendingLabel="Sending">
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" autoComplete="email" required />
          </div>
        </ActionForm>
        <p className="login-links">
          <Link href="/login">Back to sign in</Link>
        </p>
      </div>
    </main>
  );
}
