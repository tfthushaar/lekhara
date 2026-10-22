"""Counting attempts for the sign-in and sign-up limits in the database, so every API server
shares one count. Counted in memory, each server would keep its own, and three servers would
let three times as many guesses through.

Keys (an email, or a network address) are stored only as hashes, and old attempts are cleared
as new ones arrive.
"""

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import delete, func, select

from lekhara.models import RateLimitEvent, utcnow

KEEP = timedelta(days=1)
"""Attempts older than this are cleared: longer than any limit's window."""


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class DatabaseStore:
    """Where a LoginThrottle counts, shared by every server using the same database."""

    def __init__(self, session_factory, bucket: str) -> None:
        self.session_factory = session_factory
        self.bucket = bucket[:32]

    def recent(self, key: str, window_seconds: int) -> int:
        since = utcnow() - timedelta(seconds=window_seconds)
        with self.session_factory() as session:
            return session.scalar(
                select(func.count())
                .select_from(RateLimitEvent)
                .where(
                    RateLimitEvent.bucket == self.bucket,
                    RateLimitEvent.key_hash == _hash(key),
                    RateLimitEvent.at >= since,
                )
            )

    def add(self, key: str) -> None:
        with self.session_factory() as session:
            session.add(RateLimitEvent(bucket=self.bucket, key_hash=_hash(key), at=utcnow()))
            if secrets.randbelow(50) == 0:
                session.execute(delete(RateLimitEvent).where(RateLimitEvent.at < utcnow() - KEEP))
            session.commit()

    def clear(self, key: str) -> None:
        with self.session_factory() as session:
            session.execute(
                delete(RateLimitEvent).where(
                    RateLimitEvent.bucket == self.bucket, RateLimitEvent.key_hash == _hash(key)
                )
            )
            session.commit()
