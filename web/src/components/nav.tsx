"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { type PlaceTab, type View, groupsFor } from "@/lib/places";

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

type Tab = PlaceTab;

export function ProjectTabs({ projectId, team, view = "expanded", areas = [] }: { projectId: string; team: boolean; view?: View; areas?: string[] }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  const groups = groupsFor(team, view, areas);
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

export function PlainProjectTabs({ projectId, team, view = "expanded", areas = [] }: { projectId: string; team: boolean; view?: View; areas?: string[] }) {
  const base = `/projects/${projectId}`;
  return (
    <nav className="tabs" aria-label="Project">
      {groupsFor(team, view, areas).map((group) => (
        <Link key={group.label} href={`${base}${group.tabs[0].segment}`}>
          {group.label}
        </Link>
      ))}
    </nav>
  );
}
