import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { verifyEmail } from "@/app/actions";
import { ActionForm } from "@/components/action-form";

export const metadata: Metadata = { title: "Confirm your email", referrer: "no-referrer" };

export default function VerifyPage({ params }: PageProps<"/verify/[token]">) {
  return (
    <main className="login">
      <p className="wordmark login-wordmark">Lekhara</p>
      <div className="login-card">
        <h1>Confirm your email</h1>
        <p className="muted" style={{ marginTop: 6, marginBottom: 24 }}>
          One click, so that reminders and password resets reach you.
        </p>
        <Suspense fallback={null}>
          <VerifyForm params={params} />
        </Suspense>
        <p className="login-links">
          <Link href="/">Go to Lekhara</Link>
        </p>
      </div>
    </main>
  );
}

async function VerifyForm({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <ActionForm action={verifyEmail.bind(null, token)} label="Confirm my email" pendingLabel="Confirming" />;
}
