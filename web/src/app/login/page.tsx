import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { chooseView, signIn } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { PasskeySignIn } from "@/components/passkey-buttons";
import { demoAccounts } from "@/lib/api";
import { chosenView } from "@/lib/view";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage({ searchParams }: PageProps<"/login">) {
  return (
    <main className="login">
      <Link href="/" className="wordmark login-wordmark">
        Lekhara
      </Link>
      <Suspense fallback={null}>
        <DemoAccounts />
      </Suspense>
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

const VIEWS = {
  main: {
    title: "The main software",
    detail:
      "What only Lekhara does: the RERA account and its certificates, K-RERA filings, real-estate tax, registration and handover, buyer complaints and orders, and documents.",
  },
  expanded: {
    title: "The expanded software",
    detail:
      "The main software, plus the tools to run the firm if you have no ERP or CRM: units and buyers, collections from buyers, suppliers and their bills, and the budget. More are on the way.",
  },
} as const;

async function DemoAccounts() {
  const [demo, view] = await Promise.all([demoAccounts(), chosenView()]);
  if (!demo) return null;
  if (view === null) {
    return (
      <div className="login-card login-demo">
        <h2>Try the demo</h2>
        <p className="muted small" style={{ marginTop: 6, marginBottom: 16 }}>
          A made-up developer with three Bengaluru projects. Which would you like to see?{" "}
          <Link href="/welcome">Or read about Lekhara first.</Link>
        </p>
        <ul className="rows">
          {(["main", "expanded"] as const).map((v) => (
            <li key={v} className="demo-row">
              <div>
                <p className="row-title">{VIEWS[v].title}</p>
                <p className="row-detail">{VIEWS[v].detail}</p>
              </div>
              <form action={chooseView.bind(null, v, "/login")} className="demo-form">
                <button type="submit" className="button button-secondary">
                  Choose
                </button>
              </form>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  const other = view === "main" ? "expanded" : "main";
  return (
    <div className="login-card login-demo">
      <h2>Try the demo</h2>
      <p className="muted small" style={{ marginTop: 6, marginBottom: 16 }}>
        A made-up developer with three Bengaluru projects. Sign in as any of these people to see
        what they see, and try anything: the demo resets from time to time.
      </p>
      <p className="small" style={{ marginBottom: 16 }}>
        {`Showing ${VIEWS[view].title.toLowerCase()}. `}
        <button type="submit" form="switch-view" className="link-button">
          {`See ${VIEWS[other].title.toLowerCase()} instead`}
        </button>
      </p>
      <form id="switch-view" action={chooseView.bind(null, other, "/login")} hidden />
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
