from datetime import date

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.database import Base, SchemaMigrationRequired, initialize_new_database, initialize_schema, make_engine
from app.models import (
    AcademicYear,
    Department,
    PredefinedStudentGroup,
    Semester,
    SemesterSubject,
    StudentGroup,
    Subject,
)
from app.predefined_groups import (
    PredefinedGroupConfigurationError,
    PredefinedGroupDefinition,
    configure_predefined_groups,
)


def seed_cse_s5(db_session):
    department = Department(name="Test CSE", code="CSE")
    academic_year = AcademicYear(
        name="Test Academic Year", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
    )
    db_session.add_all([department, academic_year])
    db_session.flush()
    semester = Semester(
        department_id=department.id,
        academic_year_id=academic_year.id,
        semester_number=5,
        name="S5",
    )
    db_session.add(semester)
    db_session.commit()
    return semester


def s5_a_definition():
    return PredefinedGroupDefinition(
        group_code="CSE-S5-A",
        semester_number=5,
        academic_year_name="Test Academic Year",
        group_name="S5-A",
        student_count=72,
    )


def test_configuration_creates_predefined_s5_group_and_is_idempotent(db_session):
    semester = seed_cse_s5(db_session)
    definition = s5_a_definition()

    first_run = configure_predefined_groups(db_session, [definition])
    first_id = first_run[0].id
    second_run = configure_predefined_groups(db_session, [definition])

    assert second_run[0].id == first_id
    assert second_run[0].semester_id == semester.id
    assert second_run[0].group_name == "S5-A"
    assert second_run[0].student_count == 72
    assert db_session.scalar(select(func.count(StudentGroup.id))) == 1
    marker = db_session.scalar(select(PredefinedStudentGroup))
    assert marker is not None
    assert marker.student_group_id == first_id
    assert marker.group_code == "CSE-S5-A"


def test_manual_s5_configuration_api_creates_both_sections_and_is_idempotent(client, db_session):
    semester = seed_cse_s5(db_session)
    payload = {"academic_year_name": "Test Academic Year"}

    first = client.post("/api/v1/predefined-groups/configure-s5", json=payload)
    second = client.post("/api/v1/predefined-groups/configure-s5", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert [(row["group_name"], row["student_count"], row["is_predefined"]) for row in first.json()] == [
        ("S5-A", 72, True), ("S5-B", 72, True)
    ]
    assert [row["id"] for row in first.json()] == [row["id"] for row in second.json()]
    assert all(row["semester_id"] == semester.id for row in first.json())
    assert db_session.scalar(select(func.count(StudentGroup.id))) == 2


def test_manual_s5_configuration_api_refuses_missing_semester(client):
    response = client.post(
        "/api/v1/predefined-groups/configure-s5",
        json={"academic_year_name": "No such year"},
    )
    assert response.status_code == 422
    assert "Create or confirm the academic year and semester first" in response.json()["detail"]


def test_configuration_can_target_only_supported_semesters():
    for semester_number in (1, 3, 5, 7):
        definition = PredefinedGroupDefinition(
            group_code=f"TEST-S{semester_number}",
            semester_number=semester_number,
            academic_year_name="Test Year",
            group_name=f"test-only S{semester_number} group",
            student_count=1,
        )
        assert definition.semester_number == semester_number

    with pytest.raises(ValueError):
        PredefinedGroupDefinition(
            group_code="TEST-S2",
            semester_number=2,
            academic_year_name="Test Year",
            group_name="test-only S2 group",
            student_count=1,
        )


def test_configuration_refuses_to_overwrite_existing_group(db_session):
    seed_cse_s5(db_session)
    original = configure_predefined_groups(db_session, [s5_a_definition()])[0]
    changed_definition = s5_a_definition().model_copy(update={"student_count": 73})

    with pytest.raises(PredefinedGroupConfigurationError):
        configure_predefined_groups(db_session, [changed_definition])

    db_session.expire_all()
    current = db_session.get(StudentGroup, original.id)
    assert current is not None
    assert current.student_count == 72


def test_predefined_group_is_visible_and_locked_through_ordinary_api(client, db_session):
    semester = seed_cse_s5(db_session)
    group = configure_predefined_groups(db_session, [s5_a_definition()])[0]
    subject = Subject(subject_code="TEST-101", subject_name="Test subject")
    db_session.add(subject)
    db_session.commit()
    subject_id = subject.id

    assignment_response = client.post(
        "/api/v1/semester-subjects",
        json={
            "semester_id": semester.id,
            "student_group_id": group.id,
            "subject_id": subject_id,
            "weekly_lecture_hours": 2,
        },
    )
    assert assignment_response.status_code == 201
    assignment_id = assignment_response.json()["id"]

    group_url = f"/api/v1/student-groups/{group.id}"
    assert client.patch(group_url, json={"student_count": 10}).status_code == 409
    assert client.patch(group_url, json={"group_name": "S5-B"}).status_code == 409
    assert client.patch(group_url, json={"semester_id": semester.id + 1}).status_code == 409
    assert client.patch(group_url, json={"group_code": "OTHER"}).status_code == 422
    assert client.post(
        "/api/v1/student-groups",
        json={
            "semester_id": semester.id,
            "group_name": "S5-C",
            "student_count": 20,
            "group_code": "CSE-S5-C",
        },
    ).status_code == 422
    assert client.delete(group_url).status_code == 409

    listed_groups = client.get("/api/v1/student-groups").json()
    listed_group = next(item for item in listed_groups if item["id"] == group.id)
    assert listed_group["group_name"] == "S5-A"
    assert listed_group["student_count"] == 72
    assert client.get(f"/api/v1/semester-subjects/{assignment_id}").json()["student_group_id"] == group.id

    # The database foreign key is a second safety layer beneath the CRUD guard.
    db_session.delete(group)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_startup_refuses_to_silently_change_an_existing_phase2_database(tmp_path):
    old_database = tmp_path / "existing-academic-data.db"
    old_engine = make_engine(f"sqlite:///{old_database.as_posix()}")
    with old_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE student_groups (id INTEGER PRIMARY KEY)")

    before = set(inspect(old_engine).get_table_names())
    with pytest.raises(SchemaMigrationRequired):
        initialize_schema(old_engine)
    after = set(inspect(old_engine).get_table_names())

    assert before == after == {"student_groups"}
    assert "predefined_student_groups" not in after
    old_engine.dispose()


def test_fresh_schema_includes_protected_identity_table(tmp_path):
    fresh_engine = make_engine(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    initialize_new_database(fresh_engine)
    initialize_schema(fresh_engine)

    table_names = set(inspect(fresh_engine).get_table_names())
    assert "student_groups" in table_names
    assert "predefined_student_groups" in table_names
    assert Base.metadata.tables["predefined_student_groups"] is not None
    fresh_engine.dispose()
