"""Input and output validation models for academic records."""

from datetime import date, datetime, time
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RecordSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReadSchema(RecordSchema):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PatchSchema(RecordSchema):
    """Reject explicit null for fields that are not optional in storage."""

    nullable_fields: ClassVar[frozenset[str]] = frozenset()

    @model_validator(mode="after")
    def reject_null_for_required_fields(self):
        for field_name in self.model_fields_set:
            if getattr(self, field_name) is None and field_name not in self.nullable_fields:
                raise ValueError(f"{field_name} cannot be null")
        return self


class DepartmentCreate(RecordSchema):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=20)
    is_active: bool = True


class DepartmentUpdate(PatchSchema):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    code: str | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None


class DepartmentRead(ReadSchema):
    name: str
    code: str
    is_active: bool


class AcademicYearCreate(RecordSchema):
    name: str = Field(min_length=1, max_length=30)
    start_date: date
    end_date: date
    is_active: bool = True

    @model_validator(mode="after")
    def dates_are_ordered(self):
        if self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class AcademicYearUpdate(PatchSchema):
    name: str | None = Field(default=None, min_length=1, max_length=30)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def supplied_dates_are_ordered(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        return self


class AcademicYearRead(ReadSchema):
    name: str
    start_date: date
    end_date: date
    is_active: bool


class SemesterCreate(RecordSchema):
    department_id: int = Field(gt=0)
    academic_year_id: int = Field(gt=0)
    semester_number: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=50)
    is_active: bool = True


class SemesterUpdate(PatchSchema):
    department_id: int | None = Field(default=None, gt=0)
    academic_year_id: int | None = Field(default=None, gt=0)
    semester_number: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None


class SemesterRead(ReadSchema):
    department_id: int
    academic_year_id: int
    semester_number: int
    name: str
    is_active: bool


class StudentGroupCreate(RecordSchema):
    semester_id: int = Field(gt=0)
    group_name: str = Field(min_length=1, max_length=80)
    section_identifier: str | None = Field(default=None, max_length=30)
    student_count: int = Field(gt=0)
    is_active: bool = True


class StudentGroupUpdate(PatchSchema):
    nullable_fields = frozenset({"section_identifier"})
    semester_id: int | None = Field(default=None, gt=0)
    group_name: str | None = Field(default=None, min_length=1, max_length=80)
    section_identifier: str | None = Field(default=None, max_length=30)
    student_count: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class StudentGroupRead(ReadSchema):
    semester_id: int
    group_name: str
    section_identifier: str | None
    student_count: int
    is_active: bool
    is_predefined: bool = False


class S5GroupConfigurationRequest(RecordSchema):
    """Manual, create-only configuration for the confirmed S5 sections."""

    academic_year_name: str = Field(min_length=1, max_length=30)


class TimetableGenerationRequest(RecordSchema):
    academic_year_id: int = Field(gt=0)
    number_of_alternatives: Literal[3, 4] = 4


class TimetableApprovalRequest(RecordSchema):
    academic_year_id: int = Field(gt=0)
    alternative_number: int = Field(ge=1, le=4)
    sessions: list[dict[str, object]]
    confirm_approval: Literal[True]


class TimetablePublishRequest(RecordSchema):
    confirm_publish: Literal[True]


class TimetableSnapshotRead(ReadSchema):
    academic_year_id: int
    semester_id: int
    semester_number: int
    version: int
    status: str
    alternative_number: int
    sessions_json: list[dict]
    configuration_json: dict
    validation_json: list[str]
    approved_at: datetime
    created_at: datetime


class FacultyCreate(RecordSchema):
    faculty_name: str = Field(min_length=1, max_length=120)
    faculty_code: str = Field(min_length=1, max_length=30)
    email: EmailStr | None = None
    is_active: bool = True


class FacultyUpdate(PatchSchema):
    nullable_fields = frozenset({"email"})
    faculty_name: str | None = Field(default=None, min_length=1, max_length=120)
    faculty_code: str | None = Field(default=None, min_length=1, max_length=30)
    email: EmailStr | None = None
    is_active: bool | None = None


class FacultyRead(ReadSchema):
    faculty_name: str
    faculty_code: str
    email: EmailStr | None
    is_active: bool


class FacultySchedulingProfileCreate(RecordSchema):
    faculty_id: int = Field(gt=0)
    is_confirmed: bool = False
    max_daily_minutes: int | None = Field(default=None, gt=0)
    max_weekly_minutes: int | None = Field(default=None, gt=0)


class FacultySchedulingProfileUpdate(PatchSchema):
    nullable_fields = frozenset({"max_daily_minutes", "max_weekly_minutes"})
    faculty_id: int | None = Field(default=None, gt=0)
    is_confirmed: bool | None = None
    max_daily_minutes: int | None = Field(default=None, gt=0)
    max_weekly_minutes: int | None = Field(default=None, gt=0)


class FacultySchedulingProfileRead(ReadSchema):
    faculty_id: int
    is_confirmed: bool
    max_daily_minutes: int | None
    max_weekly_minutes: int | None


class FacultyAvailabilityWindowCreate(RecordSchema):
    profile_id: int = Field(gt=0)
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    availability: Literal["available", "unavailable"]

    @model_validator(mode="after")
    def valid_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class FacultyAvailabilityWindowUpdate(PatchSchema):
    profile_id: int | None = Field(default=None, gt=0)
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    availability: Literal["available", "unavailable"] | None = None


class FacultyAvailabilityWindowRead(ReadSchema):
    profile_id: int
    weekday: int
    start_time: time
    end_time: time
    availability: Literal["available", "unavailable"]


RoomType = Literal["classroom", "laboratory", "other"]


class RoomCreate(RecordSchema):
    room_name: str = Field(min_length=1, max_length=80)
    room_type: RoomType
    capacity: int = Field(gt=0)
    is_active: bool = True


class RoomUpdate(PatchSchema):
    room_name: str | None = Field(default=None, min_length=1, max_length=80)
    room_type: RoomType | None = None
    capacity: int | None = Field(default=None, gt=0)
    is_active: bool | None = None


class RoomRead(ReadSchema):
    room_name: str
    room_type: RoomType
    capacity: int
    is_active: bool


class SubjectCreate(RecordSchema):
    subject_code: str = Field(min_length=1, max_length=30)
    subject_name: str = Field(min_length=1, max_length=160)
    is_active: bool = True


class SubjectUpdate(PatchSchema):
    subject_code: str | None = Field(default=None, min_length=1, max_length=30)
    subject_name: str | None = Field(default=None, min_length=1, max_length=160)
    is_active: bool | None = None


class SubjectRead(ReadSchema):
    subject_code: str
    subject_name: str
    is_active: bool


class SemesterSubjectCreate(RecordSchema):
    semester_id: int = Field(gt=0)
    student_group_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    weekly_lecture_hours: int = Field(default=0, ge=0)
    weekly_tutorial_hours: int = Field(default=0, ge=0)
    weekly_practical_hours: int = Field(default=0, ge=0)
    lecture_session_minutes: int | None = Field(default=None, gt=0)
    tutorial_session_minutes: int | None = Field(default=None, gt=0)
    practical_session_minutes: int | None = Field(default=None, gt=0)


class SemesterSubjectUpdate(PatchSchema):
    nullable_fields = frozenset(
        {"lecture_session_minutes", "tutorial_session_minutes", "practical_session_minutes"}
    )
    semester_id: int | None = Field(default=None, gt=0)
    student_group_id: int | None = Field(default=None, gt=0)
    subject_id: int | None = Field(default=None, gt=0)
    weekly_lecture_hours: int | None = Field(default=None, ge=0)
    weekly_tutorial_hours: int | None = Field(default=None, ge=0)
    weekly_practical_hours: int | None = Field(default=None, ge=0)
    lecture_session_minutes: int | None = Field(default=None, gt=0)
    tutorial_session_minutes: int | None = Field(default=None, gt=0)
    practical_session_minutes: int | None = Field(default=None, gt=0)


class SemesterSubjectRead(ReadSchema):
    semester_id: int
    student_group_id: int
    subject_id: int
    weekly_lecture_hours: int
    weekly_tutorial_hours: int
    weekly_practical_hours: int
    lecture_session_minutes: int | None
    tutorial_session_minutes: int | None
    practical_session_minutes: int | None


class FacultySubjectCreate(RecordSchema):
    faculty_id: int = Field(gt=0)
    semester_subject_id: int = Field(gt=0)


class FacultySubjectUpdate(PatchSchema):
    faculty_id: int | None = Field(default=None, gt=0)
    semester_subject_id: int | None = Field(default=None, gt=0)


class FacultySubjectRead(ReadSchema):
    faculty_id: int
    semester_subject_id: int


class SharedSubjectRequirementCreate(RecordSchema):
    semester_id: int = Field(gt=0)
    subject_id: int = Field(gt=0)
    weekly_lecture_hours: int | None = Field(default=None, ge=0)
    weekly_tutorial_hours: int | None = Field(default=None, ge=0)
    weekly_practical_hours: int | None = Field(default=None, ge=0)
    weekly_lecture_sessions: int | None = Field(default=None, ge=0)
    weekly_tutorial_sessions: int | None = Field(default=None, ge=0)
    weekly_practical_sessions: int | None = Field(default=None, ge=0)
    lecture_session_minutes: int | None = Field(default=None, gt=0)
    tutorial_session_minutes: int | None = Field(default=None, gt=0)
    practical_session_minutes: int | None = Field(default=None, gt=0)


class SharedSubjectRequirementUpdate(PatchSchema):
    nullable_fields = frozenset({
        "weekly_lecture_hours", "weekly_tutorial_hours", "weekly_practical_hours",
        "weekly_lecture_sessions", "weekly_tutorial_sessions", "weekly_practical_sessions",
        "lecture_session_minutes", "tutorial_session_minutes", "practical_session_minutes",
    })
    semester_id: int | None = Field(default=None, gt=0)
    subject_id: int | None = Field(default=None, gt=0)
    weekly_lecture_hours: int | None = Field(default=None, ge=0)
    weekly_tutorial_hours: int | None = Field(default=None, ge=0)
    weekly_practical_hours: int | None = Field(default=None, ge=0)
    weekly_lecture_sessions: int | None = Field(default=None, ge=0)
    weekly_tutorial_sessions: int | None = Field(default=None, ge=0)
    weekly_practical_sessions: int | None = Field(default=None, ge=0)
    lecture_session_minutes: int | None = Field(default=None, gt=0)
    tutorial_session_minutes: int | None = Field(default=None, gt=0)
    practical_session_minutes: int | None = Field(default=None, gt=0)


class SharedSubjectRequirementRead(ReadSchema):
    semester_id: int
    subject_id: int
    weekly_lecture_hours: int | None
    weekly_tutorial_hours: int | None
    weekly_practical_hours: int | None
    weekly_lecture_sessions: int | None
    weekly_tutorial_sessions: int | None
    weekly_practical_sessions: int | None
    lecture_session_minutes: int | None
    tutorial_session_minutes: int | None
    practical_session_minutes: int | None


class SectionTeacherAssignmentCreate(RecordSchema):
    requirement_id: int = Field(gt=0)
    student_group_id: int = Field(gt=0)
    faculty_id: int = Field(gt=0)


class SectionTeacherAssignmentUpdate(PatchSchema):
    requirement_id: int | None = Field(default=None, gt=0)
    student_group_id: int | None = Field(default=None, gt=0)
    faculty_id: int | None = Field(default=None, gt=0)


class SectionTeacherAssignmentRead(ReadSchema):
    requirement_id: int
    student_group_id: int
    faculty_id: int


class ActivityRoomRequirementCreate(RecordSchema):
    requirement_id: int = Field(gt=0)
    activity_type: Literal["lecture", "tutorial", "practical"]
    room_type: Literal["classroom", "laboratory", "other"]


class ActivityRoomRequirementUpdate(PatchSchema):
    requirement_id: int | None = Field(default=None, gt=0)
    activity_type: Literal["lecture", "tutorial", "practical"] | None = None
    room_type: Literal["classroom", "laboratory", "other"] | None = None


class ActivityRoomRequirementRead(ReadSchema):
    requirement_id: int
    activity_type: Literal["lecture", "tutorial", "practical"]
    room_type: Literal["classroom", "laboratory", "other"]


class ActivityEquipmentRequirementCreate(RecordSchema):
    activity_requirement_id: int = Field(gt=0)
    capability_name: str = Field(min_length=1, max_length=120)


class ActivityEquipmentRequirementUpdate(PatchSchema):
    activity_requirement_id: int | None = Field(default=None, gt=0)
    capability_name: str | None = Field(default=None, min_length=1, max_length=120)


class ActivityEquipmentRequirementRead(ReadSchema):
    activity_requirement_id: int
    capability_name: str


class CollegeTimeConfigurationCreate(RecordSchema):
    version: int = Field(gt=0)
    is_active: bool = False
    academic_hour_minutes: int | None = Field(default=None, gt=0)


class CollegeTimeConfigurationUpdate(PatchSchema):
    nullable_fields = frozenset({"academic_hour_minutes"})
    version: int | None = Field(default=None, gt=0)
    is_active: bool | None = None
    academic_hour_minutes: int | None = Field(default=None, gt=0)


class CollegeTimeConfigurationRead(ReadSchema):
    version: int
    is_active: bool
    academic_hour_minutes: int | None


class CollegeWorkingDayCreate(RecordSchema):
    configuration_id: int = Field(gt=0)
    weekday: int = Field(ge=0, le=6)


class CollegeWorkingDayUpdate(PatchSchema):
    configuration_id: int | None = Field(default=None, gt=0)
    weekday: int | None = Field(default=None, ge=0, le=6)


class CollegeWorkingDayRead(ReadSchema):
    configuration_id: int
    weekday: int


class CollegeTimeBlockCreate(RecordSchema):
    configuration_id: int = Field(gt=0)
    sequence_number: int = Field(gt=0)
    block_type: Literal["teaching", "break", "lunch"]
    period_number: int | None = Field(default=None, gt=0)
    label: str | None = Field(default=None, max_length=80)
    start_time: time
    end_time: time
    is_lab_compatible: bool = False

    @model_validator(mode="after")
    def valid_block(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        if self.block_type == "teaching" and self.period_number is None:
            raise ValueError("Teaching blocks require a period_number")
        if self.block_type != "teaching" and self.is_lab_compatible:
            raise ValueError("Only teaching periods can be laboratory-compatible")
        return self


class CollegeTimeBlockUpdate(PatchSchema):
    nullable_fields = frozenset({"period_number", "label"})
    configuration_id: int | None = Field(default=None, gt=0)
    sequence_number: int | None = Field(default=None, gt=0)
    block_type: Literal["teaching", "break", "lunch"] | None = None
    period_number: int | None = Field(default=None, gt=0)
    label: str | None = Field(default=None, max_length=80)
    start_time: time | None = None
    end_time: time | None = None
    is_lab_compatible: bool | None = None


class CollegeTimeBlockRead(ReadSchema):
    configuration_id: int
    sequence_number: int
    block_type: Literal["teaching", "break", "lunch"]
    period_number: int | None
    label: str | None
    start_time: time
    end_time: time
    is_lab_compatible: bool


class RoomCapabilityCreate(RecordSchema):
    room_id: int = Field(gt=0)
    capability_name: str = Field(min_length=1, max_length=120)
    capability_type: Literal["equipment", "capability"]
    quantity: int | None = Field(default=None, gt=0)


class RoomCapabilityUpdate(PatchSchema):
    nullable_fields = frozenset({"quantity"})
    room_id: int | None = Field(default=None, gt=0)
    capability_name: str | None = Field(default=None, min_length=1, max_length=120)
    capability_type: Literal["equipment", "capability"] | None = None
    quantity: int | None = Field(default=None, gt=0)


class RoomCapabilityRead(ReadSchema):
    room_id: int
    capability_name: str
    capability_type: Literal["equipment", "capability"]
    quantity: int | None


class RoomAvailabilityProfileCreate(RecordSchema):
    room_id: int = Field(gt=0)
    is_confirmed: bool = False


class RoomAvailabilityProfileUpdate(PatchSchema):
    room_id: int | None = Field(default=None, gt=0)
    is_confirmed: bool | None = None


class RoomAvailabilityProfileRead(ReadSchema):
    room_id: int
    is_confirmed: bool


class RoomAvailabilityWindowCreate(RecordSchema):
    profile_id: int = Field(gt=0)
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    availability: Literal["available", "unavailable"]

    @model_validator(mode="after")
    def valid_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class RoomAvailabilityWindowUpdate(PatchSchema):
    profile_id: int | None = Field(default=None, gt=0)
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    availability: Literal["available", "unavailable"] | None = None


class RoomAvailabilityWindowRead(ReadSchema):
    profile_id: int
    weekday: int
    start_time: time
    end_time: time
    availability: Literal["available", "unavailable"]
