import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { resetPassword } from "@/app/actions";
import { ActionForm } from "@/components/action-form";

export const metadata: Metadata = { title: "Set a new password", referrer: "no-referrer" };

export default function ResetPage({ params }: PageProps<"/reset/[token]">) {
  return (
    <main className="login">
      <p className="wordmark login-wordmark">Lekhara</p>
      <div className="login-card">
        <h1>Set a new password</h1>
        <p className="muted" style={{ marginTop: 6, marginBottom: 24 }}>
          You will be signed out everywhere else.
        </p>
        <Suspense fallback={null}>
          <ResetForm params={params} />
        </Suspense>
        <p className="login-links">
          <Link href="/forgot">Ask for a new link</Link>
        </p>
      </div>
    </main>
  );
}

async function ResetForm({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <ActionForm action={resetPassword.bind(null, token)} label="Save the new password" pendingLabel="Saving">
      <div className="field">
        <label htmlFor="password">New password (at least 10 characters)</label>
        <input id="password" name="password" type="password" autoComplete="new-password" minLength={10} required />
      </div>
      <div className="field">
        <label htmlFor="confirm">The same again</label>
        <input id="confirm" name="confirm" type="password" autoComplete="new-password" minLength={10} required />
      </div>
    </ActionForm>
  );
}
