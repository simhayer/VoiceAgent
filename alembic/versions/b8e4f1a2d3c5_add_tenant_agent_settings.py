"""add tenant_agent_settings table and backfill existing tenants

Revision ID: b8e4f1a2d3c5
Revises: 5c81c2b7c57b
Create Date: 2026-03-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e4f1a2d3c5"
down_revision: Union[str, Sequence[str], None] = "c2f9b7d3a8aa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_agent_settings",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("openai_realtime_model", sa.String(length=120), nullable=True),
        sa.Column("openai_realtime_voice", sa.String(length=60), nullable=True),
        sa.Column("system_prompt_override", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )

    # Backfill: one row per existing tenant (NULLs = use app defaults)
    op.execute(
        sa.text(
            "INSERT INTO tenant_agent_settings (tenant_id, openai_realtime_model, openai_realtime_voice, system_prompt_override) "
            "SELECT id, NULL, NULL, tenants.system_prompt_override FROM tenants"
        )
    )


def downgrade() -> None:
    op.drop_table("tenant_agent_settings")
