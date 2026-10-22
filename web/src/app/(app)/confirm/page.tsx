import type { Metadata } from "next";
import { Suspense } from "react";

import { confirmIdentity } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { api } from "@/lib/api";

export const metadata: Metadata = { title: "Confirm it is you" };

export default function ConfirmPage({ searchParams }: PageProps<"/confirm">) {
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Confirm it is you</h1>
          <p>
            Downloading everything, changing who may do what, sharing documents outside the firm and turning on support ask
            for your password again when you signed in a while ago. It covers the next 15 minutes.
          </p>
        </div>
      </div>
      <Suspense fallback={null}>
        <ConfirmForm searchParams={searchParams} />
      </Suspense>
    </>
  );
}

async function ConfirmForm({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const next = typeof sp.next === "string" ? sp.next : "/";
  const me = await api.me();
  return (
    <div style={{ maxWidth: 420 }}>
      <ActionForm action={confirmIdentity.bind(null, next)} label="Confirm and go back" pendingLabel="Checking">
        <div className="field">
          <label htmlFor="confirm-password">Your password</label>
          <input id="confirm-password" name="password" type="password" autoComplete="current-password" required />
        </div>
        {me.two_step_on ? (
          <div className="field">
            <label htmlFor="confirm-code">The six-digit code from your app</label>
            <input id="confirm-code" name="code" inputMode="numeric" autoComplete="one-time-code" required />
          </div>
        ) : null}
      </ActionForm>
    </div>
  );
}
