import type { Metadata } from "next";
import Link from "next/link";

import { signUp } from "@/app/actions";
import { ActionForm } from "@/components/action-form";

export const metadata: Metadata = { title: "Start your free month" };

export default function SignupPage() {
  return (
    <main className="login">
      <p className="wordmark login-wordmark">Lekhara</p>
      <div className="login-card">
        <h1>Start your free month</h1>
        <p className="muted" style={{ marginTop: 6, marginBottom: 24 }}>
          One subscription covers your whole firm: every project and everyone on your team. Use it
          free for a month on your own projects. No card needed to start.
        </p>
        <ActionForm action={signUp} label="Create my account" pendingLabel="Setting up your workspace">
          <div className="field">
            <label htmlFor="name">Your name</label>
            <input id="name" name="name" autoComplete="name" required />
          </div>
          <div className="field">
            <label htmlFor="firm">Your firm</label>
            <input id="firm" name="firm" autoComplete="organization" required placeholder="As your buyers know it" />
          </div>
          <div className="field">
            <label htmlFor="email">Work email</label>
            <input id="email" name="email" type="email" autoComplete="email" required />
          </div>
          <div className="field">
            <label htmlFor="password">Password (at least 10 characters)</label>
            <input id="password" name="password" type="password" autoComplete="new-password" minLength={10} required />
          </div>
        </ActionForm>
        <p className="login-links">
          <span>
            Already have an account? <Link href="/login">Sign in</Link>
          </span>
        </p>
      </div>
    </main>
  );
}
