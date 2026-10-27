"""Explicit schema migration entry point. It never uses the app's default DB URL."""

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from app import models  # noqa: F401 - register the existing and additive tables
from app.database import BACKEND_DIR, Base, make_engine

BASELINE_REVISION = "20261021_01"
PREVIOUS_REVISION = "20261021_03"
SCHEDULER_REVISION = "20261021_04"
HEAD_REVISION = "20261021_05"
SESSION_COUNT_REVISION = "20261021_02"
SCHEDULER_TABLES = {
    "faculty_scheduling_profiles",
    "faculty_availability_windows",
    "activity_room_requirements",
    "activity_equipment_requirements",
}
APPROVAL_TABLES = {"timetable_snapshots", "official_timetables", "timetable_publication_events"}
ADDITIVE_TABLES = {
    "shared_subject_requirements",
    "section_teacher_assignments",
    "college_time_configurations",
    "college_working_days",
    "college_time_blocks",
    "room_capabilities",
    "room_availability_profiles",
    "room_availability_windows",
    *SCHEDULER_TABLES,
    *APPROVAL_TABLES,
}
LEGACY_TABLES = {
    "departments", "academic_years", "semesters", "student_groups",
    "predefined_student_groups", "faculty", "rooms", "subjects",
    "semester_subjects", "faculty_subjects",
}


def _require_existing_sqlite_file(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite" and url.database not in (None, ":memory:"):
        path = Path(url.database).expanduser().resolve()
        if not path.is_file():
            raise ValueError(
                "The migration target SQLite file does not exist. This command will not create a database."
            )


def _preflight_unversioned_database(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if not LEGACY_TABLES.issubset(tables):
        missing = ", ".join(sorted(LEGACY_TABLES - tables))
        raise ValueError(f"Database does not match the supported legacy schema; missing tables: {missing}.")
    collisions = ADDITIVE_TABLES.intersection(tables)
    if collisions:
        raise ValueError(
            "Unversioned database already contains one or more new scheduling tables. "
            "Stop for manual review; no migration was attempted: " + ", ".join(sorted(collisions))
        )
    for table_name in LEGACY_TABLES:
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        expected_columns = set(Base.metadata.tables[table_name].columns.keys())
        missing_columns = expected_columns - actual_columns
        if missing_columns:
            raise ValueError(
                f"Legacy table {table_name} is missing expected columns: {', '.join(sorted(missing_columns))}."
            )


def migrate_database(database_url: str) -> None:
    """Version an existing supported DB and add the new tables, with no data copying."""
    if not database_url.strip():
        raise ValueError("Provide --database-url explicitly; the application default is never used here.")
    _require_existing_sqlite_file(database_url)
    engine = make_engine(database_url)
    try:
        tables = set(inspect(engine).get_table_names())
        with engine.connect() as connection:
            if "alembic_version" not in tables:
                _preflight_unversioned_database(engine)
                config = _alembic_config(connection)
                command.stamp(config, BASELINE_REVISION)
            else:
                revisions = list(connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalars())
                # End the read's implicit SQLAlchemy transaction before Alembic
                # starts its migration transaction on this supplied connection.
                connection.commit()
                if revisions not in ([BASELINE_REVISION], [SESSION_COUNT_REVISION], [PREVIOUS_REVISION], [SCHEDULER_REVISION], [HEAD_REVISION]):
                    raise ValueError(f"Unsupported migration version {revisions!r}; no migration was attempted.")
                if revisions == [BASELINE_REVISION]:
                    _preflight_unversioned_database(engine)
                elif revisions == [SESSION_COUNT_REVISION]:
                    _validate_current_schema(engine, excluded_columns={
                        "shared_subject_requirements.weekly_lecture_sessions",
                        "shared_subject_requirements.weekly_tutorial_sessions",
                        "shared_subject_requirements.weekly_practical_sessions",
                        "college_time_configurations.academic_hour_minutes",
                    }, excluded_tables=SCHEDULER_TABLES | APPROVAL_TABLES)
                elif revisions == [PREVIOUS_REVISION]:
                    _validate_current_schema(engine, excluded_columns={
                        "college_time_configurations.academic_hour_minutes",
                    }, excluded_tables=SCHEDULER_TABLES | APPROVAL_TABLES)
                elif revisions == [SCHEDULER_REVISION]:
                    _validate_current_schema(engine, excluded_tables=APPROVAL_TABLES)
                elif revisions == [HEAD_REVISION]:
                    _validate_current_schema(engine)
                config = _alembic_config(connection)
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def _validate_current_schema(
    engine, excluded_columns: set[str] | None = None, excluded_tables: set[str] | None = None
) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    excluded_tables = excluded_tables or set()
    missing_tables = set(Base.metadata.tables) - tables - excluded_tables
    if missing_tables:
        raise ValueError("Current-version database is missing tables: " + ", ".join(sorted(missing_tables)))
    excluded_columns = excluded_columns or set()
    missing_columns = []
    for table_name, model_table in Base.metadata.tables.items():
        if table_name in excluded_tables:
            continue
        actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns.extend(
            f"{table_name}.{column.name}"
            for column in model_table.columns
            if column.name not in actual_columns and f"{table_name}.{column.name}" not in excluded_columns
        )
    if missing_columns:
        raise ValueError("Current-version database is missing columns: " + ", ".join(sorted(missing_columns)))


def _alembic_config(connection) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["connection"] = connection
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        required=True,
        help="Explicit SQLAlchemy URL of an existing database; no default is used.",
    )
    args = parser.parse_args()
    migrate_database(args.database_url)
    print(f"Schema migration completed through {HEAD_REVISION}.")


if __name__ == "__main__":
    main()
