"""Database plumbing. Money is stored as integer paise; percentages as hundredths."""

from decimal import Decimal

from sqlalchemy import BigInteger, Engine, Integer, MetaData, StaticPool, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from lekhara.money import from_paise, to_paise

# Every constraint gets a predictable name, so migrations can alter or drop it on any database.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Money(TypeDecorator):
    """Decimal rupees in Python, integer paise in the database."""

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else to_paise(value)

    def process_result_value(self, value, dialect):
        return None if value is None else from_paise(value)


class Percent(TypeDecorator):
    """Decimal percent (0 to 100) in Python, hundredths of a percent in the database."""

    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return None if value is None else int((Decimal(value) * 100).to_integral_value())

    def process_result_value(self, value, dialect):
        return None if value is None else (Decimal(value) / 100).quantize(Decimal("0.01"))


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs)

        @event.listens_for(engine, "connect")
        def _foreign_keys(dbapi_connection, _record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


def make_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
