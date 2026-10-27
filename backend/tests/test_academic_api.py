import pytest
from sqlalchemy import inspect

from app.database import DATABASE_ENV_VAR, DEFAULT_DATABASE_PATH, database_url_from_env, make_engine


def test_database_url_defaults_to_backend_application_data(monkeypatch):
    monkeypatch.delenv(DATABASE_ENV_VAR, raising=False)

    assert database_url_from_env() == f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"


def test_database_url_can_be_configured_by_environment(monkeypatch, tmp_path):
    configured_url = f"sqlite:///{(tmp_path / 'custom.db').as_posix()}"
    monkeypatch.setenv(DATABASE_ENV_VAR, configured_url)

    assert database_url_from_env() == configured_url
    custom_engine = make_engine(database_url_from_env())
    with custom_engine.connect():
        pass
    custom_engine.dispose()
    assert (tmp_path / "custom.db").exists()


def test_all_academic_record_types_support_crud(client):
    department_response = client.post(
        "/api/v1/departments", json={"name": "Computer Science", "code": "CSE"}
    )
    assert department_response.status_code == 201
    department = department_response.json()

    year_response = client.post(
        "/api/v1/academic-years",
        json={"name": "2026-2027", "start_date": "2026-06-01", "end_date": "2027-05-31"},
    )
    assert year_response.status_code == 201
    year = year_response.json()

    semester_response = client.post(
        "/api/v1/semesters",
        json={
            "department_id": department["id"],
            "academic_year_id": year["id"],
            "semester_number": 1,
            "name": "S1",
        },
    )
    assert semester_response.status_code == 201
    semester = semester_response.json()

    group_response = client.post(
        "/api/v1/student-groups",
        json={
            "semester_id": semester["id"],
            "group_name": "Group A",
            "section_identifier": "A",
            "student_count": 42,
        },
    )
    assert group_response.status_code == 201
    group = group_response.json()
    group_b_response = client.post(
        "/api/v1/student-groups",
        json={"semester_id": semester["id"], "group_name": "Group B", "student_count": 18},
    )
    assert group_b_response.status_code == 201
    group_b = group_b_response.json()

    faculty_response = client.post(
        "/api/v1/faculty",
        json={"faculty_name": "Example Teacher", "faculty_code": "FAC-01", "email": "teacher@example.edu"},
    )
    assert faculty_response.status_code == 201
    faculty = faculty_response.json()

    room_response = client.post(
        "/api/v1/rooms",
        json={"room_name": "Room 101", "room_type": "classroom", "capacity": 60},
    )
    assert room_response.status_code == 201
    room = room_response.json()

    subject_response = client.post(
        "/api/v1/subjects", json={"subject_code": "CS101", "subject_name": "Foundations"}
    )
    assert subject_response.status_code == 201
    subject = subject_response.json()

    semester_subject_response = client.post(
        "/api/v1/semester-subjects",
        json={
            "semester_id": semester["id"],
            "student_group_id": group["id"],
            "subject_id": subject["id"],
            "weekly_lecture_hours": 3,
            "weekly_tutorial_hours": 1,
            "weekly_practical_hours": 2,
            "practical_session_minutes": 120,
        },
    )
    assert semester_subject_response.status_code == 201
    semester_subject = semester_subject_response.json()

    duplicate_group_subject = client.post(
        "/api/v1/semester-subjects",
        json={"semester_id": semester["id"], "student_group_id": group["id"], "subject_id": subject["id"]},
    )
    assert duplicate_group_subject.status_code == 409
    group_b_subject_response = client.post(
        "/api/v1/semester-subjects",
        json={"semester_id": semester["id"], "student_group_id": group_b["id"], "subject_id": subject["id"]},
    )
    assert group_b_subject_response.status_code == 201
    group_b_subject = group_b_subject_response.json()
    group_b_only_subject = client.post(
        "/api/v1/subjects", json={"subject_code": "CS102", "subject_name": "Group B elective"}
    ).json()
    group_b_only_assignment = client.post(
        "/api/v1/semester-subjects",
        json={
            "semester_id": semester["id"],
            "student_group_id": group_b["id"],
            "subject_id": group_b_only_subject["id"],
            "weekly_lecture_hours": 2,
        },
    )
    assert group_b_only_assignment.status_code == 201
    group_b_only_assignment = group_b_only_assignment.json()

    faculty_subject_response = client.post(
        "/api/v1/faculty-subjects",
        json={"faculty_id": faculty["id"], "semester_subject_id": semester_subject["id"]},
    )
    assert faculty_subject_response.status_code == 201
    faculty_subject = faculty_subject_response.json()
    duplicate_faculty_assignment = client.post(
        "/api/v1/faculty-subjects",
        json={"faculty_id": faculty["id"], "semester_subject_id": semester_subject["id"]},
    )
    assert duplicate_faculty_assignment.status_code == 409

    resources = [
        ("departments", department["id"], {"name": "Computer Science and Engineering"}),
        ("academic-years", year["id"], {"name": "2026-2027 Academic Year"}),
        ("semesters", semester["id"], {"name": "Semester 1"}),
        ("student-groups", group["id"], {"student_count": 43}),
        ("student-groups", group_b["id"], {"student_count": 19}),
        ("faculty", faculty["id"], {"faculty_name": "Example Faculty"}),
        ("rooms", room["id"], {"capacity": 62}),
        ("subjects", subject["id"], {"subject_name": "Foundations of Computing"}),
        ("subjects", group_b_only_subject["id"], {"subject_name": "Group B elective module"}),
        ("semester-subjects", semester_subject["id"], {"weekly_lecture_hours": 4}),
        ("semester-subjects", group_b_subject["id"], {"weekly_lecture_hours": 1}),
        ("semester-subjects", group_b_only_assignment["id"], {"weekly_lecture_hours": 3}),
        (
            "faculty-subjects",
            faculty_subject["id"],
            {"faculty_id": faculty["id"]},
        ),
    ]

    for resource, record_id, changes in resources:
        path = f"/api/v1/{resource}/{record_id}"
        assert client.get(path).status_code == 200
        assert client.patch(path, json=changes).status_code == 200
        assert client.get(f"/api/v1/{resource}").status_code == 200
        assert record_id in {row["id"] for row in client.get(f"/api/v1/{resource}").json()}

    # Delete leaf records first; each referenced parent remains protected.
    for resource, record_id, _ in reversed(resources):
        assert client.delete(f"/api/v1/{resource}/{record_id}").status_code == 204
        assert client.get(f"/api/v1/{resource}/{record_id}").status_code == 404


def test_rejects_duplicate_codes_and_unique_assignments(client):
    assert client.post(
        "/api/v1/departments", json={"name": "Computing", "code": "CSE"}
    ).status_code == 201
    assert client.post(
        "/api/v1/departments", json={"name": "Computing duplicate", "code": "CSE"}
    ).status_code == 409
    assert client.post(
        "/api/v1/departments", json={"name": "Computing", "code": "CS"}
    ).status_code == 409
    assert client.post(
        "/api/v1/faculty", json={"faculty_name": "Teacher A", "faculty_code": "F-01"}
    ).status_code == 201
    assert client.post(
        "/api/v1/faculty", json={"faculty_name": "Teacher B", "faculty_code": "F-01"}
    ).status_code == 409
    assert client.post(
        "/api/v1/subjects", json={"subject_code": "CS1", "subject_name": "Subject A"}
    ).status_code == 201
    assert client.post(
        "/api/v1/subjects", json={"subject_code": "CS1", "subject_name": "Subject B"}
    ).status_code == 409


def test_invalid_values_dates_and_email_return_validation_errors(client):
    invalid_year = client.post(
        "/api/v1/academic-years",
        json={"name": "Bad year", "start_date": "2027-05-31", "end_date": "2026-06-01"},
    )
    assert invalid_year.status_code == 422

    valid_year = client.post(
        "/api/v1/academic-years",
        json={"name": "2027-2028", "start_date": "2027-06-01", "end_date": "2028-05-31"},
    ).json()
    bad_date_update = client.patch(
        f"/api/v1/academic-years/{valid_year['id']}", json={"start_date": "2029-06-01"}
    )
    assert bad_date_update.status_code == 422

    assert client.post(
        "/api/v1/student-groups", json={"semester_id": 1, "group_name": "Bad", "student_count": -2}
    ).status_code == 422
    assert client.post(
        "/api/v1/rooms", json={"room_name": "Bad room", "room_type": "classroom", "capacity": 0}
    ).status_code == 422
    assert client.post(
        "/api/v1/faculty", json={"faculty_name": "Bad email", "faculty_code": "F-BAD", "email": "nope"}
    ).status_code == 422

    assert client.post(
        "/api/v1/semester-subjects",
        json={"semester_id": 1, "student_group_id": 1, "subject_id": 1, "weekly_lecture_hours": -1},
    ).status_code == 422


def test_missing_references_are_reported_clearly(client):
    assert client.post(
        "/api/v1/semesters",
        json={"department_id": 999, "academic_year_id": 999, "semester_number": 1, "name": "S1"},
    ).status_code == 404
    assert client.post(
        "/api/v1/student-groups", json={"semester_id": 999, "group_name": "A", "student_count": 1}
    ).status_code == 404
    assert client.post(
        "/api/v1/semester-subjects",
        json={"semester_id": 999, "student_group_id": 999, "subject_id": 999},
    ).status_code == 404
    assert client.post(
        "/api/v1/faculty-subjects", json={"faculty_id": 999, "semester_subject_id": 999}
    ).status_code == 404


def test_scheduler_input_collections_are_registered_and_empty_on_a_fresh_test_database(client):
    for collection in (
        "faculty-scheduling-profiles",
        "faculty-availability-windows",
        "activity-room-requirements",
        "activity-equipment-requirements",
    ):
        response = client.get(f"/api/v1/{collection}")
        assert response.status_code == 200, (collection, response.text)
        assert response.json() == []


def test_referenced_records_cannot_be_deleted(client):
    department = client.post(
        "/api/v1/departments", json={"name": "Engineering", "code": "ENG"}
    ).json()
    year = client.post(
        "/api/v1/academic-years",
        json={"name": "2028-2029", "start_date": "2028-06-01", "end_date": "2029-05-31"},
    ).json()
    semester = client.post(
        "/api/v1/semesters",
        json={"department_id": department["id"], "academic_year_id": year["id"], "semester_number": 1, "name": "S1"},
    ).json()
    client.post(
        "/api/v1/student-groups", json={"semester_id": semester["id"], "group_name": "A", "student_count": 10}
    )

    assert client.delete(f"/api/v1/semesters/{semester['id']}").status_code == 409
    assert client.delete(f"/api/v1/departments/{department['id']}").status_code == 409
    assert client.delete(f"/api/v1/academic-years/{year['id']}").status_code == 409


def test_group_subject_must_belong_to_the_selected_semester(client):
    department = client.post(
        "/api/v1/departments", json={"name": "CSE", "code": "CSE"}
    ).json()
    year = client.post(
        "/api/v1/academic-years",
        json={"name": "2030-2031", "start_date": "2030-06-01", "end_date": "2031-05-31"},
    ).json()
    semester_one = client.post(
        "/api/v1/semesters",
        json={"department_id": department["id"], "academic_year_id": year["id"], "semester_number": 1, "name": "S1"},
    ).json()
    semester_three = client.post(
        "/api/v1/semesters",
        json={"department_id": department["id"], "academic_year_id": year["id"], "semester_number": 3, "name": "S3"},
    ).json()
    group = client.post(
        "/api/v1/student-groups",
        json={"semester_id": semester_one["id"], "group_name": "S1 Group A", "student_count": 20},
    ).json()
    subject = client.post(
        "/api/v1/subjects", json={"subject_code": "MATH1", "subject_name": "Mathematics"}
    ).json()

    response = client.post(
        "/api/v1/semester-subjects",
        json={
            "semester_id": semester_three["id"],
            "student_group_id": group["id"],
            "subject_id": subject["id"],
        },
    )
    assert response.status_code == 422


def test_foreign_keys_are_enabled_on_sqlite_connections(test_engine):
    with test_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    table_names = set(inspect(test_engine).get_table_names())
    assert "departments" in table_names
    assert "faculty_subjects" in table_names


def test_create_schemas_reject_negative_hour_values():
    from app.schemas import SemesterSubjectCreate

    with pytest.raises(ValueError):
        SemesterSubjectCreate(
            semester_id=1, student_group_id=1, subject_id=1, weekly_practical_hours=-1
        )


def test_created_and_edited_records_survive_closed_sessions_and_api_reload(client, test_engine):
    from sqlalchemy.orm import Session
    from app.models import Faculty

    created = client.post(
        "/api/v1/faculty",
        json={"faculty_name": "Persistence Check", "faculty_code": "PERSIST-01"},
    )
    assert created.status_code == 201
    faculty_id = created.json()["id"]

    # The request-scoped API session is closed when the request returns.
    with Session(test_engine) as new_session:
        record = new_session.get(Faculty, faculty_id)
        assert record is not None
        assert record.faculty_name == "Persistence Check"

    reloaded = client.get("/api/v1/faculty")
    assert reloaded.status_code == 200
    assert next(row for row in reloaded.json() if row["id"] == faculty_id)["faculty_name"] == "Persistence Check"

    updated = client.patch(f"/api/v1/faculty/{faculty_id}", json={"faculty_name": "Edited Persistence Check"})
    assert updated.status_code == 200
    with Session(test_engine) as reopened_session:
        record = reopened_session.get(Faculty, faculty_id)
        assert record is not None
        assert record.faculty_name == "Edited Persistence Check"

    refreshed_again = client.get("/api/v1/faculty")
    assert refreshed_again.status_code == 200
    assert next(row for row in refreshed_again.json() if row["id"] == faculty_id)["faculty_name"] == "Edited Persistence Check"
