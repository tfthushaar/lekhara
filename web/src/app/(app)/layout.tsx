import Link from "next/link";
import { Suspense } from "react";

import { signOut } from "@/app/actions";
import { Nav, PlainNav } from "@/components/nav";
import { api } from "@/lib/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <Link href="/" className="wordmark">
            Horus
          </Link>
          <Suspense fallback={<PlainNav />}>
            <Nav />
          </Suspense>
          <Suspense fallback={null}>
            <UserMenu />
          </Suspense>
        </div>
      </header>
      <main className="main">{children}</main>
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
