"""replace hashed_password with supabase_user_id

Revision ID: a1b2c3d4e5f6
Revises: 5c81c2b7c57b
Create Date: 2026-03-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5c81c2b7c57b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('supabase_user_id', sa.String(255), nullable=True))

    # Backfill existing rows with their id so the NOT NULL constraint can be applied
    op.execute("UPDATE users SET supabase_user_id = id WHERE supabase_user_id IS NULL")

    op.alter_column('users', 'supabase_user_id', nullable=False)
    op.create_index('ix_users_supabase_user_id', 'users', ['supabase_user_id'], unique=True)
    op.drop_column('users', 'hashed_password')


def downgrade() -> None:
    op.add_column('users', sa.Column('hashed_password', sa.String(200), nullable=True))
    op.execute("UPDATE users SET hashed_password = 'migrated' WHERE hashed_password IS NULL")
    op.alter_column('users', 'hashed_password', nullable=False)
    op.drop_index('ix_users_supabase_user_id', table_name='users')
    op.drop_column('users', 'supabase_user_id')
