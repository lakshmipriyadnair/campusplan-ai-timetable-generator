"""Explicit, create-only configuration for protected CSE student groups."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AcademicYear,
    Department,
    PredefinedStudentGroup,
    Semester,
    StudentGroup,
)


SUPPORTED_SEMESTER_NUMBERS = (1, 3, 5, 7)


class PredefinedGroupDefinition(BaseModel):
    """One group definition read from an explicit configuration file."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    group_code: str = Field(min_length=1, max_length=50)
    semester_number: Literal[1, 3, 5, 7]
    academic_year_name: str = Field(min_length=1, max_length=30)
    group_name: str = Field(min_length=1, max_length=80)
    student_count: int = Field(gt=0)


class PredefinedGroupsFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: list[PredefinedGroupDefinition] = Field(default_factory=list)


class PredefinedGroupConfigurationError(ValueError):
    """Raised when configuration conflicts with existing academic data."""


def configure_predefined_groups(
    db: Session, definitions: list[PredefinedGroupDefinition]
) -> list[StudentGroup]:
    """Create or safely identify configured groups without changing existing values.

    This function commits once. A repeated matching configuration is a no-op;
    conflicting data raises an error and rolls back the whole operation.
    """
    group_codes = [definition.group_code for definition in definitions]
    if len(group_codes) != len(set(group_codes)):
        raise PredefinedGroupConfigurationError("The configuration repeats a group_code.")

    target_keys = [
        (definition.academic_year_name, definition.semester_number, definition.group_name)
        for definition in definitions
    ]
    if len(target_keys) != len(set(target_keys)):
        raise PredefinedGroupConfigurationError(
            "The configuration repeats a semester and group name."
        )

    configured: list[StudentGroup] = []
    try:
        for definition in definitions:
            statement = (
                select(Semester)
                .join(Semester.department)
                .join(Semester.academic_year)
                .where(
Department.name == "CSE",
                    AcademicYear.name == definition.academic_year_name,
                    Semester.semester_number == definition.semester_number,
                )
            )
            semester = db.scalar(statement)
            if semester is None:
                raise PredefinedGroupConfigurationError(
                    "No matching CSE semester exists for "
                    f"{definition.academic_year_name} S{definition.semester_number}. "
                    "Create or confirm the academic year and semester first."
                )

            identity = db.scalar(
                select(PredefinedStudentGroup).where(
                    PredefinedStudentGroup.group_code == definition.group_code
                )
            )
            if identity is not None:
                existing_group = db.get(StudentGroup, identity.student_group_id)
                if existing_group is None or not _matches(existing_group, semester.id, definition):
                    raise PredefinedGroupConfigurationError(
                        f"{definition.group_code} already identifies different group data; "
                        "configuration never overwrites protected groups."
                    )
                configured.append(existing_group)
                continue

            existing_group = db.scalar(
                select(StudentGroup).where(
                    StudentGroup.semester_id == semester.id,
                    StudentGroup.group_name == definition.group_name,
                )
            )
            if existing_group is not None:
                if existing_group.student_count != definition.student_count:
                    raise PredefinedGroupConfigurationError(
                        f"{definition.group_name} already exists with a different student count; "
                        "configuration will not change it."
                    )
                group = existing_group
            else:
                group = StudentGroup(
                    semester_id=semester.id,
                    group_name=definition.group_name,
                    student_count=definition.student_count,
                )
                db.add(group)
                db.flush()

            db.add(
                PredefinedStudentGroup(
                    student_group_id=group.id,
                    group_code=definition.group_code,
                )
            )
            db.flush()
            configured.append(group)

        db.commit()
        return configured
    except IntegrityError as error:
        db.rollback()
        raise PredefinedGroupConfigurationError(
            "A group or stable group_code conflicts with existing records. "
            "No configuration changes were saved."
        ) from error
    except Exception:
        db.rollback()
        raise


def _matches(
    group: StudentGroup, semester_id: int, definition: PredefinedGroupDefinition
) -> bool:
    return (
        group.semester_id == semester_id
        and group.group_name == definition.group_name
        and group.student_count == definition.student_count
    )
