"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/projects", label: "Projects" },
  { href: "/rules", label: "Rules" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/projects") return pathname.startsWith("/projects") || pathname.startsWith("/withdrawals");
  return pathname.startsWith(href);
}

/** Main navigation without the current-page marker, shown while the page is still unknown. */
export function PlainNav() {
  return (
    <nav className="nav" aria-label="Main">
      {LINKS.map((link) => (
        <Link key={link.href} href={link.href}>
          {link.label}
        </Link>
      ))}
    </nav>
  );
}

export function Nav() {
  const pathname = usePathname();
  return (
    <nav className="nav" aria-label="Main">
      {LINKS.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          aria-current={isActive(pathname, link.href) ? "page" : undefined}
        >
          {link.label}
        </Link>
      ))}
    </nav>
  );
}

const TABS = [
  { segment: "", label: "Overview", team: false },
  { segment: "/escrow", label: "Escrow", team: false },
  { segment: "/tax", label: "Tax and statutory", team: true },
  { segment: "/units", label: "Units and landowners", team: true },
];

function tabsFor(team: boolean) {
  return TABS.filter((tab) => team || !tab.team);
}

export function ProjectTabs({ projectId, team }: { projectId: string; team: boolean }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  return (
    <nav className="tabs" aria-label="Project">
      {tabsFor(team).map((tab) => {
        const href = `${base}${tab.segment}`;
        return (
          <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}>
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function PlainProjectTabs({ projectId, team }: { projectId: string; team: boolean }) {
  const base = `/projects/${projectId}`;
  return (
    <nav className="tabs" aria-label="Project">
      {tabsFor(team).map((tab) => (
        <Link key={tab.segment} href={`${base}${tab.segment}`}>
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}
