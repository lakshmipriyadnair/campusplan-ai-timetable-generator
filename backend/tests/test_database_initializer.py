"""Safety tests for explicit fresh-database initialization."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import inspect

from app import models  # noqa: F401 - register models for schema expectations
from app.database import BACKEND_DIR, Base, SCHEMA_HEAD, initialize_new_database, make_engine
from app.initialize_database import main as initialize_database_main


def test_cli_initializer_creates_complete_empty_schema_in_clean_process(tmp_path: Path) -> None:
    database_file = tmp_path / "fresh.db"
    database_url = f"sqlite:///{database_file.as_posix()}"
    child_env = os.environ.copy()
    child_env.pop("TIMETABLE_DATABASE_URL", None)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.initialize_database",
            "--database-url",
            database_url,
        ],
        cwd=BACKEND_DIR,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "New development database initialized." in result.stdout
    engine = make_engine(database_url)
    try:
        inspector = inspect(engine)
        actual_tables = set(inspector.get_table_names())
        assert actual_tables == set(Base.metadata.tables) | {"alembic_version"}

        for table_name, model_table in Base.metadata.tables.items():
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            assert {column.name for column in model_table.columns} <= actual_columns

        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one() == SCHEMA_HEAD
            for table_name in Base.metadata.tables:
                assert connection.exec_driver_sql(
                    f'SELECT COUNT(*) FROM "{table_name}"'
                ).scalar_one() == 0
    finally:
        engine.dispose()


def test_initializer_refuses_existing_file_without_overwriting(tmp_path: Path) -> None:
    database_file = tmp_path / "already-here.db"
    original_contents = b"keep these bytes unchanged"
    database_file.write_bytes(original_contents)
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    try:
        with pytest.raises(FileExistsError, match="left untouched"):
            initialize_new_database(engine)
        assert database_file.read_bytes() == original_contents
    finally:
        engine.dispose()


def test_failed_initialization_does_not_print_success_or_write_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    database_file = tmp_path / "failed.db"
    database_url = f"sqlite:///{database_file.as_posix()}"

    def fail_create_all(*args, **kwargs) -> None:
        raise RuntimeError("simulated schema creation failure")

    monkeypatch.setattr(Base.metadata, "create_all", fail_create_all)
    monkeypatch.setattr(
        sys,
        "argv",
        ["app.initialize_database", "--database-url", database_url],
    )

    with pytest.raises(RuntimeError, match="simulated schema creation failure"):
        initialize_database_main()

    output = capsys.readouterr()
    assert "New development database initialized." not in output.out
    assert database_file.exists()
    assert database_file.stat().st_size == 0
