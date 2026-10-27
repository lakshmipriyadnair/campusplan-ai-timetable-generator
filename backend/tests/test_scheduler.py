from datetime import date, datetime, time, timezone
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import models
from app.predefined_groups import PredefinedGroupDefinition, configure_predefined_groups
from app.scheduler import generate_s5_alternatives, prepare_problem, solve_alternatives, validate_alternative


def add_base_data(db_session, *, period_count=3, lab=False, room_capacity=75, missing_hours=False):
    department = models.Department(name="Test CSE", code="CSE")
    year = models.AcademicYear(name="Test Year", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31))
    db_session.add_all([department, year]); db_session.flush()
    semester = models.Semester(department_id=department.id, academic_year_id=year.id, semester_number=5, name="S5")
    db_session.add(semester); db_session.flush()
    groups = configure_predefined_groups(db_session, [
        PredefinedGroupDefinition(group_code=f"TEST-S5-{section}", semester_number=5, academic_year_name=year.name,
                                  group_name=f"S5-{section}", student_count=72)
        for section in ("A", "B")
    ])
    subject = models.Subject(subject_code="TEST101", subject_name="Test subject")
    faculty = models.Faculty(faculty_name="Test teacher", faculty_code="TEST-T")
    room = models.Room(room_name="TEST-LAB" if lab else "TEST-ROOM", room_type="laboratory" if lab else "classroom", capacity=room_capacity)
    db_session.add_all([subject, faculty, room]); db_session.flush()
    requirement = models.SharedSubjectRequirement(
        semester_id=semester.id, subject_id=subject.id,
        weekly_lecture_hours=None if missing_hours else (0 if lab else 1),
        weekly_tutorial_hours=0, weekly_practical_hours=2 if lab else 0,
        weekly_lecture_sessions=None if missing_hours else (0 if lab else 1),
        weekly_tutorial_sessions=0, weekly_practical_sessions=1 if lab else 0,
        lecture_session_minutes=None if missing_hours or lab else 60,
        tutorial_session_minutes=None, practical_session_minutes=120 if lab else None,
    )
    db_session.add(requirement); db_session.flush()
    for group in groups:
        db_session.add(models.SectionTeacherAssignment(requirement_id=requirement.id, student_group_id=group.id, faculty_id=faculty.id))
    db_session.add(models.ActivityRoomRequirement(requirement_id=requirement.id, activity_type="practical" if lab else "lecture", room_type="laboratory" if lab else "classroom"))
    config = models.CollegeTimeConfiguration(version=1, is_active=True, academic_hour_minutes=60)
    db_session.add(config); db_session.flush()
    db_session.add(models.CollegeWorkingDay(configuration_id=config.id, weekday=0))
    for index in range(period_count):
        start = 8 * 60 + index * 60
        db_session.add(models.CollegeTimeBlock(
            configuration_id=config.id, sequence_number=index + 1, block_type="teaching",
            period_number=index + 1, start_time=time(start // 60, start % 60),
            end_time=time((start + 60) // 60, (start + 60) % 60), is_lab_compatible=lab,
        ))
    faculty_profile = models.FacultySchedulingProfile(faculty_id=faculty.id, is_confirmed=True, max_daily_minutes=600, max_weekly_minutes=600)
    room_profile = models.RoomAvailabilityProfile(room_id=room.id, is_confirmed=True)
    db_session.add_all([faculty_profile, room_profile]); db_session.flush()
    db_session.add(models.FacultyAvailabilityWindow(profile_id=faculty_profile.id, weekday=0, start_time=time(8), end_time=time(14), availability="available"))
    db_session.add(models.RoomAvailabilityWindow(profile_id=room_profile.id, weekday=0, start_time=time(8), end_time=time(14), availability="available"))
    if lab:
        db_session.add(models.RoomCapability(room_id=room.id, capability_name="GPU", capability_type="equipment"))
        activity_room = db_session.scalar(select(models.ActivityRoomRequirement).where(models.ActivityRoomRequirement.requirement_id == requirement.id))
        db_session.add(models.ActivityEquipmentRequirement(activity_requirement_id=activity_room.id, capability_name="GPU"))
    db_session.commit()
    return year, requirement


def test_shared_teacher_and_room_conflicts_are_prevented_and_alternatives_are_distinct(db_session):
    year, _ = add_base_data(db_session, period_count=3)
    result = generate_s5_alternatives(db_session, year.id, count=4)
    assert result["status"] == "success"
    assert 3 <= result["valid_count"] <= 4
    signatures = {
        tuple(sorted((session["group_name"], session["weekday"], tuple(session["period_numbers"]), session["room_id"], session["teacher_id"]) for session in alt["sessions"]))
        for alt in result["alternatives"]
    }
    assert len(signatures) == result["valid_count"]
    for alternative in result["alternatives"]:
        sessions = alternative["sessions"]
        assert len(sessions) == 2
        assert len({(item["weekday"], item["period_numbers"][0]) for item in sessions}) == 2
        assert all(item["validation"] == "valid" for item in [alternative])


def test_laboratory_uses_two_consecutive_lab_compatible_periods_and_equipment(db_session):
    year, _ = add_base_data(db_session, period_count=5, lab=True)
    result = generate_s5_alternatives(db_session, year.id, count=3)
    assert result["status"] == "success"
    assert result["valid_count"] == 3
    for alternative in result["alternatives"]:
        for session in alternative["sessions"]:
            assert session["activity_type"] == "practical"
            assert len(session["period_numbers"]) == 2
            assert session["period_numbers"][1] == session["period_numbers"][0] + 1


def test_too_few_periods_for_both_sections_is_infeasible_not_partial(db_session):
    year, _ = add_base_data(db_session, period_count=1)
    result = generate_s5_alternatives(db_session, year.id, count=3)
    assert result["status"] == "infeasible"
    assert result["valid_count"] == 0
    assert not result["alternatives"]
    assert result["diagnostics"]


def test_unknown_weekly_hours_block_generation_instead_of_becoming_zero(db_session):
    year, _ = add_base_data(db_session, missing_hours=True)
    result = generate_s5_alternatives(db_session, year.id, count=3)
    assert result["status"] == "incomplete"
    assert result["valid_count"] == 0
    assert any("weekly lecture hours are unconfirmed" in message for message in result["diagnostics"])


def test_room_capacity_mismatch_is_reported(db_session):
    year, _ = add_base_data(db_session, room_capacity=71)
    result = generate_s5_alternatives(db_session, year.id, count=3)
    assert result["status"] == "incomplete"
    assert any("no confirmed classroom has capacity 72" in message for message in result["diagnostics"])


def test_independent_validator_rejects_duplicate_group_and_teacher_slots(db_session):
    year, _ = add_base_data(db_session, period_count=3)
    problem, errors, _ = prepare_problem(db_session, year.id)
    assert not errors and problem is not None
    selected = [problem.candidates[index] for index in (problem.candidates_by_demand[problem.demands[0].key][0], problem.candidates_by_demand[problem.demands[1].key][0])]
    assert validate_alternative(problem, selected)


def test_generate_api_returns_validation_diagnostics(client, db_session):
    year, _ = add_base_data(db_session, missing_hours=True)
    response = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3})
    assert response.status_code == 200
    assert response.json()["status"] == "incomplete"
    assert response.json()["valid_count"] == 0


def _approve(client, year_id, alternative, *, confirm=True):
    return client.post("/api/v1/timetables/approve", json={
        "academic_year_id": year_id,
        "alternative_number": alternative["alternative_number"],
        "sessions": alternative["sessions"],
        "confirm_approval": confirm,
    })


def test_valid_alternative_is_revalidated_and_saved_as_immutable_approval(client, db_session):
    year, _ = add_base_data(db_session, period_count=3)
    generated = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3}).json()
    assert generated["status"] == "success"
    approved = _approve(client, year.id, generated["alternatives"][0])
    assert approved.status_code == 201, approved.text
    snapshot = approved.json()
    assert snapshot["status"] == "approved"
    assert snapshot["version"] == 1
    assert len(snapshot["sessions_json"]) == 2
    assert snapshot["configuration_json"]["working_days"] == [0]

    assert client.get(f"/api/v1/timetables/official?academic_year_id={year.id}").json() == []
    assert client.post(f"/api/v1/timetables/{snapshot['id']}/publish", json={"confirm_publish": True}).status_code == 200


def test_invalid_incomplete_or_changed_alternative_cannot_be_approved(client, db_session):
    year, _ = add_base_data(db_session, period_count=3)
    generated = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3}).json()
    changed = [dict(session) for session in generated["alternatives"][0]["sessions"]]
    changed[0]["teacher_name"] = "Changed after generation"
    rejected = client.post("/api/v1/timetables/approve", json={
        "academic_year_id": year.id, "alternative_number": 1, "sessions": changed, "confirm_approval": True,
    })
    assert rejected.status_code == 422
    assert "changed after generation" in str(rejected.json())
    incomplete = client.post("/api/v1/timetables/approve", json={
        "academic_year_id": year.id, "alternative_number": 1,
        "sessions": generated["alternatives"][0]["sessions"][:-1], "confirm_approval": True,
    })
    assert incomplete.status_code == 422
    assert client.get(f"/api/v1/timetables/approved?academic_year_id={year.id}").json() == []


def test_missing_required_data_blocks_approval(client, db_session):
    year, _ = add_base_data(db_session, missing_hours=True)
    generated = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3}).json()
    assert generated["status"] == "incomplete"
    response = client.post("/api/v1/timetables/approve", json={
        "academic_year_id": year.id, "alternative_number": 1, "sessions": [], "confirm_approval": True,
    })
    assert response.status_code == 422
    assert "weekly lecture hours are unconfirmed" in str(response.json())


def test_only_approved_selected_version_can_publish_and_republishing_keeps_history(client, db_session):
    year, _ = add_base_data(db_session, period_count=3)
    assert client.post("/api/v1/timetables/987654/publish", json={"confirm_publish": True}).status_code == 404
    generated = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3}).json()
    first = _approve(client, year.id, generated["alternatives"][0]).json()
    second = _approve(client, year.id, generated["alternatives"][1]).json()
    assert first["id"] != second["id"] and first["version"] == 1 and second["version"] == 2
    assert client.post(f"/api/v1/timetables/{first['id']}/publish", json={"confirm_publish": True}).status_code == 200
    assert client.post(f"/api/v1/timetables/{second['id']}/publish", json={"confirm_publish": True}).status_code == 200
    official = client.get(f"/api/v1/timetables/official?academic_year_id={year.id}").json()
    assert len(official) == 1
    assert official[0]["snapshot_id"] == second["id"] and official[0]["version"] == 2
    approvals = client.get(f"/api/v1/timetables/approved?academic_year_id={year.id}").json()
    assert {row["id"] for row in approvals} == {first["id"], second["id"]}
    history = client.get(f"/api/v1/timetables/publication-history?academic_year_id={year.id}").json()
    assert len(history) == 2
    assert any(row["snapshot_id"] == first["id"] and row["is_current"] is False for row in history)
    assert any(row["snapshot_id"] == second["id"] and row["is_current"] is True for row in history)


def test_generating_new_previews_never_changes_the_current_published_snapshot(client, db_session):
    year, _ = add_base_data(db_session, period_count=3)
    first_generation = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3}).json()
    approved = _approve(client, year.id, first_generation["alternatives"][0]).json()
    client.post(f"/api/v1/timetables/{approved['id']}/publish", json={"confirm_publish": True})
    official_before = client.get(f"/api/v1/timetables/official?academic_year_id={year.id}").json()
    next_preview = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3})
    assert next_preview.status_code == 200 and next_preview.json()["status"] == "success"
    official_after = client.get(f"/api/v1/timetables/official?academic_year_id={year.id}").json()
    assert official_after == official_before


def test_database_unique_current_pointer_prevents_concurrent_official_versions(db_session):
    year, _ = add_base_data(db_session, period_count=3)
    generated = generate_s5_alternatives(db_session, year.id, count=3)
    from app.scheduler import validate_submitted_alternative, serialize_candidate
    problem, selected, errors, _ = validate_submitted_alternative(db_session, year.id, generated["alternatives"][0]["sessions"])
    assert not errors and problem is not None
    snapshot = models.TimetableSnapshot(
        academic_year_id=year.id, semester_id=next(iter({db_session.get(models.SharedSubjectRequirement, d.requirement_id).semester_id for d in problem.demands})),
        semester_number=5, version=1, status="approved", alternative_number=1,
        sessions_json=[serialize_candidate(problem, item) for item in selected],
        configuration_json=problem.college_time_snapshot, validation_json=[],
        approved_at=datetime.now(timezone.utc), created_at=datetime.now(timezone.utc),
    )
    db_session.add(snapshot); db_session.flush()
    db_session.add(models.OfficialTimetable(academic_year_id=year.id, semester_id=snapshot.semester_id, snapshot_id=snapshot.id))
    db_session.commit()
    second = models.TimetableSnapshot(
        academic_year_id=year.id, semester_id=snapshot.semester_id, semester_number=5, version=2,
        status="approved", alternative_number=2, sessions_json=snapshot.sessions_json,
        configuration_json=snapshot.configuration_json, validation_json=[], approved_at=snapshot.approved_at,
        created_at=snapshot.created_at,
    )
    db_session.add(second); db_session.flush()
    db_session.add(models.OfficialTimetable(academic_year_id=year.id, semester_id=snapshot.semester_id, snapshot_id=second.id))
    try:
        db_session.commit()
        assert False, "unique current timetable constraint should reject a second current version"
    except IntegrityError:
        db_session.rollback()


def test_concurrent_publish_requests_leave_exactly_one_current_version(client, db_session):
    year, _ = add_base_data(db_session, period_count=3)
    generated = client.post("/api/v1/timetables/generate", json={"academic_year_id": year.id, "number_of_alternatives": 3}).json()
    first = _approve(client, year.id, generated["alternatives"][0]).json()
    second = _approve(client, year.id, generated["alternatives"][1]).json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda snapshot_id: client.post(
            f"/api/v1/timetables/{snapshot_id}/publish", json={"confirm_publish": True}
        ), [first["id"], second["id"]]))
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    official = client.get(f"/api/v1/timetables/official?academic_year_id={year.id}").json()
    assert len(official) == 1
    assert official[0]["snapshot_id"] in {first["id"], second["id"]}
