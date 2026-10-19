"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export type SiteLink = { href: string; label: string };

/** Links that mark the page you are on. `plain` leaves the marker out, while the page is unknown. */
export function LinkRow({ links, label, className, plain = false }: { links: SiteLink[]; label: string; className: string; plain?: boolean }) {
  return (
    <nav className={className} aria-label={label}>
      {links.map((link) => (plain ? <Link key={link.href} href={link.href}>{link.label}</Link> : <Marked key={link.href} {...link} />))}
    </nav>
  );
}

function Marked({ href, label }: SiteLink) {
  const pathname = usePathname();
  return (
    <Link href={href} aria-current={pathname === href ? "page" : undefined}>
      {label}
    </Link>
  );
}
