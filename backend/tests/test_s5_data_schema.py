from datetime import date

import pytest
from sqlalchemy import inspect

from app import models
from app.database import Base, SCHEMA_HEAD, SchemaMigrationRequired, initialize_new_database, initialize_schema, make_engine
from app.migrate import ADDITIVE_TABLES, migrate_database


def make_s5_context(db_session):
    department = models.Department(name="Computer Science", code="CSE")
    year = models.AcademicYear(name="TEST-YEAR", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db_session.add_all([department, year])
    db_session.flush()
    semester = models.Semester(
        department_id=department.id,
        academic_year_id=year.id,
        semester_number=5,
        name="S5",
    )
    db_session.add(semester)
    db_session.flush()
    group_a = models.StudentGroup(semester_id=semester.id, group_name="S5-A", student_count=72)
    group_b = models.StudentGroup(semester_id=semester.id, group_name="S5-B", student_count=72)
    db_session.add_all([group_a, group_b])
    db_session.flush()
    db_session.add_all([
        models.PredefinedStudentGroup(student_group_id=group_a.id, group_code="cse-s5-a-test"),
        models.PredefinedStudentGroup(student_group_id=group_b.id, group_code="cse-s5-b-test"),
    ])
    db_session.flush()
    return semester, group_a, group_b


def test_shared_s5_requirement_is_single_and_unknown_hours_stay_unconfirmed(client, db_session):
    semester, _, _ = make_s5_context(db_session)
    db_session.commit()
    subject = client.post("/api/v1/subjects", json={"subject_code": "S5-TEST", "subject_name": "Test Subject"})
    assert subject.status_code == 201

    response = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject.json()["id"]},
    )
    assert response.status_code == 201
    assert response.json()["weekly_lecture_hours"] is None
    assert response.json()["weekly_tutorial_hours"] is None
    assert response.json()["weekly_practical_hours"] is None
    assert response.json()["weekly_lecture_sessions"] is None
    assert response.json()["weekly_tutorial_sessions"] is None
    assert response.json()["weekly_practical_sessions"] is None
    confirmed_zero = client.patch(
        "/api/v1/shared-subject-requirements/" + str(response.json()["id"]),
        json={"weekly_lecture_hours": 0},
    )
    assert confirmed_zero.status_code == 200
    assert confirmed_zero.json()["weekly_lecture_hours"] == 0

    duplicate = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject.json()["id"], "weekly_lecture_hours": 0},
    )
    assert duplicate.status_code == 409
    listed = client.get("/api/v1/shared-subject-requirements").json()
    assert len(listed) == 1
    assert listed[0]["id"] == response.json()["id"]
    assert listed[0]["weekly_lecture_hours"] == 0


def test_session_count_and_hour_consistency_is_validated(client, db_session):
    semester, _, _ = make_s5_context(db_session)
    db_session.commit()
    subject_id = client.post("/api/v1/subjects", json={"subject_code": "S5-COUNT", "subject_name": "Count Test"}).json()["id"]
    requirement = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject_id, "weekly_lecture_hours": 3},
    )
    assert requirement.status_code == 201
    requirement_id = requirement.json()["id"]
    invalid = client.patch(
        f"/api/v1/shared-subject-requirements/{requirement_id}",
        json={"weekly_lecture_sessions": 0},
    )
    assert invalid.status_code == 422
    valid = client.patch(
        f"/api/v1/shared-subject-requirements/{requirement_id}",
        json={"weekly_lecture_sessions": 2},
    )
    assert valid.status_code == 200
    assert valid.json()["weekly_lecture_sessions"] == 2
    assert valid.json()["lecture_session_minutes"] is None


def test_teacher_assignments_are_independent_per_s5_section(client, db_session):
    semester, group_a, group_b = make_s5_context(db_session)
    db_session.commit()
    subject_id = client.post(
        "/api/v1/subjects", json={"subject_code": "S5-ASSIGN", "subject_name": "Assignment Test"}
    ).json()["id"]
    requirement_id = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject_id, "weekly_lecture_hours": 0},
    ).json()["id"]
    faculty_a = client.post(
        "/api/v1/faculty", json={"faculty_name": "Teacher A", "faculty_code": "TA"}
    ).json()["id"]
    faculty_b = client.post(
        "/api/v1/faculty", json={"faculty_name": "Teacher B", "faculty_code": "TB"}
    ).json()["id"]
    for group, faculty in ((group_a, faculty_a), (group_b, faculty_b)):
        result = client.post(
            "/api/v1/section-teacher-assignments",
            json={"requirement_id": requirement_id, "student_group_id": group.id, "faculty_id": faculty},
        )
        assert result.status_code == 201
    rows = client.get("/api/v1/section-teacher-assignments").json()
    assert {(row["student_group_id"], row["faculty_id"]) for row in rows} == {
        (group_a.id, faculty_a), (group_b.id, faculty_b)
    }


def test_same_teacher_can_be_assigned_to_both_s5_sections(client, db_session):
    semester, group_a, group_b = make_s5_context(db_session)
    db_session.commit()
    subject_id = client.post(
        "/api/v1/subjects", json={"subject_code": "S5-SAME", "subject_name": "Shared Teacher Test"}
    ).json()["id"]
    requirement_id = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject_id, "weekly_lecture_hours": 0},
    ).json()["id"]
    teacher_id = client.post(
        "/api/v1/faculty", json={"faculty_name": "Same Teacher", "faculty_code": "SAME"}
    ).json()["id"]
    results = [
        client.post(
            "/api/v1/section-teacher-assignments",
            json={"requirement_id": requirement_id, "student_group_id": group.id, "faculty_id": teacher_id},
        )
        for group in (group_a, group_b)
    ]
    assert [result.status_code for result in results] == [201, 201]
    assert {row["student_group_id"] for row in client.get("/api/v1/section-teacher-assignments").json()} == {
        group_a.id, group_b.id
    }


def test_s5_requirement_rejects_other_semesters(client, db_session):
    department = models.Department(name="Computer Science", code="CSE")
    year = models.AcademicYear(name="TEST-YEAR-2", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db_session.add_all([department, year])
    db_session.flush()
    semester = models.Semester(
        department_id=department.id, academic_year_id=year.id, semester_number=3, name="S3"
    )
    subject = models.Subject(subject_code="OTHER", subject_name="Other semester")
    db_session.add_all([semester, subject])
    db_session.flush()
    db_session.commit()
    response = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject.id},
    )
    assert response.status_code == 422


def test_shared_and_legacy_s5_hour_records_cannot_be_created_as_conflicting_duplicates(client, db_session):
    semester, group_a, _ = make_s5_context(db_session)
    db_session.commit()
    subject = client.post(
        "/api/v1/subjects", json={"subject_code": "DEDUP", "subject_name": "Duplicate guard"}
    ).json()
    legacy = client.post(
        "/api/v1/semester-subjects",
        json={
            "semester_id": semester.id, "student_group_id": group_a.id,
            "subject_id": subject["id"], "weekly_lecture_hours": 2,
        },
    )
    assert legacy.status_code == 201
    shared = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject["id"]},
    )
    assert shared.status_code == 409
    assert "Review them manually" in shared.json()["detail"]

    assert client.delete("/api/v1/semester-subjects/" + str(legacy.json()["id"])).status_code == 204
    shared = client.post(
        "/api/v1/shared-subject-requirements",
        json={"semester_id": semester.id, "subject_id": subject["id"]},
    )
    assert shared.status_code == 201
    legacy_duplicate = client.post(
        "/api/v1/semester-subjects",
        json={
            "semester_id": semester.id, "student_group_id": group_a.id,
            "subject_id": subject["id"], "weekly_lecture_hours": 3,
        },
    )
    assert legacy_duplicate.status_code == 409


def test_time_configuration_and_room_details_are_saved(client, db_session):
    config = client.post("/api/v1/college-time-configurations", json={"version": 1, "is_active": True})
    assert config.status_code == 201
    day = client.post(
        "/api/v1/college-working-days", json={"configuration_id": config.json()["id"], "weekday": 0}
    )
    assert day.status_code == 201
    block = client.post(
        "/api/v1/college-time-blocks",
        json={
            "configuration_id": config.json()["id"], "sequence_number": 1,
            "block_type": "teaching", "period_number": 1,
            "start_time": "08:00", "end_time": "08:50", "is_lab_compatible": True,
        },
    )
    assert block.status_code == 201

    room = client.post(
        "/api/v1/rooms", json={"room_name": "TEST-ROOM", "room_type": "laboratory", "capacity": 75}
    )
    capability = client.post(
        "/api/v1/room-capabilities",
        json={"room_id": room.json()["id"], "capability_name": "Entered by tester", "capability_type": "equipment"},
    )
    profile = client.post(
        "/api/v1/room-availability-profiles", json={"room_id": room.json()["id"], "is_confirmed": False}
    )
    window = client.post(
        "/api/v1/room-availability-windows",
        json={
            "profile_id": profile.json()["id"], "weekday": 0,
            "start_time": "08:00", "end_time": "12:00", "availability": "available",
        },
    )
    assert capability.status_code == 201
    assert profile.status_code == 201
    assert window.status_code == 201
    confirmation = client.patch(
        "/api/v1/room-availability-profiles/" + str(profile.json()["id"]),
        json={"is_confirmed": True},
    )
    assert confirmation.status_code == 200
    assert client.get("/api/v1/room-capabilities").json()[0]["room_id"] == room.json()["id"]


def test_time_blocks_reject_overlap_period_z_and_non_teaching_lab_flag(client):
    config = client.post("/api/v1/college-time-configurations", json={"version": 1})
    config_id = config.json()["id"]
    first = client.post(
        "/api/v1/college-time-blocks",
        json={
            "configuration_id": config_id, "sequence_number": 1, "block_type": "teaching",
            "period_number": 1, "start_time": "08:00", "end_time": "08:50",
        },
    )
    assert first.status_code == 201
    overlap = client.post(
        "/api/v1/college-time-blocks",
        json={
            "configuration_id": config_id, "sequence_number": 2, "block_type": "break",
            "label": "Break", "start_time": "08:40", "end_time": "09:00",
        },
    )
    assert overlap.status_code == 422
    z_period = client.post(
        "/api/v1/college-time-blocks",
        json={
            "configuration_id": config_id, "sequence_number": 2, "block_type": "teaching",
            "period_number": 2, "label": "Period Z", "start_time": "08:50", "end_time": "09:40",
        },
    )
    assert z_period.status_code == 422


def test_room_availability_requires_confirmed_windows_and_rejects_overlaps(client):
    room = client.post(
        "/api/v1/rooms", json={"room_name": "AVAIL-TEST", "room_type": "classroom", "capacity": 75}
    )
    room_id = room.json()["id"]
    incomplete = client.post(
        "/api/v1/room-availability-profiles", json={"room_id": room_id, "is_confirmed": True}
    )
    assert incomplete.status_code == 422
    profile = client.post(
        "/api/v1/room-availability-profiles", json={"room_id": room_id, "is_confirmed": False}
    )
    assert profile.status_code == 201
    first = client.post(
        "/api/v1/room-availability-windows",
        json={
            "profile_id": profile.json()["id"], "weekday": 1,
            "start_time": "09:00", "end_time": "11:00", "availability": "available",
        },
    )
    assert first.status_code == 201
    overlap = client.post(
        "/api/v1/room-availability-windows",
        json={
            "profile_id": profile.json()["id"], "weekday": 1,
            "start_time": "10:00", "end_time": "12:00", "availability": "unavailable",
        },
    )
    assert overlap.status_code == 422
    confirmed = client.patch(
        "/api/v1/room-availability-profiles/" + str(profile.json()["id"]),
        json={"is_confirmed": True},
    )
    assert confirmed.status_code == 200


def test_faculty_availability_and_workload_must_be_explicit_before_confirmation(client):
    faculty = client.post("/api/v1/faculty", json={"faculty_name": "Temporary Test Faculty", "faculty_code": "TEMP-FAC"}).json()
    rejected = client.post("/api/v1/faculty-scheduling-profiles", json={"faculty_id": faculty["id"], "is_confirmed": True, "max_daily_minutes": 300, "max_weekly_minutes": 1200})
    assert rejected.status_code == 422
    profile = client.post("/api/v1/faculty-scheduling-profiles", json={"faculty_id": faculty["id"], "is_confirmed": False})
    assert profile.status_code == 201
    profile_id = profile.json()["id"]
    window = client.post("/api/v1/faculty-availability-windows", json={"profile_id": profile_id, "weekday": 0, "start_time": "08:00", "end_time": "12:00", "availability": "available"})
    assert window.status_code == 201
    overlap = client.post("/api/v1/faculty-availability-windows", json={"profile_id": profile_id, "weekday": 0, "start_time": "11:00", "end_time": "13:00", "availability": "available"})
    assert overlap.status_code == 422
    confirmed = client.patch(f"/api/v1/faculty-scheduling-profiles/{profile_id}", json={"max_daily_minutes": 300, "max_weekly_minutes": 1200, "is_confirmed": True})
    assert confirmed.status_code == 200
    assert client.get("/api/v1/faculty-scheduling-profiles").json()[0]["is_confirmed"] is True


def test_activity_room_and_equipment_requirements_are_saved_and_editable(client):
    department = client.post("/api/v1/departments", json={"name": "Test CSE", "code": "CSE"}).json()
    year = client.post("/api/v1/academic-years", json={"name": "2028-2029", "start_date": "2028-06-01", "end_date": "2029-05-31"}).json()
    semester = client.post("/api/v1/semesters", json={"department_id": department["id"], "academic_year_id": year["id"], "semester_number": 5, "name": "S5"}).json()
    subject = client.post("/api/v1/subjects", json={"subject_code": "TEMP101", "subject_name": "Temporary Test Subject"}).json()
    requirement = client.post("/api/v1/shared-subject-requirements", json={"semester_id": semester["id"], "subject_id": subject["id"]}).json()
    room_requirement = client.post("/api/v1/activity-room-requirements", json={"requirement_id": requirement["id"], "activity_type": "practical", "room_type": "laboratory"})
    assert room_requirement.status_code == 201
    equipment = client.post("/api/v1/activity-equipment-requirements", json={"activity_requirement_id": room_requirement.json()["id"], "capability_name": "Confirmed test equipment"})
    assert equipment.status_code == 201
    assert client.patch(f"/api/v1/activity-equipment-requirements/{equipment.json()['id']}", json={"capability_name": "Edited test equipment"}).status_code == 200
    assert client.get("/api/v1/activity-equipment-requirements").json()[0]["capability_name"] == "Edited test equipment"


def test_migration_upgrades_only_a_temporary_legacy_schema_and_is_repeatable(tmp_path):
    database_file = tmp_path / "migration-test.db"
    database_url = f"sqlite:///{database_file.as_posix()}"
    engine = make_engine(database_url)
    legacy_tables = [table for name, table in Base.metadata.tables.items() if name not in ADDITIVE_TABLES]
    Base.metadata.create_all(bind=engine, tables=legacy_tables)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO departments (name, code, is_active) VALUES (?, ?, ?)",
            ("Preserved Department", "KEEP", True),
        )
    engine.dispose()

    migrate_database(database_url)
    migrated = make_engine(database_url)
    try:
        tables = set(inspect(migrated).get_table_names())
        assert ADDITIVE_TABLES.issubset(tables)
        assert "semester_subjects" in tables
        assert "faculty_subjects" in tables
        with migrated.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == SCHEMA_HEAD
            assert connection.exec_driver_sql("SELECT name FROM departments WHERE code='KEEP'").scalar_one() == "Preserved Department"
    finally:
        migrated.dispose()

    migrate_database(database_url)


def test_startup_refuses_to_modify_unversioned_existing_schema(tmp_path):
    database_file = tmp_path / "guard-test.db"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    Base.metadata.create_all(bind=engine, tables=[Base.metadata.tables["departments"]])
    before = set(inspect(engine).get_table_names())
    with pytest.raises(SchemaMigrationRequired):
        initialize_schema(engine)
    assert set(inspect(engine).get_table_names()) == before
    engine.dispose()


def test_startup_refuses_a_missing_or_wrong_sqlite_path_without_creating_it(tmp_path):
    database_file = tmp_path / "missing" / "wrong.db"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    with pytest.raises(SchemaMigrationRequired, match="will not create it"):
        initialize_schema(engine)
    assert not database_file.exists()
    assert not database_file.parent.exists()
    engine.dispose()
    with pytest.raises(ValueError, match="will not create a database"):
        migrate_database(f"sqlite:///{database_file.as_posix()}")
    assert not database_file.exists()


def test_new_temporary_database_requires_explicit_initialization_and_is_validated(tmp_path):
    database_file = tmp_path / "new.db"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    assert not database_file.exists()
    initialize_new_database(engine)
    assert database_file.exists()
    initialize_schema(engine)
    tables = set(inspect(engine).get_table_names())
    assert ADDITIVE_TABLES.issubset(tables)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == SCHEMA_HEAD
    engine.dispose()


def test_explicit_initialization_refuses_existing_file_without_modifying_it(tmp_path):
    database_file = tmp_path / "keep.db"
    database_file.write_bytes(b"preserve this file")
    before = database_file.read_bytes()
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    with pytest.raises(FileExistsError, match="left untouched"):
        initialize_new_database(engine)
    assert database_file.read_bytes() == before
    engine.dispose()


def test_current_version_with_missing_required_column_is_refused_safely(tmp_path):
    database_file = tmp_path / "incomplete-current.db"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    initialize_new_database(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE shared_subject_requirements DROP COLUMN weekly_lecture_sessions")
    with pytest.raises(SchemaMigrationRequired, match="shared_subject_requirements.weekly_lecture_sessions"):
        initialize_schema(engine)
    assert "weekly_lecture_sessions" not in {column["name"] for column in inspect(engine).get_columns("shared_subject_requirements")}
    engine.dispose()


def test_current_version_with_missing_required_table_is_refused_safely(tmp_path):
    engine = make_engine(f"sqlite:///{(tmp_path / 'missing-table.db').as_posix()}")
    initialize_new_database(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE college_time_blocks")
    with pytest.raises(SchemaMigrationRequired, match="missing tables: college_time_blocks"):
        initialize_schema(engine)
    engine.dispose()


def test_database_at_previous_known_revision_upgrades_with_nullable_session_counts(tmp_path):
    database_file = tmp_path / "previous-revision.db"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    initialize_new_database(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE activity_equipment_requirements")
        connection.exec_driver_sql("DROP TABLE activity_room_requirements")
        connection.exec_driver_sql("DROP TABLE faculty_availability_windows")
        connection.exec_driver_sql("DROP TABLE faculty_scheduling_profiles")
        connection.exec_driver_sql("DROP TABLE timetable_publication_events")
        connection.exec_driver_sql("DROP TABLE official_timetables")
        connection.exec_driver_sql("DROP TABLE timetable_snapshots")
        connection.exec_driver_sql("ALTER TABLE college_time_configurations DROP COLUMN academic_hour_minutes")
        connection.exec_driver_sql("ALTER TABLE shared_subject_requirements DROP COLUMN weekly_lecture_sessions")
        connection.exec_driver_sql("ALTER TABLE shared_subject_requirements DROP COLUMN weekly_tutorial_sessions")
        connection.exec_driver_sql("ALTER TABLE shared_subject_requirements DROP COLUMN weekly_practical_sessions")
        connection.exec_driver_sql("UPDATE alembic_version SET version_num='20261021_02'")
    engine.dispose()

    migrate_database(f"sqlite:///{database_file.as_posix()}")
    migrated = make_engine(f"sqlite:///{database_file.as_posix()}")
    try:
        columns = {column["name"] for column in inspect(migrated).get_columns("shared_subject_requirements")}
        assert {"weekly_lecture_sessions", "weekly_tutorial_sessions", "weekly_practical_sessions"}.issubset(columns)
        assert {"faculty_scheduling_profiles", "faculty_availability_windows", "activity_room_requirements", "activity_equipment_requirements"}.issubset(set(inspect(migrated).get_table_names()))
        assert "academic_hour_minutes" in {column["name"] for column in inspect(migrated).get_columns("college_time_configurations")}
        with migrated.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == SCHEMA_HEAD
    finally:
        migrated.dispose()


def test_database_at_scheduler_revision_adds_approval_tables_and_immutable_triggers(tmp_path):
    database_file = tmp_path / "approval-revision.db"
    engine = make_engine(f"sqlite:///{database_file.as_posix()}")
    initialize_new_database(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE timetable_publication_events")
        connection.exec_driver_sql("DROP TABLE official_timetables")
        connection.exec_driver_sql("DROP TABLE timetable_snapshots")
        connection.exec_driver_sql("UPDATE alembic_version SET version_num='20261021_04'")
    engine.dispose()

    migrate_database(f"sqlite:///{database_file.as_posix()}")
    migrated = make_engine(f"sqlite:///{database_file.as_posix()}")
    try:
        assert {"timetable_snapshots", "official_timetables", "timetable_publication_events"}.issubset(set(inspect(migrated).get_table_names()))
        with migrated.connect() as connection:
            assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == SCHEMA_HEAD
            trigger_names = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").scalars())
            assert {"timetable_snapshots_no_update", "timetable_snapshots_no_delete", "timetable_publication_events_no_update", "timetable_publication_events_no_delete"}.issubset(trigger_names)
            connection.exec_driver_sql("INSERT INTO departments (name, code, is_active) VALUES ('Trigger Test', 'TRIG', 1)")
            department_id = connection.exec_driver_sql("SELECT id FROM departments WHERE code='TRIG'").scalar_one()
            connection.exec_driver_sql("INSERT INTO academic_years (name, start_date, end_date, is_active) VALUES ('Trigger Year', '2028-06-01', '2029-05-31', 1)")
            year_id = connection.exec_driver_sql("SELECT id FROM academic_years WHERE name='Trigger Year'").scalar_one()
            connection.exec_driver_sql("INSERT INTO semesters (department_id, academic_year_id, semester_number, name, is_active) VALUES (?, ?, 5, 'S5', 1)", (department_id, year_id))
            semester_id = connection.exec_driver_sql("SELECT id FROM semesters WHERE academic_year_id=?", (year_id,)).scalar_one()
            connection.exec_driver_sql("INSERT INTO timetable_snapshots (academic_year_id, semester_id, semester_number, version, status, alternative_number, sessions_json, configuration_json, validation_json, approved_at, created_at) VALUES (?, ?, 5, 1, 'approved', 1, '[]', '{}', '[]', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)", (year_id, semester_id))
            with pytest.raises(Exception, match="approved timetable snapshots are immutable"):
                connection.exec_driver_sql("UPDATE timetable_snapshots SET version=2 WHERE semester_id=?", (semester_id,))
    finally:
        migrated.dispose()
