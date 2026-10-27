"""Add shared S5 requirements and explicit room/time configuration.

Revision ID: 20261021_02
Revises: 20261021_01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261021_02"
down_revision: Union[str, None] = "20261021_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "shared_subject_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("semester_id", sa.Integer(), sa.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("subject_id", sa.Integer(), sa.ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("weekly_lecture_hours", sa.Integer(), nullable=True),
        sa.Column("weekly_tutorial_hours", sa.Integer(), nullable=True),
        sa.Column("weekly_practical_hours", sa.Integer(), nullable=True),
        sa.Column("lecture_session_minutes", sa.Integer(), nullable=True),
        sa.Column("tutorial_session_minutes", sa.Integer(), nullable=True),
        sa.Column("practical_session_minutes", sa.Integer(), nullable=True),
        sa.UniqueConstraint("semester_id", "subject_id", name="uq_shared_requirement_semester_subject"),
        sa.CheckConstraint("weekly_lecture_hours IS NULL OR weekly_lecture_hours >= 0", name="ck_shared_lecture_nonnegative"),
        sa.CheckConstraint("weekly_tutorial_hours IS NULL OR weekly_tutorial_hours >= 0", name="ck_shared_tutorial_nonnegative"),
        sa.CheckConstraint("weekly_practical_hours IS NULL OR weekly_practical_hours >= 0", name="ck_shared_practical_nonnegative"),
        sa.CheckConstraint("lecture_session_minutes IS NULL OR lecture_session_minutes > 0", name="ck_shared_lecture_duration_positive"),
        sa.CheckConstraint("tutorial_session_minutes IS NULL OR tutorial_session_minutes > 0", name="ck_shared_tutorial_duration_positive"),
        sa.CheckConstraint("practical_session_minutes IS NULL OR practical_session_minutes > 0", name="ck_shared_practical_duration_positive"),
    )
    op.create_index("ix_shared_subject_requirements_semester_id", "shared_subject_requirements", ["semester_id"])
    op.create_index("ix_shared_subject_requirements_subject_id", "shared_subject_requirements", ["subject_id"])

    op.create_table(
        "section_teacher_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("shared_subject_requirements.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("student_group_id", sa.Integer(), sa.ForeignKey("student_groups.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("faculty_id", sa.Integer(), sa.ForeignKey("faculty.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("requirement_id", "student_group_id", "faculty_id", name="uq_section_teacher_assignment"),
    )
    for column in ("requirement_id", "student_group_id", "faculty_id"):
        op.create_index(f"ix_section_teacher_assignments_{column}", "section_teacher_assignments", [column])

    op.create_table(
        "college_time_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("version", name="uq_college_time_configuration_version"),
        sa.CheckConstraint("version > 0", name="ck_time_config_version_positive"),
    )
    op.create_index("ix_college_time_configurations_is_active", "college_time_configurations", ["is_active"])
    op.create_index(
        "uq_one_active_time_configuration", "college_time_configurations", ["is_active"], unique=True,
        sqlite_where=sa.text("is_active = 1"), postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "college_working_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("college_time_configurations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.UniqueConstraint("configuration_id", "weekday", name="uq_config_weekday"),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_working_day_range"),
    )
    op.create_index("ix_college_working_days_configuration_id", "college_working_days", ["configuration_id"])

    op.create_table(
        "college_time_blocks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("college_time_configurations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(12), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(80), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_lab_compatible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("configuration_id", "sequence_number", name="uq_config_time_block_sequence"),
        sa.UniqueConstraint("configuration_id", "period_number", name="uq_config_period_number"),
        sa.CheckConstraint("sequence_number > 0", name="ck_time_block_sequence_positive"),
        sa.CheckConstraint("block_type IN ('teaching', 'break', 'lunch')", name="ck_time_block_type"),
        sa.CheckConstraint("period_number IS NULL OR period_number > 0", name="ck_time_block_period_positive"),
        sa.CheckConstraint("end_time > start_time", name="ck_time_block_ordered_times"),
        sa.CheckConstraint("block_type = 'teaching' OR is_lab_compatible = 0", name="ck_only_teaching_lab_compatible"),
    )
    op.create_index("ix_college_time_blocks_configuration_id", "college_time_blocks", ["configuration_id"])
    op.create_index(
        "uq_config_lunch", "college_time_blocks", ["configuration_id"], unique=True,
        sqlite_where=sa.text("block_type = 'lunch'"),
        postgresql_where=sa.text("block_type = 'lunch'"),
    )

    op.create_table(
        "room_capabilities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_name", sa.String(120), nullable=False),
        sa.Column("capability_type", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.UniqueConstraint("room_id", "capability_name", name="uq_room_capability_name"),
        sa.CheckConstraint("capability_type IN ('equipment', 'capability')", name="ck_room_capability_type"),
        sa.CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_room_capability_quantity_positive"),
    )
    op.create_index("ix_room_capabilities_room_id", "room_capabilities", ["room_id"])

    op.create_table(
        "room_availability_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("room_id", sa.Integer(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("room_id", name="uq_room_availability_profile"),
    )
    op.create_index("ix_room_availability_profiles_room_id", "room_availability_profiles", ["room_id"])

    op.create_table(
        "room_availability_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("room_availability_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("availability", sa.String(12), nullable=False),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_room_window_weekday"),
        sa.CheckConstraint("availability IN ('available', 'unavailable')", name="ck_room_window_availability"),
        sa.CheckConstraint("end_time > start_time", name="ck_room_window_ordered_times"),
    )
    op.create_index("ix_room_availability_windows_profile_id", "room_availability_windows", ["profile_id"])
    op.create_index("ix_room_availability_profile_day", "room_availability_windows", ["profile_id", "weekday"])


def downgrade() -> None:
    # Removes only tables introduced by this revision.
    op.drop_index("ix_room_availability_profile_day", table_name="room_availability_windows")
    op.drop_index("ix_room_availability_windows_profile_id", table_name="room_availability_windows")
    op.drop_table("room_availability_windows")
    op.drop_index("ix_room_availability_profiles_room_id", table_name="room_availability_profiles")
    op.drop_table("room_availability_profiles")
    op.drop_index("ix_room_capabilities_room_id", table_name="room_capabilities")
    op.drop_table("room_capabilities")
    op.drop_index("uq_config_lunch", table_name="college_time_blocks")
    op.drop_index("ix_college_time_blocks_configuration_id", table_name="college_time_blocks")
    op.drop_table("college_time_blocks")
    op.drop_index("ix_college_working_days_configuration_id", table_name="college_working_days")
    op.drop_table("college_working_days")
    op.drop_index("uq_one_active_time_configuration", table_name="college_time_configurations")
    op.drop_index("ix_college_time_configurations_is_active", table_name="college_time_configurations")
    op.drop_table("college_time_configurations")
    for column in ("faculty_id", "student_group_id", "requirement_id"):
        op.drop_index(f"ix_section_teacher_assignments_{column}", table_name="section_teacher_assignments")
    op.drop_table("section_teacher_assignments")
    op.drop_index("ix_shared_subject_requirements_subject_id", table_name="shared_subject_requirements")
    op.drop_index("ix_shared_subject_requirements_semester_id", table_name="shared_subject_requirements")
    op.drop_table("shared_subject_requirements")
