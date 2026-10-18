import Link from "next/link";
import { Suspense } from "react";

import { acceptTerms, resendVerification, signOut } from "@/app/actions";
import { ActionForm } from "@/components/action-form";
import { Nav, PlainNav } from "@/components/nav";
import { api } from "@/lib/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="wordmark">
            Lekhara
          </Link>
          <Suspense fallback={<PlainNav />}>
            <Nav />
          </Suspense>
          <Suspense fallback={null}>
            <UserMenu />
          </Suspense>
        </div>
      </header>
      <Suspense fallback={null}>
        <Banners />
      </Suspense>
      <main className="main">{children}</main>
      <footer className="footer">
        <Link href="/legal/terms">Terms of service</Link>
        <Link href="/legal/privacy">Privacy notice</Link>
        <Link href="/legal/data-processing">Data processing terms</Link>
      </footer>
    </>
  );
}

async function Banners() {
  const me = await api.me();
  const org = me.organization;
  return (
    <>
      {!me.terms_accepted ? (
        <div className="banner banner-strong" role="status">
          <span>
            {"We have updated our "}
            <Link href="/legal/terms">terms of service</Link>
            {" and "}
            <Link href="/legal/privacy">privacy notice</Link>
            {". Please read them and accept to go on using Lekhara."}
          </span>
          <ActionForm action={acceptTerms} label="I accept" pendingLabel="Saving" secondary className="inline-form" />
        </div>
      ) : null}
      {org && org.delete_after ? (
        <div className="banner banner-strong" role="status">
          <span>{`This firm's account is closing: its data will be deleted after ${org.delete_after}. Download everything before then.`}</span>
          <Link href="/settings">Settings</Link>
        </div>
      ) : null}
      {org && org.access === "read_only" ? (
        <div className="banner banner-strong" role="status">
          <span>
            Your free month has ended. You can still see and export everything; subscribe to keep
            adding and changing data.
          </span>
          <Link href="/settings">Subscription</Link>
        </div>
      ) : null}
      {org && org.access === "trial" ? (
        <div className="banner">
          <span>{`Free month: ${org.days_left === 1 ? "1 day" : `${org.days_left} days`} left.`}</span>
          <Link href="/settings">Subscription</Link>
        </div>
      ) : null}
      {!me.email_verified ? (
        <div className="banner">
          <span>{`Confirm your email address with the link we sent to ${me.user.email}.`}</span>
          <ActionForm action={resendVerification} label="Send it again" pendingLabel="Sending" secondary className="inline-form" />
        </div>
      ) : null}
    </>
  );
}

async function UserMenu() {
  const me = await api.me();
  return (
    <div className="user-menu">
      <span className="org">
        {me.user.name}, {me.role_label}
      </span>
      <form action={signOut}>
        <button type="submit" className="link-button">
          Sign out
        </button>
      </form>
    </div>
  );
}
