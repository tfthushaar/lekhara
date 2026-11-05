"""What each role in the firm sees and does.

Owner, finance and accounts see everything, and a viewer sees everything without changing it.
The two working roles see only their own part:

- Sales: leads and bookings, units, handover, and buyers' requests after handover.
- Site engineer: the daily site report, materials, and snags and defects.

The web draws each person's places from `areas`, and the API refuses anything outside them, so a
link typed in by hand gets nowhere either.

Who may change what, within those places:

- Approving a payment: owner and finance. Accounts prepares bills and records payments, but cannot
  approve its own, so two people see every payment out.
- Loans: owner and finance.
- Contractors' bills and orders: owner, finance and accounts.
- Site reports, material requests and receipts: the site engineer, and owner, finance and
  accounts.
- Snags, defects and buyers' requests: everyone in the firm except a viewer.
"""

import re

from lekhara.auth import OrgRole, Principal
from lekhara.models import Project

ALL = (
    "overview", "sales", "units", "collections", "handover", "issues", "disputes",
    "escrow", "contractors", "suppliers", "budget", "cash",
    "site", "materials",
    "krera", "tax", "approvals",
    "documents", "import", "setup",
)  # fmt: skip

AREAS: dict[OrgRole, tuple[str, ...]] = {
    OrgRole.OWNER: ALL,
    OrgRole.FINANCE: ALL,
    OrgRole.ACCOUNTS: ALL,
    OrgRole.VIEWER: ALL,
    OrgRole.SALES: ("sales", "units", "handover", "issues"),
    OrgRole.SITE: ("site", "materials", "issues"),
}

MANAGERS = (OrgRole.OWNER, OrgRole.FINANCE, OrgRole.ACCOUNTS)
APPROVERS = (OrgRole.OWNER, OrgRole.FINANCE)
SITE_WORK = (*MANAGERS, OrgRole.SITE)
ISSUE_WORK = (*MANAGERS, OrgRole.SITE, OrgRole.SALES)
SALES_WORK = (*MANAGERS, OrgRole.SALES)

# What the two working roles may reach in the API. Everything else is refused.
_COMMON = (
    r"^/auth/", r"^/legal", r"^/today$", r"^/projects$", r"^/projects/[^/]+$", r"^/organization$",
    r"^/demo/mailbox$", r"^/health$",
)  # fmt: skip
_OPEN: dict[OrgRole, tuple[str, ...]] = {
    OrgRole.SALES: (
        *_COMMON,
        r"^/projects/[^/]+/(sales|leads|units|issues)(/|$)",
        r"^/projects/[^/]+/units/[^/]+/cost-sheet(\.pdf)?$",
        r"^/(leads|visits|holds|bookings|issues)/",
        r"^/partners(/[^/]+)?$",
        r"^/units/[^/]+(/handover)?$",
    ),
    OrgRole.SITE: (
        *_COMMON,
        r"^/projects/[^/]+/(site|materials|issues|daily-reports|material-requests)(/|$)",
        r"^/(daily-reports|material-requests|material-items|issues)/",
    ),
}
_OPEN_RE = {role: re.compile("|".join(f"(?:{p})" for p in pats)) for role, pats in _OPEN.items()}


def role_of(me: Principal, organization_id: str | None = None) -> OrgRole | None:
    if organization_id is not None:
        return me.org_roles.get(organization_id)
    return next(iter(me.org_roles.values()), None)


def areas_for(role: OrgRole | None) -> tuple[str, ...]:
    return AREAS.get(role, ()) if role is not None else ()


def allowed_path(me: Principal, path: str) -> bool:
    """Whether a working role may reach this part of the API at all."""
    roles = set(me.org_roles.values())
    if not roles or roles & set(MANAGERS) or OrgRole.VIEWER in roles:
        return True
    return any(_OPEN_RE[r].match(path) for r in roles if r in _OPEN_RE)


def limited(me: Principal, project: Project) -> bool:
    """A working role, for whom a project's money is not shown."""
    return me.org_roles.get(project.organization_id) in (OrgRole.SALES, OrgRole.SITE)


def can(me: Principal, project: Project, who: tuple[OrgRole, ...]) -> bool:
    return me.org_roles.get(project.organization_id) in who
