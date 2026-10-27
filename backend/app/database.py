"""Database configuration and SQLAlchemy session helpers."""

from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import Column, Engine, MetaData, String, Table, create_engine, event, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_PATH = BACKEND_DIR / "data" / "college_timetable_fresh.db"
DATABASE_ENV_VAR = "TIMETABLE_DATABASE_URL"


class Base(DeclarativeBase):
    """Base class shared by all database models."""


def database_url_from_env() -> str:
    """Return the configured SQLAlchemy URL or the local default URL."""
    configured_url = os.getenv(DATABASE_ENV_VAR)
    if configured_url:
        return configured_url
    return f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


def make_engine(database_url: str) -> Engine:
    """Create an engine and prepare parent folders for file-backed SQLite."""
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    parsed_url = make_url(database_url)
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
    if parsed_url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection: object, _: object) -> None:
            cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


DATABASE_URL = database_url_from_env()
engine = make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class SchemaMigrationRequired(RuntimeError):
    """The database needs an explicit schema migration before app startup."""


SCHEMA_HEAD = "20261021_05"
ALEMBIC_VERSION_TABLE = "alembic_version"


def initialize_schema(target_engine: Engine = engine) -> None:
    """Validate an initialized schema without creating or repairing anything."""
    _require_existing_database(target_engine)
    existing_tables = set(inspect(target_engine).get_table_names())
    if ALEMBIC_VERSION_TABLE not in existing_tables:
        raise SchemaMigrationRequired(
            "This database is not versioned. Startup made no schema changes. "
            "Review and run the explicit migration process only after approval."
        )

    version_table = Table(
        ALEMBIC_VERSION_TABLE,
        MetaData(),
        Column("version_num", String(32), primary_key=True),
    )
    with target_engine.connect() as connection:
        versions = list(connection.execute(select(version_table.c.version_num)).scalars())
    if versions != [SCHEMA_HEAD]:
        raise SchemaMigrationRequired(
            f"Database schema version is {versions or 'unknown'}, expected {SCHEMA_HEAD}. "
            "Startup made no schema changes; run the explicit migration only after approval."
        )

    missing_tables = set(Base.metadata.tables) - existing_tables
    if missing_tables:
        names = ", ".join(sorted(missing_tables))
        raise SchemaMigrationRequired(
            f"The database is marked {SCHEMA_HEAD} but is missing tables: {names}. "
            "Startup made no schema changes."
        )

    inspector = inspect(target_engine)
    missing_columns: list[str] = []
    for table_name, model_table in Base.metadata.tables.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns.extend(
            f"{table_name}.{column.name}"
            for column in model_table.columns
            if column.name not in actual_columns
        )
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise SchemaMigrationRequired(
            f"The database is marked {SCHEMA_HEAD} but is missing required columns: {names}. "
            "Startup made no schema changes; review the migration state and repair it explicitly."
        )
    if target_engine.dialect.name == "sqlite":
        with target_engine.connect() as connection:
            triggers = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").scalars())
        required_triggers = {
            "timetable_snapshots_no_update", "timetable_snapshots_no_delete",
            "timetable_publication_events_no_update", "timetable_publication_events_no_delete",
        }
        if not required_triggers.issubset(triggers):
            missing = ", ".join(sorted(required_triggers - triggers))
            raise SchemaMigrationRequired(f"The database is marked {SCHEMA_HEAD} but is missing required immutability triggers: {missing}. Startup made no schema changes.")


def _require_existing_database(target_engine: Engine) -> None:
    """Fail before connecting when the configured SQLite file is missing."""
    if target_engine.dialect.name != "sqlite":
        return
    database = target_engine.url.database
    if database in (None, ":memory:"):
        return
    path = Path(database).expanduser().resolve()
    if not path.is_file():
        raise SchemaMigrationRequired(
            f"Configured SQLite database does not exist: {path}. Startup will not create it. "
            "For a new development database, use the explicit command documented in README.md."
        )


def initialize_new_database(target_engine: Engine) -> None:
    """Explicitly initialize a new SQLite database at a path that does not exist."""
    # Register every declarative model before create_all. Importing the API app
    # or test fixtures must not be a hidden prerequisite for initialization.
    from app import models  # noqa: F401

    if target_engine.dialect.name != "sqlite":
        raise ValueError("Explicit development initialization currently supports SQLite only.")
    database = target_engine.url.database
    if database in (None, ":memory:"):
        Base.metadata.create_all(bind=target_engine)
        _create_immutability_triggers(target_engine)
        _verify_created_schema(target_engine)
        _write_schema_version(target_engine)
        initialize_schema(target_engine)
        return

    path = Path(database).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Exclusive creation prevents this command from touching an existing file.
        with path.open("xb"):
            pass
    except FileExistsError as error:
        raise FileExistsError(
            f"Database already exists and was left untouched: {path}"
        ) from error
    Base.metadata.create_all(bind=target_engine)
    _create_immutability_triggers(target_engine)
    _verify_created_schema(target_engine)
    _write_schema_version(target_engine)
    initialize_schema(target_engine)


def _verify_created_schema(target_engine: Engine) -> None:
    """Verify all registered application tables and columns before versioning."""
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    missing_tables = set(Base.metadata.tables) - existing_tables
    if missing_tables:
        names = ", ".join(sorted(missing_tables))
        raise RuntimeError(f"Fresh database is missing required tables: {names}.")

    missing_columns: list[str] = []
    for table_name, model_table in Base.metadata.tables.items():
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns.extend(
            f"{table_name}.{column.name}"
            for column in model_table.columns
            if column.name not in actual_columns
        )
    if missing_columns:
        names = ", ".join(sorted(missing_columns))
        raise RuntimeError(f"Fresh database is missing required columns: {names}.")


def _create_immutability_triggers(target_engine: Engine) -> None:
    """Protect approved snapshots and publication history in fresh SQLite databases."""
    if target_engine.dialect.name != "sqlite":
        return
    statements = (
        "CREATE TRIGGER timetable_snapshots_no_update BEFORE UPDATE ON timetable_snapshots BEGIN SELECT RAISE(ABORT, 'approved timetable snapshots are immutable'); END",
        "CREATE TRIGGER timetable_snapshots_no_delete BEFORE DELETE ON timetable_snapshots BEGIN SELECT RAISE(ABORT, 'approved timetable snapshots are immutable'); END",
        "CREATE TRIGGER timetable_publication_events_no_update BEFORE UPDATE ON timetable_publication_events BEGIN SELECT RAISE(ABORT, 'publication history is append-only'); END",
        "CREATE TRIGGER timetable_publication_events_no_delete BEFORE DELETE ON timetable_publication_events BEGIN SELECT RAISE(ABORT, 'publication history is append-only'); END",
    )
    with target_engine.begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)


def _write_schema_version(target_engine: Engine) -> None:
    version_table = Table(
        ALEMBIC_VERSION_TABLE,
        MetaData(),
        Column("version_num", String(32), primary_key=True),
    )
    version_table.create(bind=target_engine, checkfirst=True)
    with target_engine.begin() as connection:
        connection.execute(version_table.insert().values(version_num=SCHEMA_HEAD))


def get_db() -> Generator[Session, None, None]:
    """Provide one short-lived session to an API request."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
