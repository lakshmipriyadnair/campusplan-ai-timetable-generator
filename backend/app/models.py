"""Source academic data models. Timetable results are intentionally separate."""

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Time,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("name", name="uq_departments_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    semesters: Mapped[list["Semester"]] = relationship(
        back_populates="department", passive_deletes="all"
    )


class AcademicYear(Base):
    __tablename__ = "academic_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    __table_args__ = (
        CheckConstraint("end_date > start_date", name="ck_academic_year_dates"),
    )
    semesters: Mapped[list["Semester"]] = relationship(
        back_populates="academic_year", passive_deletes="all"
    )


class Semester(Base):
    __tablename__ = "semesters"
    __table_args__ = (
        UniqueConstraint(
            "department_id", "academic_year_id", "semester_number",
            name="uq_semesters_department_year_number",
        ),
        CheckConstraint("semester_number > 0", name="ck_semesters_number_positive"),
        Index("ix_semesters_department_year", "department_id", "academic_year_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(
        ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    academic_year_id: Mapped[int] = mapped_column(
        ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    department: Mapped[Department] = relationship(back_populates="semesters")
    academic_year: Mapped[AcademicYear] = relationship(back_populates="semesters")
    student_groups: Mapped[list["StudentGroup"]] = relationship(
        back_populates="semester", passive_deletes="all"
    )
    # Curriculum is attached to a group, so groups in one semester may differ.
    semester_subjects: Mapped[list["SemesterSubject"]] = relationship(
        back_populates="semester", passive_deletes="all"
    )


class StudentGroup(Base):
    __tablename__ = "student_groups"
    __table_args__ = (
        UniqueConstraint("semester_id", "group_name", name="uq_groups_semester_name"),
        CheckConstraint("student_count > 0", name="ck_groups_student_count_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    group_name: Mapped[str] = mapped_column(String(80), nullable=False)
    section_identifier: Mapped[str | None] = mapped_column(String(30), nullable=True)
    student_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    semester: Mapped[Semester] = relationship(back_populates="student_groups")
    semester_subjects: Mapped[list["SemesterSubject"]] = relationship(
        back_populates="student_group", passive_deletes="all"
    )
    predefined_identity: Mapped["PredefinedStudentGroup | None"] = relationship(
        back_populates="student_group", uselist=False, passive_deletes="all"
    )

    @property
    def is_predefined(self) -> bool:
        """Expose the protected marker without making it writable via CRUD."""
        return self.predefined_identity is not None


class PredefinedStudentGroup(Base):
    """Private identity marker for groups protected from ordinary CRUD edits."""

    __tablename__ = "predefined_student_groups"

    student_group_id: Mapped[int] = mapped_column(
        ForeignKey("student_groups.id", ondelete="RESTRICT"), primary_key=True
    )
    group_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    student_group: Mapped[StudentGroup] = relationship(back_populates="predefined_identity")


class Faculty(Base):
    __tablename__ = "faculty"

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    faculty_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    faculty_subjects: Mapped[list["FacultySubject"]] = relationship(
        back_populates="faculty", passive_deletes="all"
    )

    scheduling_profile: Mapped["FacultySchedulingProfile | None"] = relationship(
        back_populates="faculty", uselist=False, cascade="all, delete-orphan"
    )


class FacultySchedulingProfile(Base):
    """Explicit availability and workload limits required before scheduling a faculty member."""

    __tablename__ = "faculty_scheduling_profiles"
    __table_args__ = (
        UniqueConstraint("faculty_id", name="uq_faculty_scheduling_profile"),
        CheckConstraint("max_daily_minutes IS NULL OR max_daily_minutes > 0", name="ck_faculty_daily_limit_positive"),
        CheckConstraint("max_weekly_minutes IS NULL OR max_weekly_minutes > 0", name="ck_faculty_weekly_limit_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False, index=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_daily_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_weekly_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    faculty: Mapped[Faculty] = relationship(back_populates="scheduling_profile")
    windows: Mapped[list["FacultyAvailabilityWindow"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class FacultyAvailabilityWindow(Base):
    """An explicitly available or unavailable faculty time range."""

    __tablename__ = "faculty_availability_windows"
    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_faculty_window_weekday"),
        CheckConstraint("availability IN ('available', 'unavailable')", name="ck_faculty_window_availability"),
        CheckConstraint("end_time > start_time", name="ck_faculty_window_ordered_times"),
        Index("ix_faculty_availability_profile_day", "profile_id", "weekday"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("faculty_scheduling_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[object] = mapped_column(Time, nullable=False)
    end_time: Mapped[object] = mapped_column(Time, nullable=False)
    availability: Mapped[str] = mapped_column(String(12), nullable=False)
    profile: Mapped[FacultySchedulingProfile] = relationship(back_populates="windows")


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint(
            "room_type IN ('classroom', 'laboratory', 'other')", name="ck_rooms_type"
        ),
        CheckConstraint("capacity > 0", name="ck_rooms_capacity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    room_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    subject_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    semester_subjects: Mapped[list["SemesterSubject"]] = relationship(
        back_populates="subject", passive_deletes="all"
    )


class SemesterSubject(Base):
    __tablename__ = "semester_subjects"
    __table_args__ = (
        UniqueConstraint("student_group_id", "subject_id", name="uq_group_subject"),
        CheckConstraint("weekly_lecture_hours >= 0", name="ck_lecture_hours_nonnegative"),
        CheckConstraint("weekly_tutorial_hours >= 0", name="ck_tutorial_hours_nonnegative"),
        CheckConstraint("weekly_practical_hours >= 0", name="ck_practical_hours_nonnegative"),
        CheckConstraint(
            "lecture_session_minutes IS NULL OR lecture_session_minutes > 0",
            name="ck_lecture_duration_positive",
        ),
        CheckConstraint(
            "tutorial_session_minutes IS NULL OR tutorial_session_minutes > 0",
            name="ck_tutorial_duration_positive",
        ),
        CheckConstraint(
            "practical_session_minutes IS NULL OR practical_session_minutes > 0",
            name="ck_practical_duration_positive",
        ),
        Index("ix_semester_subjects_semester", "semester_id"),
        Index("ix_semester_subjects_group", "student_group_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(
        ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    student_group_id: Mapped[int] = mapped_column(
        ForeignKey("student_groups.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    weekly_lecture_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weekly_tutorial_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weekly_practical_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lecture_session_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tutorial_session_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    practical_session_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    semester: Mapped[Semester] = relationship(back_populates="semester_subjects")
    student_group: Mapped[StudentGroup] = relationship(back_populates="semester_subjects")
    subject: Mapped[Subject] = relationship(back_populates="semester_subjects")
    faculty_subjects: Mapped[list["FacultySubject"]] = relationship(
        back_populates="semester_subject", passive_deletes="all"
    )


class FacultySubject(Base):
    __tablename__ = "faculty_subjects"
    __table_args__ = (
        UniqueConstraint(
            "faculty_id", "semester_subject_id", name="uq_faculty_semester_subject"
        ),
        Index("ix_faculty_subjects_semester_subject", "semester_subject_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(
        ForeignKey("faculty.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    semester_subject_id: Mapped[int] = mapped_column(
        ForeignKey("semester_subjects.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    faculty: Mapped[Faculty] = relationship(back_populates="faculty_subjects")
    semester_subject: Mapped[SemesterSubject] = relationship(back_populates="faculty_subjects")


class SharedSubjectRequirement(Base):
    """One common S5 subject requirement shared by S5-A and S5-B.

    Nullable hour values mean the administrator has not confirmed the value.
    An explicitly confirmed zero is stored as 0, never inferred from absence.
    """

    __tablename__ = "shared_subject_requirements"
    __table_args__ = (
        UniqueConstraint("semester_id", "subject_id", name="uq_shared_requirement_semester_subject"),
        CheckConstraint("weekly_lecture_hours IS NULL OR weekly_lecture_hours >= 0", name="ck_shared_lecture_nonnegative"),
        CheckConstraint("weekly_tutorial_hours IS NULL OR weekly_tutorial_hours >= 0", name="ck_shared_tutorial_nonnegative"),
        CheckConstraint("weekly_practical_hours IS NULL OR weekly_practical_hours >= 0", name="ck_shared_practical_nonnegative"),
        CheckConstraint("lecture_session_minutes IS NULL OR lecture_session_minutes > 0", name="ck_shared_lecture_duration_positive"),
        CheckConstraint("tutorial_session_minutes IS NULL OR tutorial_session_minutes > 0", name="ck_shared_tutorial_duration_positive"),
        CheckConstraint("practical_session_minutes IS NULL OR practical_session_minutes > 0", name="ck_shared_practical_duration_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False, index=True)
    weekly_lecture_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_tutorial_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_practical_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_lecture_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_tutorial_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_practical_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lecture_session_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tutorial_session_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    practical_session_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    semester: Mapped[Semester] = relationship()
    subject: Mapped[Subject] = relationship()
    section_teacher_assignments: Mapped[list["SectionTeacherAssignment"]] = relationship(back_populates="requirement", passive_deletes="all")
    activity_room_requirements: Mapped[list["ActivityRoomRequirement"]] = relationship(back_populates="requirement", cascade="all, delete-orphan")


class SectionTeacherAssignment(Base):
    """Teacher link for one section; assignments may differ by section."""

    __tablename__ = "section_teacher_assignments"
    __table_args__ = (
        UniqueConstraint("requirement_id", "student_group_id", "faculty_id", name="uq_section_teacher_assignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("shared_subject_requirements.id", ondelete="RESTRICT"), nullable=False, index=True)
    student_group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="RESTRICT"), nullable=False, index=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="RESTRICT"), nullable=False, index=True)

    requirement: Mapped[SharedSubjectRequirement] = relationship(back_populates="section_teacher_assignments")
    student_group: Mapped[StudentGroup] = relationship()
    faculty: Mapped[Faculty] = relationship()


class ActivityRoomRequirement(Base):
    """Confirmed room type required for one activity within a shared subject."""

    __tablename__ = "activity_room_requirements"
    __table_args__ = (
        UniqueConstraint("requirement_id", "activity_type", name="uq_activity_room_requirement"),
        CheckConstraint("activity_type IN ('lecture', 'tutorial', 'practical')", name="ck_activity_room_activity_type"),
        CheckConstraint("room_type IN ('classroom', 'laboratory', 'other')", name="ck_activity_room_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("shared_subject_requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    room_type: Mapped[str] = mapped_column(String(20), nullable=False)
    requirement: Mapped[SharedSubjectRequirement] = relationship(back_populates="activity_room_requirements")
    equipment: Mapped[list["ActivityEquipmentRequirement"]] = relationship(back_populates="activity_requirement", cascade="all, delete-orphan")


class ActivityEquipmentRequirement(Base):
    """One explicitly named capability required for a particular activity."""

    __tablename__ = "activity_equipment_requirements"
    __table_args__ = (
        UniqueConstraint("activity_requirement_id", "capability_name", name="uq_activity_equipment_requirement"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_requirement_id: Mapped[int] = mapped_column(ForeignKey("activity_room_requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    capability_name: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_requirement: Mapped[ActivityRoomRequirement] = relationship(back_populates="equipment")


class TimetableSnapshot(Base):
    """Immutable, independently validated approval snapshot for one CSE S5 year."""

    __tablename__ = "timetable_snapshots"
    __table_args__ = (
        UniqueConstraint("semester_id", "version", name="uq_timetable_snapshot_semester_version"),
        CheckConstraint("status = 'approved'", name="ck_timetable_snapshot_approved_only"),
        CheckConstraint("version > 0", name="ck_timetable_snapshot_version_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    semester_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="approved")
    alternative_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sessions_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    configuration_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class OfficialTimetable(Base):
    """Single atomic pointer to the current published snapshot for a semester."""

    __tablename__ = "official_timetables"
    __table_args__ = (UniqueConstraint("semester_id", name="uq_official_timetable_semester"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("timetable_snapshots.id", ondelete="RESTRICT"), nullable=False, unique=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TimetablePublicationEvent(Base):
    """Append-only publication history; old versions remain available."""

    __tablename__ = "timetable_publication_events"
    __table_args__ = (Index("ix_timetable_publication_semester_time", "semester_id", "published_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False, index=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("timetable_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True)
    previous_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("timetable_snapshots.id", ondelete="RESTRICT"), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class CollegeTimeConfiguration(Base):
    """College-wide, versioned timetable layout; no default times are seeded."""

    __tablename__ = "college_time_configurations"
    __table_args__ = (
        UniqueConstraint("version", name="uq_college_time_configuration_version"),
        CheckConstraint("version > 0", name="ck_time_config_version_positive"),
        Index(
            "uq_one_active_time_configuration",
            "is_active",
            unique=True,
            sqlite_where=text("is_active = 1"),
            postgresql_where=text("is_active = true"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    academic_hour_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    working_days: Mapped[list["CollegeWorkingDay"]] = relationship(back_populates="configuration", cascade="all, delete-orphan")
    time_blocks: Mapped[list["CollegeTimeBlock"]] = relationship(back_populates="configuration", cascade="all, delete-orphan")


class CollegeWorkingDay(Base):
    __tablename__ = "college_working_days"
    __table_args__ = (
        UniqueConstraint("configuration_id", "weekday", name="uq_config_weekday"),
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_working_day_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("college_time_configurations.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)  # Monday=0 through Sunday=6
    configuration: Mapped[CollegeTimeConfiguration] = relationship(back_populates="working_days")


class CollegeTimeBlock(Base):
    """An ordered teaching period, break, or lunch interval."""

    __tablename__ = "college_time_blocks"
    __table_args__ = (
        UniqueConstraint("configuration_id", "sequence_number", name="uq_config_time_block_sequence"),
        UniqueConstraint("configuration_id", "period_number", name="uq_config_period_number"),
        Index(
            "uq_config_lunch",
            "configuration_id",
            unique=True,
            sqlite_where=text("block_type = 'lunch'"),
            postgresql_where=text("block_type = 'lunch'"),
        ),
        CheckConstraint("sequence_number > 0", name="ck_time_block_sequence_positive"),
        CheckConstraint("block_type IN ('teaching', 'break', 'lunch')", name="ck_time_block_type"),
        CheckConstraint("period_number IS NULL OR period_number > 0", name="ck_time_block_period_positive"),
        CheckConstraint("end_time > start_time", name="ck_time_block_ordered_times"),
        CheckConstraint("block_type = 'teaching' OR is_lab_compatible = 0", name="ck_only_teaching_lab_compatible"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    configuration_id: Mapped[int] = mapped_column(ForeignKey("college_time_configurations.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String(12), nullable=False)
    period_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    start_time: Mapped[object] = mapped_column(Time, nullable=False)
    end_time: Mapped[object] = mapped_column(Time, nullable=False)
    is_lab_compatible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    configuration: Mapped[CollegeTimeConfiguration] = relationship(back_populates="time_blocks")


class RoomCapability(Base):
    """Administrator-entered equipment or capability attached to a room."""

    __tablename__ = "room_capabilities"
    __table_args__ = (
        UniqueConstraint("room_id", "capability_name", name="uq_room_capability_name"),
        CheckConstraint("capability_type IN ('equipment', 'capability')", name="ck_room_capability_type"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_room_capability_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    capability_name: Mapped[str] = mapped_column(String(120), nullable=False)
    capability_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RoomAvailabilityProfile(Base):
    """An explicit availability-completeness marker for a room."""

    __tablename__ = "room_availability_profiles"
    __table_args__ = (UniqueConstraint("room_id", name="uq_room_availability_profile"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, index=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    windows: Mapped[list["RoomAvailabilityWindow"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class RoomAvailabilityWindow(Base):
    """An explicit allowed or unavailable interval within a weekday."""

    __tablename__ = "room_availability_windows"
    __table_args__ = (
        CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_room_window_weekday"),
        CheckConstraint("availability IN ('available', 'unavailable')", name="ck_room_window_availability"),
        CheckConstraint("end_time > start_time", name="ck_room_window_ordered_times"),
        Index("ix_room_availability_profile_day", "profile_id", "weekday"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("room_availability_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[object] = mapped_column(Time, nullable=False)
    end_time: Mapped[object] = mapped_column(Time, nullable=False)
    availability: Mapped[str] = mapped_column(String(12), nullable=False)
    profile: Mapped[RoomAvailabilityProfile] = relationship(back_populates="windows")
