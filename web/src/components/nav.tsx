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

/** The project's work, as tabs; then, quieter, where its records are kept and brought in.
 * `expanded` marks the business modules, left out of the main software's view. */
const TABS = [
  { segment: "", label: "Overview", team: false, data: false, expanded: false },
  { segment: "/escrow", label: "Escrow", team: false, data: false, expanded: false },
  { segment: "/collections", label: "Collections", team: true, data: false, expanded: true },
  { segment: "/handover", label: "Handover", team: true, data: false, expanded: false },
  { segment: "/disputes", label: "Disputes", team: true, data: false, expanded: false },
  { segment: "/tax", label: "Tax", team: true, data: false, expanded: false },
  { segment: "/krera", label: "K-RERA", team: true, data: false, expanded: false },
  { segment: "/documents", label: "Documents", team: true, data: false, expanded: false },
  { segment: "/units", label: "Units", team: true, data: true, expanded: true },
  { segment: "/suppliers", label: "Suppliers", team: true, data: true, expanded: true },
  { segment: "/budget", label: "Budget", team: true, data: true, expanded: true },
  { segment: "/approvals", label: "Approvals", team: true, data: true, expanded: false },
  { segment: "/import", label: "Import", team: true, data: true, expanded: false },
  { segment: "/setup", label: "Set-up", team: true, data: true, expanded: false },
];

type View = "main" | "expanded";

function tabsFor(team: boolean, view: View) {
  return TABS.filter((tab) => (team || !tab.team) && (view === "expanded" || !tab.expanded));
}

export function ProjectTabs({ projectId, team, view = "expanded" }: { projectId: string; team: boolean; view?: View }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const tabs = tabsFor(team, view);
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

export function PlainProjectTabs({ projectId, team, view = "expanded" }: { projectId: string; team: boolean; view?: View }) {
  const base = `/projects/${projectId}`;
  const tabs = tabsFor(team, view);
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
