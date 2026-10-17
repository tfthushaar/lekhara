import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { acceptInvitation } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { invitationInfo } from "@/lib/api";

export const metadata: Metadata = { title: "Your invitation", referrer: "no-referrer" };

export default function InvitePage({ params }: PageProps<"/invite/[token]">) {
  return (
    <main className="login">
      <p className="wordmark login-wordmark">Lekhara</p>
      <div className="login-card">
        <Suspense fallback={<p className="loading">Opening your invitation</p>}>
          <Invitation params={params} />
        </Suspense>
      </div>
    </main>
  );
}

async function Invitation({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const invite = await invitationInfo(token);
  if (invite === null) {
    return (
      <>
        <h1>This invitation has closed</h1>
        <p className="muted" style={{ marginTop: 6 }}>
          It has expired or has already been used. Ask the person who invited you to send a new one.
        </p>
        <p className="login-links">
          <Link href="/login">Sign in</Link>
        </p>
      </>
    );
  }
  return (
    <>
      <h1>Join {invite.firm}</h1>
      <p className="muted" style={{ marginTop: 6, marginBottom: 24 }}>
        You are invited as {invite.role_label.toLowerCase()}
        {invite.certifier && invite.projects.length ? ` for ${invite.projects.join(", ")}` : ""}.
        Lekhara is free for you; {invite.firm} holds the subscription.
      </p>
      <ActionForm
        action={acceptInvitation.bind(null, token)}
        label={invite.has_account ? "Sign in and join" : "Create my account and join"}
        pendingLabel="Joining"
      >
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" value={invite.email} readOnly />
        </div>
        {invite.has_account ? null : (
          <div className="field">
            <label htmlFor="name">Your name</label>
            <input id="name" name="name" autoComplete="name" required />
          </div>
        )}
        {invite.certifier ? (
          <div className="field">
            <label htmlFor="firm">Your firm, as it appears on your certificates</label>
            <input id="firm" name="firm" autoComplete="organization" />
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="password">
            {invite.has_account ? "Your Lekhara password" : "Choose a password (at least 10 characters)"}
          </label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={invite.has_account ? "current-password" : "new-password"}
            minLength={invite.has_account ? undefined : 10}
            required
          />
        </div>
      </ActionForm>
    </>
  );
}
