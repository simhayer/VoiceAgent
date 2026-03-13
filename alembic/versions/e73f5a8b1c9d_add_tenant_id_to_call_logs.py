"""add tenant_id to call_logs

Revision ID: e73f5a8b1c9d
Revises: a1b2c3d4e5f6
Create Date: 2026-03-13 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e73f5a8b1c9d"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("call_logs", sa.Column("tenant_id", sa.String(length=36), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE call_logs
            SET tenant_id = (
                SELECT id
                FROM tenants
                ORDER BY created_at
                LIMIT 1
            )
            WHERE tenant_id IS NULL
            """
        )
    )

    op.alter_column("call_logs", "tenant_id", nullable=False)
    op.create_index(op.f("ix_call_logs_tenant_id"), "call_logs", ["tenant_id"], unique=False)
    op.create_foreign_key(
        "fk_call_logs_tenant_id",
        "call_logs",
        "tenants",
        ["tenant_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_call_logs_tenant_id", "call_logs", type_="foreignkey")
    op.drop_index(op.f("ix_call_logs_tenant_id"), table_name="call_logs")
    op.drop_column("call_logs", "tenant_id")
