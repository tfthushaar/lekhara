import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { signIn } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { PasskeySignIn } from "@/components/passkey-buttons";
import { demoAccounts } from "@/lib/api";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <main className="login">
      <Link href="/" className="wordmark login-wordmark">
        Lekhara
      </Link>
      <div className="login-card">
        <h1>Sign in</h1>
        <Suspense fallback={null}>
          <ResetNotice searchParams={searchParams} />
        </Suspense>
        <p className="muted" style={{ marginTop: 6, marginBottom: 24 }}>
          For developers, and for the architects, engineers and CAs who certify their projects.
        </p>
        <ActionForm action={signIn} label="Sign in" pendingLabel="Signing in">
          <div className="field">
            <label htmlFor="email">Email</label>
            <input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </div>
        </ActionForm>
        <PasskeySignIn />
        <p className="login-links">
          <Link href="/signup">New to Lekhara? Start your free month</Link>
          <Link href="/forgot">Forgot your password?</Link>
        </p>
      </div>
      <Suspense fallback={null}>
        <DemoAccounts />
      </Suspense>
    </main>
  );
}

async function ResetNotice({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  if (sp.reset !== "1") return null;
  return (
    <p className="form-ok" role="status" style={{ marginTop: 12 }}>
      Your password has been changed. Sign in with the new one.
    </p>
  );
}

async function DemoAccounts() {
  const demo = await demoAccounts();
  if (!demo) return null;
  return (
    <div className="login-card login-demo">
      <h2>Try the demo</h2>
      <p className="muted small" style={{ marginTop: 6, marginBottom: 16 }}>
        A fictional developer with three Bengaluru projects. Sign in as any of these people to see
        what they see.
      </p>
      <ul className="rows">
        {demo.accounts.map((account) => (
          <li key={account.email} className="demo-row">
            <div>
              <p className="row-title">{account.label}</p>
              <p className="row-detail">
                {account.name}, {account.email}
              </p>
            </div>
            <ActionForm
              action={signIn}
              label="Sign in"
              pendingLabel="Signing in"
              secondary
              className="demo-form"
            >
              <input type="hidden" name="email" value={account.email} />
              <input type="hidden" name="password" value={demo.password} />
            </ActionForm>
          </li>
        ))}
      </ul>
    </div>
  );
}
