from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEKHARA_", env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./lekhara.db"
    today: date | None = None
    """Fixes the date Lekhara treats as today. For demos and tests only."""
    auto_migrate: bool = True
    """Bring the database schema up to date when the API starts."""
    demo: bool = False
    """Show the demo accounts on the sign-in screen. Never set in production."""
    storage_dir: str = "./storage"
    """Where the document vault keeps files on local disk."""
    max_upload_mb: int = 20
    tally_upload_mb: int = 100
    trial_days: int = 30
    web_url: str = "http://localhost:3000"
    """Where people open Lekhara; used in the links Lekhara emails."""
    smtp_url: str | None = None
    """smtp://user:password@host:587 or smtps://...; without it, emails go to the log."""
    mail_from: str = "Lekhara <no-reply@lekhara.local>"
    inbound_domain: str = "in.lekhara.local"
    """Each project's forwarding address is <token>@ this domain."""
    inbound_secret: str | None = None
    """Shared with the email service that posts incoming mail to /inbound/email."""
    inbound_imap_url: str | None = None
    """imaps://user:password@host/INBOX: a catch-all mailbox to check instead of, or as well
    as, posted mail."""
    secret_key: str | None = None
    """Seals secrets kept for firms, such as statement passwords. Set it in production."""
    worker: bool = True
    """Run background jobs (incoming mail, connectors) inside the API process."""
    clamav_url: str | None = None
    """tcp://host:3310 of a clamd daemon to check every file for viruses; unset, nothing is
    scanned."""
    signups_per_hour: int = 10
    """Sign-ups allowed from one network address in an hour."""
    resets_per_hour: int = 10
    """Password reset emails asked for from one network address in an hour."""
    failed_logins_per_address: int = 30
    """Failed sign-ins from one network address in fifteen minutes, across all emails."""
    company_name: str = "Lekhara"
    """The legal entity that runs Lekhara, as named in the terms and on invoices."""
    company_address: str = "Bengaluru, Karnataka, India"
    grievance_officer: str = "The grievance officer"
    grievance_email: str = "grievance@lekhara.local"
    contact_email: str = "hello@lekhara.local"
    """Where builders write to us, shown on the website's contact page."""
    contact_phone: str | None = None
    price_per_month: int | None = None
    """The subscription in rupees a month before GST, shown on the pricing page; unset until
    the prices are decided."""
    months_charged_per_year: int = 10
    """Paying yearly: twelve months for the price of this many."""

    def as_of(self) -> date:
        return self.today or date.today()


@lru_cache
def get_settings() -> Settings:
    return Settings()
