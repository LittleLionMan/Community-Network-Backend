"""Add enhanced service fields 2

Revision ID: 7e8e4839ff21
Revises: 9fb01f10c65b
Create Date: 2025-09-16 18:39:04.168941

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e8e4839ff21'
down_revision: Union[str, Sequence[str], None] = '9fb01f10c65b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Services Tabelle hat bereits alle Spalten - nichts zu tun!

    # Nur die neuen Tabellen erstellen, falls sie nicht existieren
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Create service_interests table
    if 'service_interests' not in existing_tables:
        op.create_table('service_interests',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('message', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.Column('status', sa.String(50), nullable=False, default='pending'),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('service_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['service_id'], ['services.id'], ),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # Create moderation_actions table
    if 'moderation_actions' not in existing_tables:
        op.create_table('moderation_actions',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('action_type', sa.String(50), nullable=False),
            sa.Column('content_type', sa.String(50), nullable=False),
            sa.Column('content_id', sa.Integer(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )

def downgrade() -> None:
    op.drop_table('moderation_actions')
    op.drop_table('service_interests')

    with op.batch_alter_table('services', schema=None) as batch_op:
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('flagged_reason')
        batch_op.drop_column('flagged_at')
        batch_op.drop_column('admin_notes')
