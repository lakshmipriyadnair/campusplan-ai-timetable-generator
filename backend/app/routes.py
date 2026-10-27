from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.crud import create_crud_router
from app.database import get_db
from app.imports import router as import_router
from app.predefined_groups import (
    PredefinedGroupConfigurationError,
    PredefinedGroupDefinition,
    configure_predefined_groups,
)
from app.scheduler import generate_s5_alternatives, serialize_candidate, validate_submitted_alternative


def validate_academic_year_update(record: Any, values: dict[str, Any]) -> None:
    start_date = values.get("start_date", record.start_date)
    end_date = values.get("end_date", record.end_date)
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date <= start_date:
        raise HTTPException(status_code=422, detail="end_date must be after start_date.")


def validate_group_subject_scope(
    db: Session, values: dict[str, Any], record: Any | None
) -> None:
    semester_id = values.get("semester_id", getattr(record, "semester_id", None))
    group_id = values.get("student_group_id", getattr(record, "student_group_id", None))
    group = db.get(models.StudentGroup, group_id)
    if group is not None and group.semester_id != semester_id:
        raise HTTPException(
            status_code=422,
            detail="The selected student group must belong to the selected semester.",
        )
    semester = db.get(models.Semester, semester_id) if semester_id is not None else None
    department = db.get(models.Department, semester.department_id) if semester else None
    subject_id = values.get("subject_id", getattr(record, "subject_id", None))
    if (
        semester is not None
        and semester.semester_number == 5
        and department is not None
        and (department.code == "CSE" or department.name == "CSE")
        and db.query(models.SharedSubjectRequirement.id).filter(
            models.SharedSubjectRequirement.semester_id == semester.id,
            models.SharedSubjectRequirement.subject_id == subject_id,
        ).first()
    ):
        raise HTTPException(
            status_code=409,
            detail="A shared S5 requirement already exists for this subject. Use the section-specific teacher assignment instead of a duplicate weekly-hours record.",
        )


def protect_predefined_student_group(db: Session, record: models.StudentGroup) -> None:
    identity = db.get(models.PredefinedStudentGroup, record.id)
    if identity is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "This student group is predefined and cannot be changed or deleted "
                "through ordinary academic-data endpoints."
            ),
        )


def _require_cse_s5(db: Session, semester_id: int | None) -> None:
    semester = db.get(models.Semester, semester_id) if semester_id is not None else None
    department = db.get(models.Department, semester.department_id) if semester else None

    if (
        semester is None
        or int(semester.semester_number) != 5
        or department is None
        or (department.code != "CSE" and department.name != "CSE")
    ):
        raise HTTPException(
            status_code=422,
            detail="This record must belong to a CSE S5 semester.",
        )


def validate_shared_requirement(db: Session, values: dict[str, Any], record: Any | None) -> None:
    semester_id = values.get("semester_id", getattr(record, "semester_id", None))
    _require_cse_s5(db, semester_id)
    subject_id = values.get("subject_id", getattr(record, "subject_id", None))
    if record is None and db.query(models.SemesterSubject.id).filter(
        models.SemesterSubject.semester_id == semester_id,
        models.SemesterSubject.subject_id == subject_id,
    ).first():
        raise HTTPException(
            status_code=409,
            detail="Legacy per-group S5 subject records already exist. Review them manually before creating one shared requirement; no records were merged.",
        )
    for activity in ("lecture", "tutorial", "practical"):
        hours = values.get(f"weekly_{activity}_hours", getattr(record, f"weekly_{activity}_hours", None))
        sessions = values.get(f"weekly_{activity}_sessions", getattr(record, f"weekly_{activity}_sessions", None))
        if hours is not None and sessions is not None and ((hours == 0) != (sessions == 0)):
            raise HTTPException(
                status_code=422,
                detail=f"Confirmed zero {activity} hours must pair with zero sessions; positive hours require a positive session count.",
            )


def validate_section_teacher_assignment(db: Session, values: dict[str, Any], record: Any | None) -> None:
    requirement_id = values.get("requirement_id", getattr(record, "requirement_id", None))
    group_id = values.get("student_group_id", getattr(record, "student_group_id", None))
    requirement = db.get(models.SharedSubjectRequirement, requirement_id) if requirement_id else None
    group = db.get(models.StudentGroup, group_id) if group_id else None
    if requirement is None or group is None:
        return  # The generic reference validator returns the appropriate 404.
    _require_cse_s5(db, requirement.semester_id)
    if group.semester_id != requirement.semester_id or group.group_name not in {"S5-A", "S5-B"}:
        raise HTTPException(status_code=422, detail="Teacher assignments must target S5-A or S5-B in the requirement's semester.")
    if group.predefined_identity is None:
        raise HTTPException(status_code=422, detail="S5-A and S5-B must be configured as protected predefined groups first.")


def validate_time_block(db: Session, values: dict[str, Any], record: Any | None) -> None:
    configuration_id = values.get("configuration_id", getattr(record, "configuration_id", None))
    start_time = values.get("start_time", getattr(record, "start_time", None))
    end_time = values.get("end_time", getattr(record, "end_time", None))
    block_type = values.get("block_type", getattr(record, "block_type", None))
    period_number = values.get("period_number", getattr(record, "period_number", None))
    label = values.get("label", getattr(record, "label", None))
    lab_compatible = values.get("is_lab_compatible", getattr(record, "is_lab_compatible", False))
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time.")
    if block_type == "teaching" and period_number is None:
        raise HTTPException(status_code=422, detail="Teaching blocks require a period_number.")
    if block_type != "teaching" and lab_compatible:
        raise HTTPException(status_code=422, detail="Only teaching periods can be laboratory-compatible.")
    if block_type == "teaching" and label and label.strip().upper() in {"Z", "PERIOD Z"}:
        raise HTTPException(status_code=422, detail="Period Z is not supported.")
    if start_time is None or end_time is None:
        return
    for other in db.query(models.CollegeTimeBlock).filter(
        models.CollegeTimeBlock.configuration_id == configuration_id
    ):
        if record is not None and other.id == record.id:
            continue
        if start_time < other.end_time and other.start_time < end_time:
            raise HTTPException(status_code=422, detail="College time blocks cannot overlap.")
        sequence = values.get("sequence_number", getattr(record, "sequence_number", None))
        if sequence is not None:
            if sequence < other.sequence_number and end_time > other.start_time:
                raise HTTPException(status_code=422, detail="Time blocks must follow their configured sequence.")
            if sequence > other.sequence_number and start_time < other.end_time:
                raise HTTPException(status_code=422, detail="Time blocks must follow their configured sequence.")


def validate_room_availability_profile(db: Session, values: dict[str, Any], record: Any | None) -> None:
    confirmed = values.get("is_confirmed", getattr(record, "is_confirmed", False))
    profile_id = getattr(record, "id", None)
    room_id = values.get("room_id", getattr(record, "room_id", None))
    if confirmed and profile_id is not None:
        has_window = db.query(models.RoomAvailabilityWindow.id).filter(
            models.RoomAvailabilityWindow.profile_id == profile_id,
            models.RoomAvailabilityWindow.availability == "available",
        ).first()
        if has_window is None:
            raise HTTPException(status_code=422, detail="Add at least one available time window before confirming room availability.")
    elif confirmed and profile_id is None:
        raise HTTPException(status_code=422, detail="Save the room profile and add available time windows before confirming it.")
    if room_id is not None and db.query(models.RoomAvailabilityProfile.id).filter(
        models.RoomAvailabilityProfile.room_id == room_id,
        models.RoomAvailabilityProfile.id != (profile_id or -1),
    ).first():
        raise HTTPException(status_code=422, detail="This room already has an availability profile.")


def validate_room_availability_window(db: Session, values: dict[str, Any], record: Any | None) -> None:
    profile_id = values.get("profile_id", getattr(record, "profile_id", None))
    weekday = values.get("weekday", getattr(record, "weekday", None))
    start_time = values.get("start_time", getattr(record, "start_time", None))
    end_time = values.get("end_time", getattr(record, "end_time", None))
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time.")
    for other in db.query(models.RoomAvailabilityWindow).filter(
        models.RoomAvailabilityWindow.profile_id == profile_id,
        models.RoomAvailabilityWindow.weekday == weekday,
    ):
        if record is not None and other.id == record.id:
            continue
        if start_time < other.end_time and other.start_time < end_time:
            raise HTTPException(status_code=422, detail="Room availability windows on the same day cannot overlap.")


def validate_faculty_scheduling_profile(db: Session, values: dict[str, Any], record: Any | None) -> None:
    confirmed = values.get("is_confirmed", getattr(record, "is_confirmed", False))
    profile_id = getattr(record, "id", None)
    daily_limit = values.get("max_daily_minutes", getattr(record, "max_daily_minutes", None))
    weekly_limit = values.get("max_weekly_minutes", getattr(record, "max_weekly_minutes", None))
    faculty_id = values.get("faculty_id", getattr(record, "faculty_id", None))
    if confirmed:
        if daily_limit is None or weekly_limit is None:
            raise HTTPException(status_code=422, detail="Enter confirmed daily and weekly workload limits before confirming faculty scheduling data.")
        if profile_id is None:
            raise HTTPException(status_code=422, detail="Save the profile and availability windows before confirming faculty scheduling data.")
        if db.query(models.FacultyAvailabilityWindow.id).filter(
            models.FacultyAvailabilityWindow.profile_id == profile_id,
            models.FacultyAvailabilityWindow.availability == "available",
        ).first() is None:
            raise HTTPException(status_code=422, detail="Add at least one available time window before confirming faculty scheduling data.")
    if faculty_id is not None and db.query(models.FacultySchedulingProfile.id).filter(
        models.FacultySchedulingProfile.faculty_id == faculty_id,
        models.FacultySchedulingProfile.id != (profile_id or -1),
    ).first():
        raise HTTPException(status_code=422, detail="This faculty member already has a scheduling profile.")


def validate_faculty_availability_window(db: Session, values: dict[str, Any], record: Any | None) -> None:
    profile_id = values.get("profile_id", getattr(record, "profile_id", None))
    weekday = values.get("weekday", getattr(record, "weekday", None))
    start_time = values.get("start_time", getattr(record, "start_time", None))
    end_time = values.get("end_time", getattr(record, "end_time", None))
    if start_time is not None and end_time is not None and end_time <= start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time.")
    for other in db.query(models.FacultyAvailabilityWindow).filter(
        models.FacultyAvailabilityWindow.profile_id == profile_id,
        models.FacultyAvailabilityWindow.weekday == weekday,
    ):
        if record is not None and other.id == record.id:
            continue
        if start_time < other.end_time and other.start_time < end_time:
            raise HTTPException(status_code=422, detail="Faculty availability windows on the same day cannot overlap.")


api_router = APIRouter(prefix="/api/v1")
api_router.include_router(import_router)


@api_router.post("/predefined-groups/configure-s5", status_code=201, tags=["Student groups"])
def configure_s5_groups(
    request: schemas.S5GroupConfigurationRequest,
    db: Session = Depends(get_db),
) -> list[schemas.StudentGroupRead]:
    """Create or verify the known protected S5-A/S5-B groups without editing existing data."""
    definitions = [
        PredefinedGroupDefinition(
            group_code=f"CSE-S5-{section}", semester_number=5,
            academic_year_name=request.academic_year_name,
            group_name=f"S5-{section}", student_count=72,
        )
        for section in ("A", "B")
    ]
    try:
        groups = configure_predefined_groups(db, definitions)
    except PredefinedGroupConfigurationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [schemas.StudentGroupRead.model_validate(group) for group in groups]


@api_router.post("/timetables/generate", tags=["Timetable generation"])
def generate_timetables(
    request: schemas.TimetableGenerationRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate transient S5 alternatives; this endpoint never stores or publishes them."""
    return generate_s5_alternatives(
        db,
        academic_year_id=request.academic_year_id,
        count=request.number_of_alternatives,
    )


@api_router.post("/timetables/approve", status_code=201, tags=["Timetable approval"])
def approve_timetable(request: schemas.TimetableApprovalRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Revalidate a selected preview and store an immutable approved snapshot."""
    problem, candidates, diagnostics, _warnings = validate_submitted_alternative(
        db, request.academic_year_id, request.sessions
    )
    if diagnostics or problem is None:
        raise HTTPException(status_code=422, detail={"message": "This alternative cannot be approved.", "diagnostics": diagnostics})
    # Serialize version allocation in SQLite; the unique semester/version constraint is a second guard.
    db.execute(text("BEGIN IMMEDIATE"))
    try:
        semester_ids = {next(d for d in problem.demands if d.key == c.demand_key).requirement_id for c in candidates}
        requirement_ids = {db.get(models.SharedSubjectRequirement, rid).semester_id for rid in semester_ids}
        if len(requirement_ids) != 1:
            raise HTTPException(status_code=422, detail="The alternative must cover exactly one semester.")
        semester_id = next(iter(requirement_ids))
        semester = db.get(models.Semester, semester_id)
        version = (db.scalar(select(models.TimetableSnapshot.version).where(models.TimetableSnapshot.semester_id == semester_id).order_by(models.TimetableSnapshot.version.desc()).limit(1)) or 0) + 1
        canonical = [serialize_candidate(problem, candidate) for candidate in candidates]
        now = datetime.now(timezone.utc)
        snapshot = models.TimetableSnapshot(
            academic_year_id=request.academic_year_id, semester_id=semester_id,
            semester_number=semester.semester_number, version=version,
            status="approved", alternative_number=request.alternative_number,
            sessions_json=canonical, configuration_json=problem.college_time_snapshot,
            validation_json=[], approved_at=now, created_at=now,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return schemas.TimetableSnapshotRead.model_validate(snapshot).model_dump(mode="json")
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="An approval with this version was created concurrently. Refresh and try again.") from error
    except Exception:
        db.rollback()
        raise


@api_router.get("/timetables/approved", tags=["Timetable approval"])
def list_approved_timetables(academic_year_id: int = Query(gt=0), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(models.TimetableSnapshot).where(
        models.TimetableSnapshot.academic_year_id == academic_year_id
    ).order_by(models.TimetableSnapshot.approved_at.desc())).all()
    return [schemas.TimetableSnapshotRead.model_validate(row).model_dump(mode="json") for row in rows]


@api_router.post("/timetables/{snapshot_id}/publish", tags=["Timetable publication"])
def publish_timetable(snapshot_id: int, request: schemas.TimetablePublishRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Atomically switch the official pointer and append publication history."""
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        snapshot = db.get(models.TimetableSnapshot, snapshot_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Approved timetable not found.")
        if snapshot.status != "approved":
            raise HTTPException(status_code=409, detail="Only an approved timetable can be published.")
        current = db.scalar(select(models.OfficialTimetable).where(models.OfficialTimetable.semester_id == snapshot.semester_id))
        previous_id = current.snapshot_id if current else None
        if previous_id == snapshot.id:
            raise HTTPException(status_code=409, detail="This version is already the official published timetable.")
        now = datetime.now(timezone.utc)
        if current:
            current.snapshot_id = snapshot.id
            current.academic_year_id = snapshot.academic_year_id
            current.published_at = now
        else:
            current = models.OfficialTimetable(
                academic_year_id=snapshot.academic_year_id, semester_id=snapshot.semester_id,
                snapshot_id=snapshot.id, published_at=now,
            )
            db.add(current)
        db.add(models.TimetablePublicationEvent(
            academic_year_id=snapshot.academic_year_id, semester_id=snapshot.semester_id,
            snapshot_id=snapshot.id, previous_snapshot_id=previous_id, published_at=now,
        ))
        db.commit()
        return {"status": "published", "snapshot_id": snapshot.id, "version": snapshot.version, "published_at": now.isoformat()}
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Publication changed concurrently. Refresh and retry.") from error
    except Exception:
        db.rollback()
        raise


@api_router.get("/timetables/official", tags=["Official timetable viewer"])
def get_official_timetables(academic_year_id: int = Query(gt=0), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """Viewer endpoint exposes only the current official publication, never previews or approvals."""
    rows = db.execute(
        select(models.OfficialTimetable, models.TimetableSnapshot)
        .join(models.TimetableSnapshot, models.TimetableSnapshot.id == models.OfficialTimetable.snapshot_id)
        .join(models.Semester, models.Semester.id == models.OfficialTimetable.semester_id)
        .join(models.Department, models.Department.id == models.Semester.department_id)
        .where(models.OfficialTimetable.academic_year_id == academic_year_id,
               models.Semester.semester_number == 5,
               (models.Department.code == "CSE") | (models.Department.name == "CSE"))
    ).all()
    return [{
        "snapshot_id": snapshot.id, "academic_year_id": snapshot.academic_year_id,
        "semester_id": snapshot.semester_id, "semester_number": snapshot.semester_number,
        "version": snapshot.version, "status": "published", "published_at": official.published_at,
        "sessions": snapshot.sessions_json, "configuration": snapshot.configuration_json,
    } for official, snapshot in rows]


@api_router.get("/timetables/publication-history", tags=["Timetable approval"])
def publication_history(academic_year_id: int = Query(gt=0), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.execute(select(models.TimetablePublicationEvent, models.TimetableSnapshot)
        .join(models.TimetableSnapshot, models.TimetableSnapshot.id == models.TimetablePublicationEvent.snapshot_id)
        .where(models.TimetablePublicationEvent.academic_year_id == academic_year_id)
        .order_by(models.TimetablePublicationEvent.published_at.desc())).all()
    return [{"id": event.id, "snapshot_id": snapshot.id, "version": snapshot.version,
             "previous_snapshot_id": event.previous_snapshot_id, "published_at": event.published_at,
             "is_current": db.scalar(select(models.OfficialTimetable.id).where(models.OfficialTimetable.snapshot_id == snapshot.id)) is not None}
            for event, snapshot in rows]

api_router.include_router(create_crud_router(
    path="/departments", tag="Departments", model=models.Department,
    create_schema=schemas.DepartmentCreate, update_schema=schemas.DepartmentUpdate,
    read_schema=schemas.DepartmentRead,
))

# These additive resources keep shared S5 requirements separate from the
# legacy per-group SemesterSubject records. They are intentionally not backfilled.
api_router.include_router(create_crud_router(
    path="/shared-subject-requirements", tag="Shared S5 subject requirements",
    model=models.SharedSubjectRequirement,
    create_schema=schemas.SharedSubjectRequirementCreate,
    update_schema=schemas.SharedSubjectRequirementUpdate,
    read_schema=schemas.SharedSubjectRequirementRead,
    references={"semester_id": models.Semester, "subject_id": models.Subject},
    validate_values=validate_shared_requirement,
))
api_router.include_router(create_crud_router(
    path="/section-teacher-assignments", tag="S5 section teacher assignments",
    model=models.SectionTeacherAssignment,
    create_schema=schemas.SectionTeacherAssignmentCreate,
    update_schema=schemas.SectionTeacherAssignmentUpdate,
    read_schema=schemas.SectionTeacherAssignmentRead,
    references={
        "requirement_id": models.SharedSubjectRequirement,
        "student_group_id": models.StudentGroup,
        "faculty_id": models.Faculty,
    },
    validate_values=validate_section_teacher_assignment,
))
api_router.include_router(create_crud_router(
    path="/activity-room-requirements", tag="Activity room requirements",
    model=models.ActivityRoomRequirement,
    create_schema=schemas.ActivityRoomRequirementCreate,
    update_schema=schemas.ActivityRoomRequirementUpdate,
    read_schema=schemas.ActivityRoomRequirementRead,
    references={"requirement_id": models.SharedSubjectRequirement},
))
api_router.include_router(create_crud_router(
    path="/activity-equipment-requirements", tag="Activity equipment requirements",
    model=models.ActivityEquipmentRequirement,
    create_schema=schemas.ActivityEquipmentRequirementCreate,
    update_schema=schemas.ActivityEquipmentRequirementUpdate,
    read_schema=schemas.ActivityEquipmentRequirementRead,
    references={"activity_requirement_id": models.ActivityRoomRequirement},
))
api_router.include_router(create_crud_router(
    path="/faculty-scheduling-profiles", tag="Faculty scheduling profiles",
    model=models.FacultySchedulingProfile,
    create_schema=schemas.FacultySchedulingProfileCreate,
    update_schema=schemas.FacultySchedulingProfileUpdate,
    read_schema=schemas.FacultySchedulingProfileRead,
    references={"faculty_id": models.Faculty},
    validate_values=validate_faculty_scheduling_profile,
))
api_router.include_router(create_crud_router(
    path="/faculty-availability-windows", tag="Faculty availability windows",
    model=models.FacultyAvailabilityWindow,
    create_schema=schemas.FacultyAvailabilityWindowCreate,
    update_schema=schemas.FacultyAvailabilityWindowUpdate,
    read_schema=schemas.FacultyAvailabilityWindowRead,
    references={"profile_id": models.FacultySchedulingProfile},
    validate_values=validate_faculty_availability_window,
))
api_router.include_router(create_crud_router(
    path="/college-time-configurations", tag="College time configurations",
    model=models.CollegeTimeConfiguration,
    create_schema=schemas.CollegeTimeConfigurationCreate,
    update_schema=schemas.CollegeTimeConfigurationUpdate,
    read_schema=schemas.CollegeTimeConfigurationRead,
))
api_router.include_router(create_crud_router(
    path="/college-working-days", tag="College working days",
    model=models.CollegeWorkingDay,
    create_schema=schemas.CollegeWorkingDayCreate,
    update_schema=schemas.CollegeWorkingDayUpdate,
    read_schema=schemas.CollegeWorkingDayRead,
    references={"configuration_id": models.CollegeTimeConfiguration},
))
api_router.include_router(create_crud_router(
    path="/college-time-blocks", tag="College time blocks",
    model=models.CollegeTimeBlock,
    create_schema=schemas.CollegeTimeBlockCreate,
    update_schema=schemas.CollegeTimeBlockUpdate,
    read_schema=schemas.CollegeTimeBlockRead,
    references={"configuration_id": models.CollegeTimeConfiguration},
    validate_values=validate_time_block,
))
api_router.include_router(create_crud_router(
    path="/room-capabilities", tag="Room equipment and capabilities",
    model=models.RoomCapability,
    create_schema=schemas.RoomCapabilityCreate,
    update_schema=schemas.RoomCapabilityUpdate,
    read_schema=schemas.RoomCapabilityRead,
    references={"room_id": models.Room},
))
api_router.include_router(create_crud_router(
    path="/room-availability-profiles", tag="Room availability profiles",
    model=models.RoomAvailabilityProfile,
    create_schema=schemas.RoomAvailabilityProfileCreate,
    update_schema=schemas.RoomAvailabilityProfileUpdate,
    read_schema=schemas.RoomAvailabilityProfileRead,
    references={"room_id": models.Room},
    validate_values=validate_room_availability_profile,
))
api_router.include_router(create_crud_router(
    path="/room-availability-windows", tag="Room availability windows",
    model=models.RoomAvailabilityWindow,
    create_schema=schemas.RoomAvailabilityWindowCreate,
    update_schema=schemas.RoomAvailabilityWindowUpdate,
    read_schema=schemas.RoomAvailabilityWindowRead,
    references={"profile_id": models.RoomAvailabilityProfile},
    validate_values=validate_room_availability_window,
))
api_router.include_router(create_crud_router(
    path="/academic-years", tag="Academic years", model=models.AcademicYear,
    create_schema=schemas.AcademicYearCreate, update_schema=schemas.AcademicYearUpdate,
    read_schema=schemas.AcademicYearRead, validate_update=validate_academic_year_update,
))
api_router.include_router(create_crud_router(
    path="/semesters", tag="Semesters", model=models.Semester,
    create_schema=schemas.SemesterCreate, update_schema=schemas.SemesterUpdate,
    read_schema=schemas.SemesterRead,
    references={"department_id": models.Department, "academic_year_id": models.AcademicYear},
))
api_router.include_router(create_crud_router(
    path="/student-groups", tag="Student groups", model=models.StudentGroup,
    create_schema=schemas.StudentGroupCreate, update_schema=schemas.StudentGroupUpdate,
    read_schema=schemas.StudentGroupRead,
    references={"semester_id": models.Semester},
    protect_record=protect_predefined_student_group,
))
api_router.include_router(create_crud_router(
    path="/faculty", tag="Faculty", model=models.Faculty,
    create_schema=schemas.FacultyCreate, update_schema=schemas.FacultyUpdate,
    read_schema=schemas.FacultyRead,
))
api_router.include_router(create_crud_router(
    path="/rooms", tag="Rooms", model=models.Room,
    create_schema=schemas.RoomCreate, update_schema=schemas.RoomUpdate,
    read_schema=schemas.RoomRead,
))
api_router.include_router(create_crud_router(
    path="/subjects", tag="Subjects", model=models.Subject,
    create_schema=schemas.SubjectCreate, update_schema=schemas.SubjectUpdate,
    read_schema=schemas.SubjectRead,
))
api_router.include_router(create_crud_router(
    path="/semester-subjects", tag="Semester subjects", model=models.SemesterSubject,
    create_schema=schemas.SemesterSubjectCreate, update_schema=schemas.SemesterSubjectUpdate,
    read_schema=schemas.SemesterSubjectRead,
    references={
        "semester_id": models.Semester,
        "student_group_id": models.StudentGroup,
        "subject_id": models.Subject,
    },
    validate_values=validate_group_subject_scope,
))
api_router.include_router(create_crud_router(
    path="/faculty-subjects", tag="Faculty subject assignments", model=models.FacultySubject,
    create_schema=schemas.FacultySubjectCreate, update_schema=schemas.FacultySubjectUpdate,
    read_schema=schemas.FacultySubjectRead,
    references={"faculty_id": models.Faculty, "semester_subject_id": models.SemesterSubject},
))
