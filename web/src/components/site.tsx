import Link from "next/link";
import { Suspense } from "react";

import { LinkRow, type SiteLink } from "@/components/site-nav";

const SITE: SiteLink[] = [
  { href: "/pricing", label: "Pricing" },
  { href: "/contact", label: "Contact" },
];

export const POLICIES: SiteLink[] = [
  { href: "/legal/terms", label: "Terms of service" },
  { href: "/legal/privacy", label: "Privacy notice" },
  { href: "/legal/data-processing", label: "Data processing terms" },
  { href: "/legal/refunds", label: "Cancellation and refunds" },
  { href: "/legal/delivery", label: "Shipping and delivery" },
];

/** The public website's header: what Lekhara is, its price, how to reach us, and the way in. */
export function SiteHeader() {
  return (
    <header className="topbar">
      <div className="topbar-inner">
        <Link href="/" className="wordmark">
          Lekhara
        </Link>
        <Suspense fallback={<LinkRow links={SITE} label="Lekhara" className="nav" plain />}>
          <LinkRow links={SITE} label="Lekhara" className="nav" />
        </Suspense>
        <div className="site-way-in">
          <Link href="/login" className="link-action">
            Sign in
          </Link>
          <Link href="/signup" className="button site-start">
            Start your free month
          </Link>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="footer">
      {[...SITE, ...POLICIES].map((link) => (
        <Link key={link.href} href={link.href}>
          {link.label}
        </Link>
      ))}
    </footer>
  );
}
