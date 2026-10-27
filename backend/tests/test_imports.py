"""Excel imports use temporary API databases and never touch local user data."""

from io import BytesIO
from datetime import date

from openpyxl import Workbook

from app.models import AcademicYear, Department, Faculty, Room, Semester


def workbook_bytes(columns: list[str], rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(columns)
    for row in rows:
        sheet.append(row)
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def upload(client, path: str, filename: str, content: bytes):
    return client.post(
        path,
        files={"file": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def make_cse_semester(db_session):
    department = Department(name="Computer Science", code="CSE")
    year = AcademicYear(name="2025-26", start_date=date(2025, 6, 1), end_date=date(2026, 5, 31))
    db_session.add_all([department, year])
    db_session.flush()
    semester = Semester(department_id=department.id, academic_year_id=year.id, semester_number=1, name="S1")
    db_session.add(semester)
    db_session.commit()
    return semester


def test_template_downloads_match_documented_xlsx_columns(client):
    response = client.get("/api/v1/imports/templates/faculty")
    assert response.status_code == 200
    assert response.headers["content-disposition"].endswith('filename="faculty-template.xlsx"')
    assert response.content[:2] == b"PK"


def test_preview_rejects_non_xlsx_and_wrong_columns(client):
    not_excel = upload(client, "/api/v1/imports/faculty/preview", "data.xls", b"not xlsx")
    assert not_excel.status_code == 415
    wrong_columns = upload(client, "/api/v1/imports/faculty/preview", "data.xlsx", workbook_bytes(["name", "code"], [["A", "1"]]))
    assert wrong_columns.status_code == 422
    assert "expected_columns" in wrong_columns.json()["detail"]
    oversized = upload(client, "/api/v1/imports/faculty/preview", "large.xlsx", b"x" * (5 * 1024 * 1024 + 1))
    assert oversized.status_code == 413


def test_preview_reports_missing_values_and_duplicate_codes_without_writing(client, db_session):
    content = workbook_bytes(
        ["faculty_name", "faculty_code", "email"],
        [["", "T-01", ""], ["Teacher", "T-01", "teacher@example.edu"]],
    )
    response = upload(client, "/api/v1/imports/faculty/preview", "faculty.xlsx", content)
    assert response.status_code == 200
    assert response.json()["can_apply"] is False
    assert any(error["row"] == 2 and error["column"] == "faculty_name" for error in response.json()["errors"])
    assert any("Duplicate faculty_code" in error["message"] for error in response.json()["errors"])
    assert db_session.query(Faculty).count() == 0


def test_duplicate_saved_code_is_reported_and_not_overwritten(client, db_session):
    db_session.add(Faculty(faculty_name="Existing teacher", faculty_code="T-01"))
    db_session.commit()
    content = workbook_bytes(["faculty_name", "faculty_code", "email"], [["New name", "T-01", ""]])
    response = upload(client, "/api/v1/imports/faculty/preview", "faculty.xlsx", content)
    assert response.status_code == 200
    assert response.json()["can_apply"] is False
    assert "already exists" in response.json()["errors"][0]["message"]
    assert db_session.query(Faculty).one().faculty_name == "Existing teacher"


def test_invalid_room_capacity_and_import_are_atomic(client, db_session):
    columns = ["room_name", "room_type", "capacity"]
    content = workbook_bytes(columns, [["Classroom A", "classroom", 30], ["Lab X", "laboratory", 0]])
    preview = upload(client, "/api/v1/imports/rooms/preview", "rooms.xlsx", content).json()
    assert preview["can_apply"] is False
    assert any(error["row"] == 3 and error["column"] == "capacity" for error in preview["errors"])
    applied = client.post(
        "/api/v1/imports/rooms/apply",
        data={"expected_preview_id": preview["preview_id"]},
        files={"file": ("rooms.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert applied.status_code == 422
    assert db_session.query(Room).count() == 0


def test_successful_import_saves_every_row_and_changed_file_requires_new_preview(client, db_session):
    columns = ["faculty_name", "faculty_code", "email"]
    content = workbook_bytes(columns, [["Teacher One", "T-01", ""], ["Teacher Two", "T-02", "two@example.edu"]])
    preview = upload(client, "/api/v1/imports/faculty/preview", "faculty.xlsx", content).json()
    assert preview["can_apply"] is True
    changed = workbook_bytes(columns, [["Different", "T-03", ""]])
    mismatch = client.post(
        "/api/v1/imports/faculty/apply",
        data={"expected_preview_id": preview["preview_id"]},
        files={"file": ("faculty.xlsx", changed, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert mismatch.status_code == 409
    assert db_session.query(Faculty).count() == 0
    applied = client.post(
        "/api/v1/imports/faculty/apply",
        data={"expected_preview_id": preview["preview_id"]},
        files={"file": ("faculty.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert applied.status_code == 200
    assert applied.json()["imported_count"] == 2
    assert db_session.query(Faculty).count() == 2


def test_imported_records_survive_request_session_close_and_api_reload(client, test_engine):
    from sqlalchemy.orm import Session

    content = workbook_bytes(
        ["faculty_name", "faculty_code", "email"],
        [["Imported persistence check", "IMPORT-PERSIST-01", ""]],
    )
    preview = upload(client, "/api/v1/imports/faculty/preview", "faculty.xlsx", content).json()
    applied = client.post(
        "/api/v1/imports/faculty/apply",
        data={"expected_preview_id": preview["preview_id"]},
        files={"file": ("faculty.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert applied.status_code == 200

    with Session(test_engine) as reopened_session:
        record = reopened_session.query(Faculty).filter_by(faculty_code="IMPORT-PERSIST-01").one()
        assert record.faculty_name == "Imported persistence check"

    refreshed = client.get("/api/v1/faculty")
    assert refreshed.status_code == 200
    assert any(row["faculty_code"] == "IMPORT-PERSIST-01" for row in refreshed.json())


def test_semester_subject_preview_rejects_missing_foreign_keys(client):
    columns = ["semester_id", "student_group_id", "subject_id", "weekly_lecture_hours",
               "weekly_tutorial_hours", "weekly_practical_hours", "lecture_session_minutes",
               "tutorial_session_minutes", "practical_session_minutes"]
    content = workbook_bytes(columns, [[999, 998, 997, 3, 0, 0, None, None, None]])
    response = upload(client, "/api/v1/imports/semester-subjects/preview", "assignments.xlsx", content)
    assert response.status_code == 200
    assert response.json()["can_apply"] is False
    assert {error["column"] for error in response.json()["errors"]} >= {"semester_id", "student_group_id", "subject_id"}


def test_group_configuration_import_marks_group_protected_and_relationships_stay_valid(client, db_session):
    semester = make_cse_semester(db_session)
    columns = ["group_code", "semester_number", "academic_year_name", "group_name", "student_count"]
    content = workbook_bytes(columns, [["CSE-S1-A", 1, "2025-26", "S1-A", 60]])
    preview = upload(client, "/api/v1/imports/student-groups/preview", "groups.xlsx", content).json()
    assert preview["can_apply"] is True
    applied = client.post(
        "/api/v1/imports/student-groups/apply",
        data={"expected_preview_id": preview["preview_id"]},
        files={"file": ("groups.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert applied.status_code == 200
    listed = client.get("/api/v1/student-groups").json()
    assert listed == [{"id": listed[0]["id"], "semester_id": semester.id, "group_name": "S1-A",
                       "section_identifier": None, "student_count": 60, "is_active": True, "is_predefined": True}]
    group_id = listed[0]["id"]
    subject = client.post("/api/v1/subjects", json={"subject_code": "CS101", "subject_name": "Confirmed subject"})
    assert subject.status_code == 201
    assignment = client.post("/api/v1/semester-subjects", json={
        "semester_id": semester.id,
        "student_group_id": group_id,
        "subject_id": subject.json()["id"],
        "weekly_lecture_hours": 3,
    })
    assert assignment.status_code == 201
    assert client.get("/api/v1/student-groups").json()[0]["id"] == group_id
    assert client.patch(f"/api/v1/student-groups/{group_id}", json={"student_count": 72}).status_code == 409
    assert client.delete(f"/api/v1/student-groups/{group_id}").status_code == 409
    repeated = client.post(
        "/api/v1/imports/student-groups/apply",
        data={"expected_preview_id": preview["preview_id"]},
        files={"file": ("groups.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert repeated.status_code == 200
    assert len(client.get("/api/v1/student-groups").json()) == 1
