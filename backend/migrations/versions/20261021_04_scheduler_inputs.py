"""Add explicit faculty, activity-resource, and academic-hour inputs."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261021_04"
down_revision: Union[str, None] = "20261021_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "college_time_configurations",
        sa.Column("academic_hour_minutes", sa.Integer(), nullable=True),
    )

    op.create_table(
        "faculty_scheduling_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("faculty_id", sa.Integer(), sa.ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("max_daily_minutes", sa.Integer(), nullable=True),
        sa.Column("max_weekly_minutes", sa.Integer(), nullable=True),
        sa.UniqueConstraint("faculty_id", name="uq_faculty_scheduling_profile"),
        sa.CheckConstraint("max_daily_minutes IS NULL OR max_daily_minutes > 0", name="ck_faculty_daily_limit_positive"),
        sa.CheckConstraint("max_weekly_minutes IS NULL OR max_weekly_minutes > 0", name="ck_faculty_weekly_limit_positive"),
    )
    op.create_index("ix_faculty_scheduling_profiles_faculty_id", "faculty_scheduling_profiles", ["faculty_id"])

    op.create_table(
        "faculty_availability_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("faculty_scheduling_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("availability", sa.String(length=12), nullable=False),
        sa.CheckConstraint("weekday >= 0 AND weekday <= 6", name="ck_faculty_window_weekday"),
        sa.CheckConstraint("availability IN ('available', 'unavailable')", name="ck_faculty_window_availability"),
        sa.CheckConstraint("end_time > start_time", name="ck_faculty_window_ordered_times"),
    )
    op.create_index("ix_faculty_availability_windows_profile_id", "faculty_availability_windows", ["profile_id"])
    op.create_index("ix_faculty_availability_profile_day", "faculty_availability_windows", ["profile_id", "weekday"])

    op.create_table(
        "activity_room_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("shared_subject_requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("activity_type", sa.String(length=16), nullable=False),
        sa.Column("room_type", sa.String(length=20), nullable=False),
        sa.UniqueConstraint("requirement_id", "activity_type", name="uq_activity_room_requirement"),
        sa.CheckConstraint("activity_type IN ('lecture', 'tutorial', 'practical')", name="ck_activity_room_activity_type"),
        sa.CheckConstraint("room_type IN ('classroom', 'laboratory', 'other')", name="ck_activity_room_type"),
    )
    op.create_index("ix_activity_room_requirements_requirement_id", "activity_room_requirements", ["requirement_id"])

    op.create_table(
        "activity_equipment_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_requirement_id", sa.Integer(), sa.ForeignKey("activity_room_requirements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("capability_name", sa.String(length=120), nullable=False),
        sa.UniqueConstraint("activity_requirement_id", "capability_name", name="uq_activity_equipment_requirement"),
    )
    op.create_index("ix_activity_equipment_requirements_activity_requirement_id", "activity_equipment_requirements", ["activity_requirement_id"])


def downgrade() -> None:
    op.drop_index("ix_activity_equipment_requirements_activity_requirement_id", table_name="activity_equipment_requirements")
    op.drop_table("activity_equipment_requirements")
    op.drop_index("ix_activity_room_requirements_requirement_id", table_name="activity_room_requirements")
    op.drop_table("activity_room_requirements")
    op.drop_index("ix_faculty_availability_profile_day", table_name="faculty_availability_windows")
    op.drop_index("ix_faculty_availability_windows_profile_id", table_name="faculty_availability_windows")
    op.drop_table("faculty_availability_windows")
    op.drop_index("ix_faculty_scheduling_profiles_faculty_id", table_name="faculty_scheduling_profiles")
    op.drop_table("faculty_scheduling_profiles")
    op.drop_column("college_time_configurations", "academic_hour_minutes")
