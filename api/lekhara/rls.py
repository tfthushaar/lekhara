"""Row-level security in Postgres: a second wall between firms, beneath the checks in the code.

Every table that holds a firm's data carries a policy. While a signed-in person's request runs,
a row is visible, and can be written, only if it belongs to one of the person's firms (or the
sample firm), or to a project the person certifies. Anything else Lekhara does (sign-up, shared
data room links, the forwarding address, the Tally connector, background jobs, the seed) is not a
person's request and is not restricted, since it has no person to restrict to.

Who is asking is kept on the SQLAlchemy session (`restrict`) and given to Postgres at the start of
every transaction, so it holds across commits within a request. The settings are local to the
transaction, so a pooled connection never carries one request's person into the next.

The policies bind only a role that is not a superuser and does not own the tables with FORCE off:
Lekhara is meant to connect as such a role (`grant` makes one), while migrations run as the owner.
On SQLite none of this applies; the checks in the code are the only wall there.
"""

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from lekhara.db import Base

INFO_KEY = "lekhara_rls"

IDENTITY_TABLES = {
    "users",
    "sessions",
    "one_time_tokens",
    "memberships",
    "project_access",
    "acceptances",
    "access_events",
    "jobs",
    "outbound_emails",
    "passkeys",
    "passkey_challenges",
}
"""Read while working out who the person is, or written with no firm known yet: kept in the open
for the code to guard."""

CHILDREN = {
    "landowner_payments": ("landowner_id", "landowners"),
    "withdrawal_certificates": ("request_id", "withdrawal_requests"),
    "unit_handovers": ("unit_id", "units"),
    "dispute_hearings": ("case_id", "dispute_cases"),
    "dispute_orders": ("case_id", "dispute_cases"),
    "dispute_payments": ("case_id", "dispute_cases"),
    "document_pages": ("document_id", "documents"),
    "data_room_documents": ("room_id", "data_rooms"),
    "data_room_visits": ("room_id", "data_rooms"),
    "data_room_visitors": ("room_id", "data_rooms"),
    "inbound_items": ("message_id", "inbound_messages"),
}
"""Tables with neither a firm nor a project of their own: a row is visible with its parent."""

FUNCTIONS = """
CREATE OR REPLACE FUNCTION lekhara_unrestricted() RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT coalesce(current_setting('lekhara.who', true), '') <> 'person'
$$;

CREATE OR REPLACE FUNCTION lekhara_list(setting text) RETURNS text[] LANGUAGE sql STABLE AS $$
  SELECT string_to_array(coalesce(current_setting(setting, true), ''), ',')
$$;

CREATE OR REPLACE FUNCTION lekhara_org(org text) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT lekhara_unrestricted() OR org = ANY(lekhara_list('lekhara.orgs'))
$$;

CREATE OR REPLACE FUNCTION lekhara_project(project text) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT lekhara_unrestricted()
      OR project = ANY(lekhara_list('lekhara.projects'))
      OR EXISTS (SELECT 1 FROM projects p WHERE p.id = project AND lekhara_org(p.organization_id))
$$;
"""


def _policies() -> dict[str, str]:
    """Table name to the condition a row must meet."""
    out: dict[str, str] = {
        "organizations": "lekhara_org(id) OR id IN (SELECT organization_id FROM projects "
        "WHERE id = ANY(lekhara_list('lekhara.projects')))",
        "projects": "lekhara_org(organization_id) OR id = ANY(lekhara_list('lekhara.projects'))",
    }
    for table in Base.metadata.sorted_tables:
        name, columns = table.name, set(table.c.keys())
        if name in out or name in IDENTITY_TABLES:
            continue
        if name in CHILDREN:
            column, parent = CHILDREN[name]
            # Names from the models, never from a request.
            out[name] = f"EXISTS (SELECT 1 FROM {parent} x WHERE x.id = {name}.{column})"  # nosec B608
        elif {"organization_id", "project_id"} <= columns:
            out[name] = "lekhara_org(organization_id) OR lekhara_project(project_id)"
        elif "organization_id" in columns:
            out[name] = "lekhara_org(organization_id)"
        elif "project_id" in columns:
            out[name] = "lekhara_project(project_id)"
    return out


def install(conn) -> None:
    """Creates the functions and a policy on every table holding a firm's data. Safe to run
    again. Postgres only."""
    if conn.dialect.name != "postgresql":
        return
    conn.execute(text(FUNCTIONS))
    present = set(
        conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
        ).scalars()
    )
    for table, condition in _policies().items():
        if table not in present:
            continue
        conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(f"DROP POLICY IF EXISTS lekhara_firm ON {table}"))
        conn.execute(
            text(
                f"CREATE POLICY lekhara_firm ON {table} USING ({condition}) "
                f"WITH CHECK ({condition})"
            )
        )


def tables() -> list[str]:
    return sorted(_policies())


def grant(conn, role: str, password: str) -> None:
    """A login role for Lekhara to connect as, bound by the policies. Postgres only."""
    if conn.dialect.name != "postgresql":
        return
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).first()
    if exists is None:
        conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{password}'"))
    conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
    conn.execute(
        text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
    )
    conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}"))


# Telling Postgres who is asking


def restrict(session: Session, organization_ids: set[str], project_ids: set[str]) -> None:
    """From now on in this session, rows are limited to these firms and certified projects."""
    session.info[INFO_KEY] = (",".join(sorted(organization_ids)), ",".join(sorted(project_ids)))
    if session.in_transaction() and session.get_bind().dialect.name == "postgresql":
        _apply(session.connection(), session.info[INFO_KEY])


def _apply(connection, who: tuple[str, str]) -> None:
    orgs, projects = who
    connection.execute(
        text(
            "SELECT set_config('lekhara.who', 'person', true), "
            "set_config('lekhara.orgs', :orgs, true), "
            "set_config('lekhara.projects', :projects, true)"
        ),
        {"orgs": orgs, "projects": projects},
    )


@event.listens_for(Session, "after_begin")
def _each_transaction(session: Session, _transaction, connection) -> None:
    who = session.info.get(INFO_KEY)
    if who is not None and connection.dialect.name == "postgresql":
        _apply(connection, who)
