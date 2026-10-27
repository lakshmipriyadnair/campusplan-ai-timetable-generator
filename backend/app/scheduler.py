from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import time
import random
from typing import Any

from ortools.sat.python import cp_model
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
ACTIVITIES = (
    ("lecture", "weekly_lecture_hours", "weekly_lecture_sessions", "lecture_session_minutes"),
    ("tutorial", "weekly_tutorial_hours", "weekly_tutorial_sessions", "tutorial_session_minutes"),
    ("practical", "weekly_practical_hours", "weekly_practical_sessions", "practical_session_minutes"),
)


@dataclass(frozen=True)
class Slot:
    weekday: int
    period_number: int
    sequence_number: int
    start_minute: int
    end_minute: int
    is_lab_compatible: bool

    @property
    def key(self) -> tuple[int, int]:
        return self.weekday, self.period_number


@dataclass(frozen=True)
class Demand:
    key: str
    requirement_id: int
    group_id: int
    group_name: str
    student_count: int
    subject_code: str
    subject_name: str
    activity_type: str
    session_index: int
    duration_minutes: int
    academic_year_id: int
    teacher_id: int
    teacher_name: str
    room_type: str
    equipment: frozenset[str]


@dataclass(frozen=True)
class Candidate:
    demand_key: str
    weekday: int
    slots: tuple[Slot, ...]
    room_id: int
    room_name: str
    teacher_id: int
    start_minute: int
    end_minute: int

    @property
    def slot_keys(self) -> tuple[tuple[int, int], ...]:
        return tuple(slot.key for slot in self.slots)


@dataclass
class PreparedProblem:
    demands: list[Demand]
    candidates: list[Candidate]
    candidates_by_demand: dict[str, list[int]]
    periods: list[Slot]
    working_days: list[int]
    rooms: dict[int, models.Room]
    faculties: dict[int, models.Faculty]
    room_windows: dict[int, list[models.RoomAvailabilityWindow]]
    faculty_windows: dict[int, list[models.FacultyAvailabilityWindow]]
    faculty_daily_limits: dict[int, int]
    faculty_weekly_limits: dict[int, int]
    room_capabilities: dict[int, set[str]]
    academic_year_id: int
    college_time_snapshot: dict[str, Any]


def _minute(value: time) -> int:
    return value.hour * 60 + value.minute


def _within_window(start: int, end: int, weekday: int, windows: list[Any]) -> bool:
    matching = [window for window in windows if window.weekday == weekday]
    available = [window for window in matching if window.availability == "available"]
    denied = [window for window in matching if window.availability == "unavailable"]
    return any(_minute(window.start_time) <= start and end <= _minute(window.end_time) for window in available) and not any(
        start < _minute(window.end_time) and _minute(window.start_time) < end for window in denied
    )


def prepare_problem(db: Session, academic_year_id: int) -> tuple[PreparedProblem | None, list[str], list[str]]:
    """Validate inputs without defaults and build legal session placements."""
    errors: list[str] = []
    warnings: list[str] = []
    departments = db.scalars(
        select(models.Department).where(
            (models.Department.code == "CSE") | (models.Department.name == "CSE")
        )
    ).all()
    department_ids = {department.id for department in departments}
    semesters = db.scalars(
        select(models.Semester).where(
            models.Semester.department_id.in_(department_ids or {-1}),
            models.Semester.academic_year_id == academic_year_id,
            models.Semester.semester_number == 5,
        )
    ).all()
    if len(semesters) != 1:
        errors.append(f"Expected exactly one CSE Semester 5 record for academic year {academic_year_id}; found {len(semesters)}.")
        return None, errors, warnings
    semester = semesters[0]

    groups = db.scalars(select(models.StudentGroup).where(models.StudentGroup.semester_id == semester.id)).all()
    group_map: dict[str, models.StudentGroup] = {}
    for name in ("S5-A", "S5-B"):
        matches = [group for group in groups if group.group_name == name]
        if len(matches) != 1:
            errors.append(f"{name}: expected exactly one group in the selected CSE S5 academic year; found {len(matches)}.")
            continue
        group = matches[0]
        if group.predefined_identity is None:
            errors.append(f"{name}: group is not protected as a predefined section.")
        elif group.student_count != 72:
            errors.append(f"{name}: expected the confirmed fixed count of 72 students; found {group.student_count}.")
        else:
            group_map[name] = group

    configs = db.scalars(select(models.CollegeTimeConfiguration).where(models.CollegeTimeConfiguration.is_active.is_(True))).all()
    if len(configs) != 1:
        errors.append(f"Expected exactly one active college time configuration; found {len(configs)}.")
        return None, errors, warnings
    config = configs[0]
    if config.academic_hour_minutes is None:
        errors.append("Academic-hour length is unconfirmed. Enter the confirmed minutes per weekly academic hour.")
    working_days = sorted({row.weekday for row in db.scalars(select(models.CollegeWorkingDay).where(models.CollegeWorkingDay.configuration_id == config.id)).all()})
    if not working_days:
        errors.append("No college working days are configured in the active time configuration.")
    blocks = db.scalars(
        select(models.CollegeTimeBlock).where(models.CollegeTimeBlock.configuration_id == config.id).order_by(models.CollegeTimeBlock.sequence_number)
    ).all()
    for block in blocks:
        if _minute(block.start_time) >= _minute(block.end_time):
            errors.append(f"College time block '{block.label}' must end after it starts.")
    for previous, current in zip(blocks, blocks[1:]):
        if _minute(previous.end_time) > _minute(current.start_time):
            errors.append(f"College time blocks '{previous.label}' and '{current.label}' overlap or are out of chronological order.")
    teaching = [block for block in blocks if block.block_type == "teaching"]
    if not teaching:
        errors.append("No teaching periods are configured in the active time configuration.")
    if any(block.label and block.label.strip().upper() in {"Z", "PERIOD Z"} for block in teaching):
        errors.append("Period Z is not supported; remove it from the college time configuration.")
    periods = [
        Slot(-1, int(block.period_number), int(block.sequence_number), _minute(block.start_time), _minute(block.end_time), bool(block.is_lab_compatible))
        for block in teaching if block.period_number is not None
    ]
    if len(periods) != len(teaching):
        errors.append("Every teaching period must have a confirmed period number.")
    if [slot.period_number for slot in periods] != list(range(1, len(periods) + 1)):
        errors.append("Teaching periods must be numbered consecutively starting at Period 1.")

    requirements = db.scalars(select(models.SharedSubjectRequirement).where(models.SharedSubjectRequirement.semester_id == semester.id)).all()
    if not requirements:
        errors.append("No shared S5 subject requirements have been entered.")

    all_rooms = db.scalars(select(models.Room).where(models.Room.is_active.is_(True))).all()
    room_profiles = db.scalars(select(models.RoomAvailabilityProfile)).all()
    room_profile_by_id = {profile.room_id: profile for profile in room_profiles}
    room_windows: dict[int, list[models.RoomAvailabilityWindow]] = {}
    eligible_rooms: dict[int, models.Room] = {}
    for room in all_rooms:
        profile = room_profile_by_id.get(room.id)
        if profile is None or not profile.is_confirmed:
            warnings.append(f"Room {room.room_name} excluded because its availability is not confirmed.")
            continue
        windows = db.scalars(select(models.RoomAvailabilityWindow).where(models.RoomAvailabilityWindow.profile_id == profile.id)).all()
        if not any(window.availability == "available" for window in windows):
            warnings.append(f"Room {room.room_name} excluded because no available time window is recorded.")
            continue
        room_windows[room.id] = list(windows)
        eligible_rooms[room.id] = room

    faculty_ids = {
        assignment.faculty_id
        for assignment in db.scalars(
            select(models.SectionTeacherAssignment)
            .join(models.SharedSubjectRequirement)
            .where(models.SharedSubjectRequirement.semester_id == semester.id)
        ).all()
    }
    faculty_map = {faculty.id: faculty for faculty in db.scalars(select(models.Faculty).where(models.Faculty.id.in_(faculty_ids or {-1}), models.Faculty.is_active.is_(True))).all()}
    profiles = db.scalars(select(models.FacultySchedulingProfile).where(models.FacultySchedulingProfile.faculty_id.in_(faculty_map.keys() or {-1}))).all()
    profile_by_faculty = {profile.faculty_id: profile for profile in profiles}
    faculty_windows: dict[int, list[models.FacultyAvailabilityWindow]] = {}
    faculty_daily_limits: dict[int, int] = {}
    faculty_weekly_limits: dict[int, int] = {}
    for faculty_id, faculty in faculty_map.items():
        profile = profile_by_faculty.get(faculty_id)
        if profile is None or not profile.is_confirmed:
            errors.append(f"{faculty.faculty_name}: availability and workload limits are not confirmed.")
            continue
        if profile.max_daily_minutes is None or profile.max_weekly_minutes is None:
            errors.append(f"{faculty.faculty_name}: confirmed daily and weekly workload limits are required.")
            continue
        windows = db.scalars(select(models.FacultyAvailabilityWindow).where(models.FacultyAvailabilityWindow.profile_id == profile.id)).all()
        if not any(window.availability == "available" for window in windows):
            errors.append(f"{faculty.faculty_name}: add at least one available time window.")
            continue
        faculty_windows[faculty_id] = list(windows)
        faculty_daily_limits[faculty_id] = profile.max_daily_minutes
        faculty_weekly_limits[faculty_id] = profile.max_weekly_minutes

    room_capabilities: dict[int, set[str]] = defaultdict(set)
    for capability in db.scalars(select(models.RoomCapability).where(models.RoomCapability.capability_type.in_(["equipment", "capability"]))).all():
        room_capabilities[capability.room_id].add(capability.capability_name.strip().casefold())

    assignments = db.scalars(
        select(models.SectionTeacherAssignment)
        .join(models.SharedSubjectRequirement)
        .where(models.SharedSubjectRequirement.semester_id == semester.id)
    ).all()
    assignment_map: dict[tuple[int, int], list[models.SectionTeacherAssignment]] = defaultdict(list)
    for assignment in assignments:
        assignment_map[(assignment.requirement_id, assignment.student_group_id)].append(assignment)

    demand_records: list[tuple[Demand, models.ActivityRoomRequirement]] = []
    for requirement in requirements:
        subject = db.get(models.Subject, requirement.subject_id)
        if subject is None or not subject.is_active:
            errors.append(f"Requirement {requirement.id}: subject record is missing or inactive.")
            continue
        activity_room_by_type = {item.activity_type: item for item in requirement.activity_room_requirements}
        for group_name, group in group_map.items():
            assigned = assignment_map.get((requirement.id, group.id), [])
            if len(assigned) != 1:
                errors.append(f"{subject.subject_code} · {group_name}: expected exactly one teacher assignment; found {len(assigned)}.")
                continue
            teacher_id = assigned[0].faculty_id
            teacher = faculty_map.get(teacher_id)
            if teacher is None:
                errors.append(f"{subject.subject_code} · {group_name}: assigned faculty is missing or inactive.")
                continue
            for activity, hours_field, sessions_field, duration_field in ACTIVITIES:
                hours = getattr(requirement, hours_field)
                sessions = getattr(requirement, sessions_field)
                duration = getattr(requirement, duration_field)
                if hours is None:
                    errors.append(f"{subject.subject_code} · {group_name}: weekly {activity} hours are unconfirmed.")
                    continue
                if hours == 0:
                    if sessions not in (None, 0):
                        errors.append(f"{subject.subject_code} · {group_name}: {activity} has zero confirmed hours but a non-zero session count.")
                    continue
                if sessions is None or sessions <= 0:
                    errors.append(f"{subject.subject_code} · {group_name}: positive {activity} hours require a confirmed positive weekly session count.")
                    continue
                if duration is None or duration <= 0:
                    errors.append(f"{subject.subject_code} · {group_name}: {activity} session duration is unconfirmed.")
                    continue
                if config.academic_hour_minutes and sessions * duration != hours * config.academic_hour_minutes:
                    errors.append(
                        f"{subject.subject_code} · {group_name}: {activity} demand does not reconcile "
                        f"({sessions} × {duration} minutes versus {hours} × {config.academic_hour_minutes} minutes per academic hour)."
                    )
                    continue
                room_requirement = activity_room_by_type.get(activity)
                if room_requirement is None:
                    errors.append(f"{subject.subject_code} · {group_name}: required room type for {activity} is unconfirmed.")
                    continue
                if room_requirement.room_type == "laboratory" and not any(slot.is_lab_compatible for slot in periods):
                    errors.append(f"{subject.subject_code} · {activity}: no teaching period is confirmed laboratory-compatible.")
                    continue
                equipment = frozenset(item.capability_name.strip().casefold() for item in room_requirement.equipment)
                for index in range(sessions):
                    demand_records.append((Demand(
                        key=f"{requirement.id}:{group.id}:{activity}:{index + 1}",
                        requirement_id=requirement.id, group_id=group.id, group_name=group_name,
                        student_count=group.student_count, subject_code=subject.subject_code,
                        subject_name=subject.subject_name, activity_type=activity,
                        session_index=index + 1, duration_minutes=duration,
                        academic_year_id=academic_year_id, teacher_id=teacher_id,
                        teacher_name=teacher.faculty_name, room_type=room_requirement.room_type,
                        equipment=equipment,
                    ), room_requirement))

    if errors:
        return None, sorted(set(errors)), sorted(set(warnings))
    if not demand_records:
        return None, ["There are no confirmed positive-hour sessions to schedule."], sorted(set(warnings))

    day_periods = {day: [Slot(day, slot.period_number, slot.sequence_number, slot.start_minute, slot.end_minute, slot.is_lab_compatible) for slot in periods] for day in working_days}
    all_periods = [slot for day in working_days for slot in day_periods[day]]
    candidate_rows: list[Candidate] = []
    candidates_by_demand: dict[str, list[int]] = defaultdict(list)
    for demand, room_requirement in demand_records:
        type_rooms = [
            room for room in eligible_rooms.values()
            if room.room_type == demand.room_type
            and room.capacity >= demand.student_count
            and demand.equipment.issubset(room_capabilities.get(room.id, set()))
        ]
        if not type_rooms:
            needed = ", ".join(sorted(demand.equipment))
            detail = f" and equipment [{needed}]" if needed else ""
            errors.append(f"{demand.subject_code} · {demand.group_name} · {demand.activity_type}: no confirmed {demand.room_type} has capacity {demand.student_count}{detail}.")
            continue
        for weekday in working_days:
            day_slots = day_periods[weekday]
            for start_index, first in enumerate(day_slots):
                chosen: list[Slot] = []
                total_minutes = 0
                for slot in day_slots[start_index:]:
                    if chosen and (slot.sequence_number != chosen[-1].sequence_number + 1 or slot.period_number != chosen[-1].period_number + 1):
                        break
                    chosen.append(slot)
                    total_minutes += slot.end_minute - slot.start_minute
                    if total_minutes > demand.duration_minutes:
                        break
                    if total_minutes != demand.duration_minutes:
                        continue
                    is_lab_session = demand.room_type == "laboratory"
                    if is_lab_session and (len(chosen) != 2 or not all(item.is_lab_compatible for item in chosen)):
                        break
                    start_minute, end_minute = chosen[0].start_minute, chosen[-1].end_minute
                    if not _within_window(start_minute, end_minute, weekday, faculty_windows[demand.teacher_id]):
                        break
                    for room in type_rooms:
                        if _within_window(start_minute, end_minute, weekday, room_windows[room.id]):
                            candidate = Candidate(demand.key, weekday, tuple(chosen), room.id, room.room_name, demand.teacher_id, start_minute, end_minute)
                            candidates_by_demand[demand.key].append(len(candidate_rows))
                            candidate_rows.append(candidate)
                    break
        if not candidates_by_demand.get(demand.key):
            errors.append(
                f"{demand.subject_code} · {demand.group_name} · {demand.activity_type} session {demand.session_index}: "
                "no placement fits the confirmed days, periods, availability, room requirements, and duration."
            )
    if errors:
        return None, sorted(set(errors)), sorted(set(warnings))

    prepared = PreparedProblem(
        demands=[item[0] for item in demand_records], candidates=candidate_rows,
        candidates_by_demand=dict(candidates_by_demand), periods=all_periods,
        working_days=working_days, rooms=eligible_rooms, faculties=faculty_map,
        room_windows=room_windows, faculty_windows=faculty_windows,
        faculty_daily_limits=faculty_daily_limits, faculty_weekly_limits=faculty_weekly_limits,
        room_capabilities=dict(room_capabilities),
        academic_year_id=academic_year_id,
        college_time_snapshot={
            "configuration_id": config.id, "version": config.version,
            "academic_hour_minutes": config.academic_hour_minutes,
            "working_days": working_days,
            "blocks": [{"sequence_number": block.sequence_number, "block_type": block.block_type,
                        "period_number": block.period_number, "label": block.label,
                        "start_time": block.start_time.isoformat(), "end_time": block.end_time.isoformat(),
                        "is_lab_compatible": block.is_lab_compatible} for block in blocks],
        },
    )
    return prepared, [], sorted(set(warnings))


def validate_alternative(problem: PreparedProblem, selected: list[Candidate]) -> list[str]:
    """Independent post-solve verification; a failure prevents returning a valid alternative."""
    diagnostics: list[str] = []
    by_demand: dict[str, list[Candidate]] = defaultdict(list)
    group_slots: set[tuple[int, int, int]] = set()
    teacher_slots: set[tuple[int, int, int]] = set()
    room_slots: set[tuple[int, int, int]] = set()
    teacher_daily: dict[tuple[int, int], int] = defaultdict(int)
    teacher_weekly: dict[int, int] = defaultdict(int)
    demand_by_key = {demand.key: demand for demand in problem.demands}
    for candidate in selected:
        demand = demand_by_key.get(candidate.demand_key)
        if demand is None:
            diagnostics.append("A solver result refers to an unknown required session.")
            continue
        by_demand[demand.key].append(candidate)
        if len(candidate.slots) < 1 or sum(slot.end_minute - slot.start_minute for slot in candidate.slots) != demand.duration_minutes:
            diagnostics.append(f"{demand.subject_code} {demand.group_name}: session duration does not match its confirmed requirement.")
        if demand.room_type == "laboratory" and (len(candidate.slots) != 2 or not all(slot.is_lab_compatible for slot in candidate.slots)):
            diagnostics.append(f"{demand.subject_code} {demand.group_name}: laboratory session is not exactly two compatible consecutive periods.")
        if len(candidate.slots) > 1 and any(
            current.sequence_number != previous.sequence_number + 1
            or current.period_number != previous.period_number + 1
            for previous, current in zip(candidate.slots, candidate.slots[1:])
        ):
            diagnostics.append(f"{demand.subject_code} {demand.group_name}: a multi-period session crosses a non-teaching break.")
        room = problem.rooms.get(candidate.room_id)
        if room is None or room.room_type != demand.room_type or room.capacity < demand.student_count:
            diagnostics.append(f"{demand.subject_code} {demand.group_name}: selected room is incompatible with the group.")
        elif not demand.equipment.issubset(problem.room_capabilities.get(candidate.room_id, set())):
            diagnostics.append(f"{demand.subject_code} {demand.group_name}: selected room lacks required equipment.")
        if candidate.teacher_id != demand.teacher_id:
            diagnostics.append(f"{demand.subject_code} {demand.group_name}: selected faculty does not match its assignment.")
        for slot in candidate.slots:
            expected_slot = next((item for item in problem.periods if item.weekday == candidate.weekday and item.period_number == slot.period_number), None)
            if expected_slot != slot:
                diagnostics.append(f"{demand.subject_code} {demand.group_name}: placement uses a period outside the active college schedule.")
            g_key = (demand.group_id, candidate.weekday, slot.period_number)
            t_key = (candidate.teacher_id, candidate.weekday, slot.period_number)
            r_key = (candidate.room_id, candidate.weekday, slot.period_number)
            if g_key in group_slots:
                diagnostics.append(f"Student group conflict: {demand.group_name} has simultaneous sessions.")
            if t_key in teacher_slots:
                diagnostics.append(f"Teacher conflict: {demand.teacher_name} has simultaneous sessions.")
            if r_key in room_slots:
                diagnostics.append(f"Room conflict: {candidate.room_name} is used simultaneously.")
            group_slots.add(g_key); teacher_slots.add(t_key); room_slots.add(r_key)
        minutes = demand.duration_minutes
        teacher_daily[(candidate.teacher_id, candidate.weekday)] += minutes
        teacher_weekly[candidate.teacher_id] += minutes
        if not _within_window(candidate.start_minute, candidate.end_minute, candidate.weekday, problem.faculty_windows[candidate.teacher_id]):
            diagnostics.append(f"Faculty availability conflict: {demand.teacher_name} is outside a confirmed available window.")
        if not _within_window(candidate.start_minute, candidate.end_minute, candidate.weekday, problem.room_windows[candidate.room_id]):
            diagnostics.append(f"Room availability conflict: {candidate.room_name} is outside a confirmed available window.")
    for demand in problem.demands:
        if len(by_demand[demand.key]) != 1:
            diagnostics.append(f"{demand.subject_code} {demand.group_name}: required session {demand.session_index} is missing or duplicated.")
    for (teacher_id, weekday), minutes in teacher_daily.items():
        if minutes > problem.faculty_daily_limits[teacher_id]:
            diagnostics.append(f"Daily workload exceeded for {problem.faculties[teacher_id].faculty_name} on {WEEKDAY_NAMES[weekday]}.")
    for teacher_id, minutes in teacher_weekly.items():
        if minutes > problem.faculty_weekly_limits[teacher_id]:
            diagnostics.append(f"Weekly workload exceeded for {problem.faculties[teacher_id].faculty_name}.")
    return sorted(set(diagnostics))


def serialize_candidate(problem: PreparedProblem, candidate: Candidate) -> dict[str, Any]:
    demand = next(item for item in problem.demands if item.key == candidate.demand_key)
    room = problem.rooms[candidate.room_id]
    return {
        "group_id": demand.group_id, "group_name": demand.group_name,
        "subject_code": demand.subject_code, "subject_name": demand.subject_name,
        "activity_type": demand.activity_type, "session_index": demand.session_index,
        "teacher_id": candidate.teacher_id, "teacher_name": demand.teacher_name,
        "room_id": candidate.room_id, "room_name": candidate.room_name,
        "room_type": room.room_type, "room_capacity": room.capacity,
        "room_equipment": sorted(problem.room_capabilities.get(candidate.room_id, set())),
        "required_room_type": demand.room_type, "required_equipment": sorted(demand.equipment),
        "student_count": demand.student_count, "weekday": candidate.weekday,
        "period_numbers": [slot.period_number for slot in candidate.slots],
        "start_time": f"{candidate.start_minute // 60:02d}:{candidate.start_minute % 60:02d}",
        "end_time": f"{candidate.end_minute // 60:02d}:{candidate.end_minute % 60:02d}",
        "duration_minutes": demand.duration_minutes,
    }


def validate_submitted_alternative(db: Session, academic_year_id: int, submitted: list[dict[str, Any]]) -> tuple[PreparedProblem | None, list[Candidate], list[str], list[str]]:
    """Rebuild and validate a client preview against current confirmed source data."""
    problem, errors, warnings = prepare_problem(db, academic_year_id)
    if errors or problem is None:
        return problem, [], errors, warnings
    by_identity = {
        (next(d for d in problem.demands if d.key == candidate.demand_key).group_id,
         next(d for d in problem.demands if d.key == candidate.demand_key).subject_code,
         next(d for d in problem.demands if d.key == candidate.demand_key).activity_type,
         next(d for d in problem.demands if d.key == candidate.demand_key).session_index,
         candidate.room_id, candidate.weekday, candidate.slot_keys): candidate
        for candidate in problem.candidates
    }
    selected: list[Candidate] = []
    errors = []
    expected_keys = set()
    for session in submitted:
        try:
            identity = (
                int(session["group_id"]), str(session["subject_code"]), str(session["activity_type"]),
                int(session["session_index"]), int(session["room_id"]), int(session["weekday"]),
                tuple((int(session["weekday"]), int(period)) for period in session["period_numbers"]),
            )
        except (KeyError, TypeError, ValueError):
            errors.append("A session is missing required placement identifiers.")
            continue
        candidate = by_identity.get(identity)
        if candidate is None:
            errors.append("A proposed session no longer matches confirmed subjects, assignments, times, room rules, and availability.")
            continue
        canonical = serialize_candidate(problem, candidate)
        if any(session.get(key) != value for key, value in canonical.items()):
            errors.append("A proposed session's details were changed after generation; generate a fresh alternative.")
            continue
        demand = next(item for item in problem.demands if item.key == candidate.demand_key)
        if demand.key in expected_keys:
            errors.append("A required session was duplicated in the proposed alternative.")
            continue
        expected_keys.add(demand.key)
        selected.append(candidate)
    if expected_keys != {demand.key for demand in problem.demands}:
        errors.append("The alternative is incomplete: it must include every required session exactly once.")
    if not errors:
        errors.extend(validate_alternative(problem, selected))
    return problem, selected, sorted(set(errors)), warnings


def solve_alternatives(problem: PreparedProblem, count: int = 4, max_seconds_per_solve: float = 10.0) -> dict[str, Any]:
    """Find distinct complete alternatives, minimizing group idle gaps."""
    if count not in (3, 4):
        raise ValueError("Request either three or four alternatives.")
    model = cp_model.CpModel()
    variables = [model.new_bool_var(f"placement_{index}") for index in range(len(problem.candidates))]
    for demand in problem.demands:
        model.add_exactly_one(variables[index] for index in problem.candidates_by_demand[demand.key])

    resource_indices: dict[tuple[str, int, int, int], list[int]] = defaultdict(list)
    for index, candidate in enumerate(problem.candidates):
        demand = next(item for item in problem.demands if item.key == candidate.demand_key)
        for slot in candidate.slots:
            resource_indices[("group", demand.group_id, candidate.weekday, slot.period_number)].append(index)
            resource_indices[("teacher", candidate.teacher_id, candidate.weekday, slot.period_number)].append(index)
            resource_indices[("room", candidate.room_id, candidate.weekday, slot.period_number)].append(index)
    for indices in resource_indices.values():
        if len(indices) > 1:
            model.add_at_most_one(variables[index] for index in indices)

    demand_by_key = {demand.key: demand for demand in problem.demands}
    for teacher_id in problem.faculty_weekly_limits:
        weekly_terms = []
        for index, candidate in enumerate(problem.candidates):
            demand = demand_by_key[candidate.demand_key]
            if demand.teacher_id == teacher_id:
                term = demand.duration_minutes * variables[index]
                weekly_terms.append(term)
        model.add(sum(weekly_terms) <= problem.faculty_weekly_limits[teacher_id])
        for weekday in problem.working_days:
            daily_terms = []
            for index, candidate in enumerate(problem.candidates):
                demand = demand_by_key[candidate.demand_key]
                if demand.teacher_id == teacher_id and candidate.weekday == weekday:
                    daily_terms.append(demand.duration_minutes * variables[index])
            if daily_terms:
                model.add(sum(daily_terms) <= problem.faculty_daily_limits[teacher_id])

    gap_terms = []
    for group_id in {demand.group_id for demand in problem.demands}:
        for weekday in problem.working_days:
            day_slots = [slot for slot in problem.periods if slot.weekday == weekday]
            occupancy = []
            for slot in day_slots:
                matching = [
                    variables[index] for index, candidate in enumerate(problem.candidates)
                    if candidate.weekday == weekday and slot.period_number in {item.period_number for item in candidate.slots}
                    and demand_by_key[candidate.demand_key].group_id == group_id
                ]
                occupied = model.new_bool_var(f"occupied_g{group_id}_d{weekday}_p{slot.period_number}")
                model.add(sum(matching) == occupied)
                occupancy.append(occupied)
            if not occupancy:
                continue
            active = model.new_bool_var(f"active_g{group_id}_d{weekday}")
            total = sum(occupancy)
            model.add(total >= 1).only_enforce_if(active)
            model.add(total == 0).only_enforce_if(active.negated())
            first = model.new_int_var(0, len(occupancy) + 1, f"first_g{group_id}_d{weekday}")
            last = model.new_int_var(0, len(occupancy), f"last_g{group_id}_d{weekday}")
            first_positions = []
            last_positions = []
            for position, occupied in enumerate(occupancy, start=1):
                first_pos = model.new_int_var(1, len(occupancy) + 1, f"firstpos_{group_id}_{weekday}_{position}")
                model.add(first_pos == position).only_enforce_if(occupied)
                model.add(first_pos == len(occupancy) + 1).only_enforce_if(occupied.negated())
                first_positions.append(first_pos)
                last_pos = model.new_int_var(0, len(occupancy), f"lastpos_{group_id}_{weekday}_{position}")
                model.add(last_pos == position).only_enforce_if(occupied)
                model.add(last_pos == 0).only_enforce_if(occupied.negated())
                last_positions.append(last_pos)
            model.add_min_equality(first, first_positions)
            model.add_max_equality(last, last_positions)
            gaps = model.new_int_var(0, len(occupancy), f"gaps_g{group_id}_d{weekday}")
            model.add(gaps == last - first + 1 - total).only_enforce_if(active)
            model.add(gaps == 0).only_enforce_if(active.negated())
            gap_terms.append(gaps)

    alternatives: list[dict[str, Any]] = []
    last_solver_status: int | None = None
    for alternative_index in range(count):
        rng = random.Random(7301 + alternative_index)
        tie_break_terms = [rng.randint(1, 25) * variable for variable in variables]
        big_gap_weight = len(problem.demands) * 25 + 1
        model.minimize(big_gap_weight * sum(gap_terms) + sum(tie_break_terms))
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = max_seconds_per_solve
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 7301 + alternative_index
        status = solver.solve(model)
        last_solver_status = status
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            break
        selected_indices = [index for index, variable in enumerate(variables) if solver.boolean_value(variable)]
        selected = [problem.candidates[index] for index in selected_indices]
        diagnostics = validate_alternative(problem, selected)
        if diagnostics:
            return {"status": "invalid", "requested_count": count, "valid_count": 0, "alternatives": [], "diagnostics": diagnostics, "warnings": []}
        alternatives.append({
            "alternative_number": alternative_index + 1,
            "sessions": [
                {
                    "group_id": demand_by_key[candidate.demand_key].group_id,
                    "group_name": demand_by_key[candidate.demand_key].group_name,
                    "subject_code": demand_by_key[candidate.demand_key].subject_code,
                    "subject_name": demand_by_key[candidate.demand_key].subject_name,
                    "activity_type": demand_by_key[candidate.demand_key].activity_type,
                    "session_index": demand_by_key[candidate.demand_key].session_index,
                    "teacher_id": candidate.teacher_id,
                    "teacher_name": demand_by_key[candidate.demand_key].teacher_name,
                    "room_id": candidate.room_id,
                    "room_name": candidate.room_name,
                    "room_type": problem.rooms[candidate.room_id].room_type,
                    "room_capacity": problem.rooms[candidate.room_id].capacity,
                    "room_equipment": sorted(problem.room_capabilities.get(candidate.room_id, set())),
                    "required_room_type": demand_by_key[candidate.demand_key].room_type,
                    "required_equipment": sorted(demand_by_key[candidate.demand_key].equipment),
                    "student_count": demand_by_key[candidate.demand_key].student_count,
                    "weekday": candidate.weekday,
                    "period_numbers": [slot.period_number for slot in candidate.slots],
                    "start_time": f"{candidate.start_minute // 60:02d}:{candidate.start_minute % 60:02d}",
                    "end_time": f"{candidate.end_minute // 60:02d}:{candidate.end_minute % 60:02d}",
                    "duration_minutes": demand_by_key[candidate.demand_key].duration_minutes,
                }
                for candidate in sorted(selected, key=lambda item: (item.weekday, item.slots[0].period_number, item.room_name))
                for demand in [demand_by_key[candidate.demand_key]]
            ],
            "validation": "valid",
        })
        # Exclude the complete prior selection to ensure the next schedule is genuinely different.
        model.add(sum(variables[index] for index in selected_indices) <= len(problem.demands) - 1)

    if alternatives:
        status_label = "success"
        diagnostics: list[str] = []
    else:
        # UNKNOWN means the solver may have reached its time limit without
        # proving infeasibility. Do not report that outcome as proven infeasible.
        if last_solver_status == cp_model.INFEASIBLE:
            status_label = "infeasible"
            primary_diagnostic = (
                "The solver proved that no complete timetable satisfies the currently confirmed constraints. "
                "Check actual availability windows, compatible consecutive lab periods, shared-teacher assignments, "
                "room/equipment requirements, and faculty workload limits."
            )
        elif last_solver_status == cp_model.MODEL_INVALID:
            status_label = "model_error"
            primary_diagnostic = (
                "The solver rejected the constraint model as invalid. Inspect backend logs and model constraints "
                "before changing timetable data."
            )
        elif last_solver_status == cp_model.UNKNOWN:
            status_label = "no_solution_found"
            primary_diagnostic = (
                f"The solver reached its {max_seconds_per_solve:g}-second time limit without finding a complete "
                "timetable or proving that none exists. This is not proof that the constraints are infeasible. "
                "Review availability windows before increasing the solve time further."
            )
        else:
            status_label = "no_solution_found"
            primary_diagnostic = (
                "The solver did not return a complete timetable. Review backend logs and confirmed availability, "
                "room compatibility, and workload constraints."
            )

        demand_summary = ", ".join(
            f"{demand.group_name} {demand.subject_code} {demand.activity_type} ({demand.duration_minutes} min × 1)"
            for demand in problem.demands[:12]
        )
        suffix = " …" if len(problem.demands) > 12 else ""
        diagnostics = [
            primary_diagnostic,
            f"Required sessions considered: {demand_summary}{suffix}" if demand_summary else "No required sessions were derived from the confirmed inputs.",
        ]
    if alternatives and len(alternatives) < count:
        diagnostics.append(f"Only {len(alternatives)} distinct valid alternative(s) were found; the requested count was {count}.")
    return {"status": status_label, "requested_count": count, "valid_count": len(alternatives), "alternatives": alternatives, "diagnostics": diagnostics, "warnings": []}


def generate_s5_alternatives(db: Session, academic_year_id: int, count: int = 4) -> dict[str, Any]:
    prepared, errors, warnings = prepare_problem(db, academic_year_id)
    if errors:
        return {"status": "incomplete", "requested_count": count, "valid_count": 0, "alternatives": [], "diagnostics": errors, "warnings": warnings}
    assert prepared is not None
    result = solve_alternatives(prepared, count=count)
    result["warnings"] = warnings
    return result
