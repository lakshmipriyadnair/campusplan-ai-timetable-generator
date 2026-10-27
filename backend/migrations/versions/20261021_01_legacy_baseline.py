"""Marker for the existing academic schema; this revision performs no DDL.

Revision ID: 20261021_01
Revises: None
"""

from typing import Sequence, Union

revision: str = "20261021_01"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing installations are stamped here only after a schema preflight.
    # Fresh installations create current metadata and are stamped at head.
    pass


def downgrade() -> None:
    pass
