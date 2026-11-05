"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Today" },
  { href: "/projects", label: "Projects" },
  { href: "/settings", label: "Settings" },
];

const IN_PROJECTS = ["/projects", "/withdrawals", "/units", "/leads", "/partners", "/bills", "/suppliers", "/cases", "/bank", "/gst", "/tally", "/imports"];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/review");
  if (href === "/projects") return IN_PROJECTS.some((start) => pathname.startsWith(start));
  if (href === "/settings") return pathname.startsWith("/settings") || pathname.startsWith("/rules");
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

type Tab = { segment: string; label: string; team: boolean; expanded: boolean };

/** A project's work, in the few places a builder would look for it. Each place opens on its
 * first page, with the rest beside it. `expanded` marks the business modules, left out of the
 * main software's view. */
const GROUPS: { label: string; tabs: Tab[] }[] = [
  { label: "Overview", tabs: [{ segment: "", label: "Overview", team: false, expanded: false }] },
  {
    label: "Buyers",
    tabs: [
      { segment: "/sales", label: "Leads and bookings", team: true, expanded: true },
      { segment: "/units", label: "Units", team: true, expanded: true },
      { segment: "/collections", label: "Payments", team: true, expanded: true },
      { segment: "/handover", label: "Handover", team: true, expanded: false },
      { segment: "/disputes", label: "Cases", team: true, expanded: false },
    ],
  },
  {
    label: "Money",
    tabs: [
      { segment: "/escrow", label: "RERA account", team: false, expanded: false },
      { segment: "/suppliers", label: "Suppliers", team: true, expanded: true },
      { segment: "/budget", label: "Budget", team: true, expanded: true },
    ],
  },
  {
    label: "Government",
    tabs: [
      { segment: "/krera", label: "K-RERA", team: true, expanded: false },
      { segment: "/tax", label: "Tax", team: true, expanded: false },
      { segment: "/approvals", label: "Approvals", team: true, expanded: false },
    ],
  },
  {
    label: "Files",
    tabs: [
      { segment: "/documents", label: "Documents", team: true, expanded: false },
      { segment: "/import", label: "Add files", team: true, expanded: false },
      { segment: "/setup", label: "Set-up", team: true, expanded: false },
    ],
  },
];

type View = "main" | "expanded";

function groupsFor(team: boolean, view: View) {
  return GROUPS.map((group) => ({
    label: group.label,
    tabs: group.tabs.filter((tab) => (team || !tab.team) && (view === "expanded" || !tab.expanded)),
  })).filter((group) => group.tabs.length > 0);
}

export function ProjectTabs({ projectId, team, view = "expanded" }: { projectId: string; team: boolean; view?: View }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const groups = groupsFor(team, view);
  const here = (tab: Tab) => (tab.segment ? pathname.startsWith(`${base}${tab.segment}`) : pathname === base);
  const current = groups.find((group) => group.tabs.some(here));
  return (
    <>
      <nav className="tabs" aria-label="Project">
        {groups.map((group) => (
          <Link key={group.label} href={`${base}${group.tabs[0].segment}`} aria-current={group === current ? "page" : undefined}>
            {group.label}
          </Link>
        ))}
      </nav>
      {current && current.tabs.length > 1 ? (
        <nav className="chips subtabs" aria-label={current.label}>
          {current.tabs.map((tab) => (
            <Link key={tab.segment} href={`${base}${tab.segment}`} className={`chip${here(tab) ? " chip-on" : ""}`} aria-current={here(tab) ? "page" : undefined}>
              {tab.label}
            </Link>
          ))}
        </nav>
      ) : null}
    </>
  );
}

export function PlainProjectTabs({ projectId, team, view = "expanded" }: { projectId: string; team: boolean; view?: View }) {
  const base = `/projects/${projectId}`;
  return (
    <nav className="tabs" aria-label="Project">
      {groupsFor(team, view).map((group) => (
        <Link key={group.label} href={`${base}${group.tabs[0].segment}`}>
          {group.label}
        </Link>
      ))}
    </nav>
  );
}
