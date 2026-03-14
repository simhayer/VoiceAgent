"""placeholder for revision already applied in DB (c2f9b7d3a8aa)

The database was stamped with this revision (e.g. from another branch or env).
This no-op migration lets Alembic recognize it so upgrade head can run.

Revision ID: c2f9b7d3a8aa
Revises: e73f5a8b1c9d
Create Date: 2026-03-13

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c2f9b7d3a8aa"
down_revision: Union[str, Sequence[str], None] = "e73f5a8b1c9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
