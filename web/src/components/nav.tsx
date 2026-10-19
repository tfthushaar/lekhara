"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/projects", label: "Projects" },
  { href: "/review", label: "To review" },
  { href: "/rules", label: "Rules" },
  { href: "/settings", label: "Settings" },
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

/** The project's work, as tabs; then, quieter, where its records are kept and brought in. */
const TABS = [
  { segment: "", label: "Overview", team: false, data: false },
  { segment: "/escrow", label: "Escrow", team: false, data: false },
  { segment: "/collections", label: "Collections", team: true, data: false },
  { segment: "/handover", label: "Handover", team: true, data: false },
  { segment: "/disputes", label: "Disputes", team: true, data: false },
  { segment: "/tax", label: "Tax", team: true, data: false },
  { segment: "/krera", label: "K-RERA", team: true, data: false },
  { segment: "/documents", label: "Documents", team: true, data: false },
  { segment: "/units", label: "Units", team: true, data: true },
  { segment: "/suppliers", label: "Suppliers", team: true, data: true },
  { segment: "/budget", label: "Budget", team: true, data: true },
  { segment: "/approvals", label: "Approvals", team: true, data: true },
  { segment: "/import", label: "Import", team: true, data: true },
  { segment: "/setup", label: "Set-up", team: true, data: true },
];

function tabsFor(team: boolean) {
  return TABS.filter((tab) => team || !tab.team);
}

export function ProjectTabs({ projectId, team }: { projectId: string; team: boolean }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const tabs = tabsFor(team);
  const link = (tab: (typeof TABS)[number]) => {
    const href = `${base}${tab.segment}`;
    return (
      <Link key={href} href={href} className={tab.data ? "tab-quiet" : undefined} aria-current={pathname === href ? "page" : undefined}>
        {tab.label}
      </Link>
    );
  };
  return (
    <nav className="tabs" aria-label="Project">
      {tabs.filter((t) => !t.data).map(link)}
      <span className="tabs-gap" />
      {tabs.filter((t) => t.data).map(link)}
    </nav>
  );
}

export function PlainProjectTabs({ projectId, team }: { projectId: string; team: boolean }) {
  const base = `/projects/${projectId}`;
  const tabs = tabsFor(team);
  return (
    <nav className="tabs" aria-label="Project">
      {tabs
        .filter((t) => !t.data)
        .map((tab) => (
          <Link key={tab.segment} href={`${base}${tab.segment}`}>
            {tab.label}
          </Link>
        ))}
      <span className="tabs-gap" />
      {tabs
        .filter((t) => t.data)
        .map((tab) => (
          <Link key={tab.segment} href={`${base}${tab.segment}`} className="tab-quiet">
            {tab.label}
          </Link>
        ))}
    </nav>
  );
}
