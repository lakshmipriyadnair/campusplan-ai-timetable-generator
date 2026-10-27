"""Add nullable weekly session counts to shared S5 requirements."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261021_03"
down_revision: Union[str, None] = "20261021_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable keeps existing S5 requirements explicitly unconfirmed.
    op.add_column("shared_subject_requirements", sa.Column("weekly_lecture_sessions", sa.Integer(), nullable=True))
    op.add_column("shared_subject_requirements", sa.Column("weekly_tutorial_sessions", sa.Integer(), nullable=True))
    op.add_column("shared_subject_requirements", sa.Column("weekly_practical_sessions", sa.Integer(), nullable=True))


def downgrade() -> None:
    # This removes any session counts entered after this revision is applied.
    op.drop_column("shared_subject_requirements", "weekly_practical_sessions")
    op.drop_column("shared_subject_requirements", "weekly_tutorial_sessions")
    op.drop_column("shared_subject_requirements", "weekly_lecture_sessions")
