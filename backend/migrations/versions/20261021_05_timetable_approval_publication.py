"""Add immutable approvals and an atomic official publication pointer."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261021_05"
down_revision: Union[str, None] = "20261021_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timetable_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("academic_year_id", sa.Integer(), sa.ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("semester_id", sa.Integer(), sa.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("semester_number", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="approved"),
        sa.Column("alternative_number", sa.Integer(), nullable=False),
        sa.Column("sessions_json", sa.JSON(), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("semester_id", "version", name="uq_timetable_snapshot_semester_version"),
        sa.CheckConstraint("status = 'approved'", name="ck_timetable_snapshot_approved_only"),
        sa.CheckConstraint("version > 0", name="ck_timetable_snapshot_version_positive"),
    )
    op.create_index("ix_timetable_snapshots_academic_year_id", "timetable_snapshots", ["academic_year_id"])
    op.create_index("ix_timetable_snapshots_semester_id", "timetable_snapshots", ["semester_id"])

    op.create_table(
        "official_timetables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("academic_year_id", sa.Integer(), sa.ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("semester_id", sa.Integer(), sa.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("timetable_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("semester_id", name="uq_official_timetable_semester"),
        sa.UniqueConstraint("snapshot_id", name="uq_official_timetables_snapshot"),
    )
    op.create_index("ix_official_timetables_academic_year_id", "official_timetables", ["academic_year_id"])
    op.create_index("ix_official_timetables_semester_id", "official_timetables", ["semester_id"])

    op.create_table(
        "timetable_publication_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("academic_year_id", sa.Integer(), sa.ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("semester_id", sa.Integer(), sa.ForeignKey("semesters.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), sa.ForeignKey("timetable_snapshots.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("previous_snapshot_id", sa.Integer(), sa.ForeignKey("timetable_snapshots.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_timetable_publication_events_academic_year_id", "timetable_publication_events", ["academic_year_id"])
    op.create_index("ix_timetable_publication_events_semester_id", "timetable_publication_events", ["semester_id"])
    op.create_index("ix_timetable_publication_events_snapshot_id", "timetable_publication_events", ["snapshot_id"])
    op.create_index("ix_timetable_publication_semester_time", "timetable_publication_events", ["semester_id", "published_at"])

    # Snapshot and publication history are append-only at the database layer.
    op.execute("CREATE TRIGGER timetable_snapshots_no_update BEFORE UPDATE ON timetable_snapshots BEGIN SELECT RAISE(ABORT, 'approved timetable snapshots are immutable'); END")
    op.execute("CREATE TRIGGER timetable_snapshots_no_delete BEFORE DELETE ON timetable_snapshots BEGIN SELECT RAISE(ABORT, 'approved timetable snapshots are immutable'); END")
    op.execute("CREATE TRIGGER timetable_publication_events_no_update BEFORE UPDATE ON timetable_publication_events BEGIN SELECT RAISE(ABORT, 'publication history is append-only'); END")
    op.execute("CREATE TRIGGER timetable_publication_events_no_delete BEFORE DELETE ON timetable_publication_events BEGIN SELECT RAISE(ABORT, 'publication history is append-only'); END")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS timetable_publication_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS timetable_publication_events_no_update")
    op.execute("DROP TRIGGER IF EXISTS timetable_snapshots_no_delete")
    op.execute("DROP TRIGGER IF EXISTS timetable_snapshots_no_update")
    op.drop_index("ix_timetable_publication_semester_time", table_name="timetable_publication_events")
    op.drop_index("ix_timetable_publication_events_snapshot_id", table_name="timetable_publication_events")
    op.drop_index("ix_timetable_publication_events_semester_id", table_name="timetable_publication_events")
    op.drop_index("ix_timetable_publication_events_academic_year_id", table_name="timetable_publication_events")
    op.drop_table("timetable_publication_events")
    op.drop_index("ix_official_timetables_semester_id", table_name="official_timetables")
    op.drop_index("ix_official_timetables_academic_year_id", table_name="official_timetables")
    op.drop_table("official_timetables")
    op.drop_index("ix_timetable_snapshots_semester_id", table_name="timetable_snapshots")
    op.drop_index("ix_timetable_snapshots_academic_year_id", table_name="timetable_snapshots")
    op.drop_table("timetable_snapshots")
