"""initial schema with multi-tenancy

Revision ID: 04f466c7e8e6
Revises: 
Create Date: 2026-03-10 23:44:24.722849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04f466c7e8e6'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Create new tables
    op.create_table('tenants',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('twilio_phone_number', sa.String(length=20), nullable=True),
        sa.Column('cartesia_voice_id', sa.String(length=100), nullable=True),
        sa.Column('greeting_message', sa.Text(), nullable=True),
        sa.Column('system_prompt_override', sa.Text(), nullable=True),
        sa.Column('emergency_phone', sa.String(length=20), nullable=True),
        sa.Column('transfer_phone', sa.String(length=20), nullable=True),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('plan', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
        sa.UniqueConstraint('twilio_phone_number')
    )

    # Insert a default tenant so existing rows can reference it
    op.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, timezone, plan, is_active) "
            "VALUES (:id, :name, :slug, :tz, :plan, :active)"
        ).bindparams(
            id=DEFAULT_TENANT_ID,
            name="Default Clinic",
            slug="default-clinic",
            tz="America/Los_Angeles",
            plan="starter",
            active=True,
        )
    )

    op.create_table('users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False),
        sa.Column('hashed_password', sa.String(length=200), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_tenant_id'), 'users', ['tenant_id'], unique=False)

    # Add tenant_id as nullable first, backfill, then make non-null
    for table in ['appointments', 'availability_rules', 'office_config', 'patients', 'providers']:
        op.add_column(table, sa.Column('tenant_id', sa.String(length=36), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET tenant_id = :tid").bindparams(tid=DEFAULT_TENANT_ID))
        op.alter_column(table, 'tenant_id', nullable=False)
        op.create_index(op.f(f'ix_{table}_tenant_id'), table, ['tenant_id'], unique=False)
        op.create_foreign_key(f'fk_{table}_tenant_id', table, 'tenants', ['tenant_id'], ['id'])

    # Replace global unique constraints with tenant-scoped ones
    op.drop_constraint('office_config_key_key', 'office_config', type_='unique')
    op.create_unique_constraint('uq_office_config_tenant_key', 'office_config', ['tenant_id', 'key'])

    op.drop_constraint('patients_phone_key', 'patients', type_='unique')
    op.create_unique_constraint('uq_patient_tenant_phone', 'patients', ['tenant_id', 'phone'])


def downgrade() -> None:
    for table in ['providers', 'patients', 'office_config', 'availability_rules', 'appointments']:
        op.drop_constraint(f'fk_{table}_tenant_id', table, type_='foreignkey')
        op.drop_index(op.f(f'ix_{table}_tenant_id'), table_name=table)
        op.drop_column(table, 'tenant_id')

    op.drop_constraint('uq_office_config_tenant_key', 'office_config', type_='unique')
    op.create_unique_constraint('office_config_key_key', 'office_config', ['key'])

    op.drop_constraint('uq_patient_tenant_phone', 'patients', type_='unique')
    op.create_unique_constraint('patients_phone_key', 'patients', ['phone'])

    op.drop_index(op.f('ix_users_tenant_id'), table_name='users')
    op.drop_table('users')
    op.drop_table('tenants')
