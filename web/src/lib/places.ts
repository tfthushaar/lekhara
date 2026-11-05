// A project's places and which of them a role works in. Shared by the navigation and by
// server pages that send a person to their own work.

export type PlaceTab = { segment: string; label: string; team: boolean; expanded: boolean };

/** A project's work, in the few places a builder would look for it. Each place opens on its
 * first page, with the rest beside it. `expanded` marks the business modules, left out of the
 * main software's view. Each person sees only the pages their role works in (`areas`, from the
 * API); a place left with one page takes that page's name. */
const GROUPS: { label: string; tabs: PlaceTab[] }[] = [
  { label: "Overview", tabs: [{ segment: "", label: "Overview", team: false, expanded: false }] },
  {
    label: "Buyers",
    tabs: [
      { segment: "/sales", label: "Leads and bookings", team: true, expanded: true },
      { segment: "/units", label: "Units", team: true, expanded: true },
      { segment: "/collections", label: "Payments", team: true, expanded: true },
      { segment: "/handover", label: "Handover", team: true, expanded: false },
      { segment: "/issues", label: "After handover", team: true, expanded: true },
      { segment: "/disputes", label: "Cases", team: true, expanded: false },
    ],
  },
  {
    label: "Money",
    tabs: [
      { segment: "/escrow", label: "RERA account", team: false, expanded: false },
      { segment: "/contractors", label: "Contractors", team: true, expanded: true },
      { segment: "/suppliers", label: "Suppliers", team: true, expanded: true },
      { segment: "/budget", label: "Budget", team: true, expanded: true },
      { segment: "/cash", label: "Cash and loans", team: true, expanded: true },
    ],
  },
  {
    label: "Site",
    tabs: [
      { segment: "/site", label: "Daily report", team: true, expanded: true },
      { segment: "/materials", label: "Materials", team: true, expanded: true },
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

export type View = "main" | "expanded";

const area = (tab: PlaceTab) => tab.segment.slice(1) || "overview";

export function groupsFor(team: boolean, view: View, areas: string[] = []) {
  const groups = GROUPS.map((group) => {
    const tabs = group.tabs.filter(
      (tab) => (team || !tab.team) && (view === "expanded" || !tab.expanded) && (!areas.length || areas.includes(area(tab))),
    );
    return { label: tabs.length === 1 ? tabs[0].label : group.label, tabs };
  }).filter((group) => group.tabs.length > 0);
  if (!areas.length || areas.includes("overview")) return groups;
  // A working role: its main work (the first of its areas) comes first.
  const rank = (g: (typeof groups)[number]) => Math.min(...g.tabs.map((t) => areas.indexOf(area(t))));
  return [...groups].sort((a, b) => rank(a) - rank(b));
}

/** Where a project opens for this person: its first page they work in. */
export function projectHome(projectId: string, areas: string[] = []): string {
  const first = groupsFor(true, "expanded", areas)[0]?.tabs[0];
  return `/projects/${projectId}${first?.segment ?? ""}`;
}
